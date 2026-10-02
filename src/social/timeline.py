"""Timeline cache, fan-out strategies and feed reads with cursors and ranking."""

from __future__ import annotations

import base64
import bisect
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

from social.graph import FollowGraph
from social.ids import timestamp_ms
from social.posts import Post, PostStore


class Strategy(str, Enum):
    WRITE = "write"  # fan-out on write (push)
    READ = "read"  # fan-out on read (pull)
    HYBRID = "hybrid"  # push for most authors, pull for high-follower authors


class TimelineCache:
    """Per-user list of post ids, newest first, capped. Production: Redis sorted sets / lists per user."""

    def __init__(self, max_size: int = 800) -> None:
        self.max_size = max_size
        self._timelines: dict[str, list[int]] = {}  # ascending ids; read newest-first

    def has(self, user: str) -> bool:
        return user in self._timelines

    def ensure(self, user: str) -> None:
        self._timelines.setdefault(user, [])

    def insert(self, user: str, post_id: int) -> None:
        tl = self._timelines.setdefault(user, [])
        i = bisect.bisect_left(tl, post_id)
        if i < len(tl) and tl[i] == post_id:
            return  # idempotent: redelivered fan-out events do not duplicate entries
        tl.insert(i, post_id)
        if len(tl) > self.max_size:
            del tl[0 : len(tl) - self.max_size]  # drop the oldest

    def page(self, user: str, before: int | None, limit: int) -> list[int]:
        tl = self._timelines.get(user, [])
        end = len(tl) if before is None else bisect.bisect_left(tl, before)
        return tl[max(0, end - limit) : end][::-1]

    def evict(self, user: str) -> None:
        self._timelines.pop(user, None)

    def size(self, user: str) -> int:
        return len(self._timelines.get(user, []))


def encode_cursor(before: int) -> str:
    return base64.urlsafe_b64encode(f"v1:{before}".encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> int | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        version, value = raw.split(":", 1)
        if version != "v1":
            raise ValueError
        return int(value)
    except (ValueError, UnicodeDecodeError) as e:
        raise ValueError("invalid cursor") from e


@dataclass
class FeedPage:
    posts: list[Post]
    next_cursor: str | None
    sources_read: int = 0  # timelines + author lists touched: the read cost of this request
    rebuilt: bool = False


@dataclass
class FanoutStats:
    timeline_writes: int = 0
    posts: int = 0
    per_post: list[int] = field(default_factory=list)


class FeedService:
    def __init__(
        self,
        graph: FollowGraph,
        posts: PostStore,
        cache: TimelineCache,
        strategy: Strategy = Strategy.HYBRID,
        celebrity_threshold: int = 10_000,
    ) -> None:
        self.graph = graph
        self.posts = posts
        self.cache = cache
        self.strategy = strategy
        self.celebrity_threshold = celebrity_threshold
        self.stats = FanoutStats()

    # --- classification ---------------------------------------------------------------------------------------
    def is_pull_author(self, author: str) -> bool:
        if self.strategy is Strategy.READ:
            return True
        if self.strategy is Strategy.WRITE:
            return False
        return self.graph.follower_count(author) >= self.celebrity_threshold

    # --- write path -------------------------------------------------------------------------------------------
    def fan_out(self, post: Post) -> int:
        """Push a new post into timelines. Returns the number of timeline writes (write amplification)."""
        writes = 0
        if self.strategy is not Strategy.READ:
            self.cache.insert(post.author, post.id)  # authors see their own posts immediately
            writes += 1
        if not self.is_pull_author(post.author):
            for follower in self.graph.followers(post.author):
                if self.cache.has(follower):  # inactive users have no cached timeline; rebuilt on next read
                    self.cache.insert(follower, post.id)
                    writes += 1
        self.stats.timeline_writes += writes
        self.stats.posts += 1
        self.stats.per_post.append(writes)
        return writes

    def on_follow(self, follower: str, followee: str, backfill: int = 20) -> None:
        if self.cache.has(follower) and not self.is_pull_author(followee):
            for pid in self.posts.recent_by_author(followee, None, backfill):
                self.cache.insert(follower, pid)

    # --- read path --------------------------------------------------------------------------------------------
    def _pull_sources(self, user: str, rebuild: bool) -> list[str]:
        following = self.graph.following(user)
        if rebuild or self.strategy is Strategy.READ:
            return sorted(following | {user})
        return sorted(a for a in following if self.is_pull_author(a))

    def _rebuild(self, user: str) -> int:
        """Cold start: materialise the pushed part of the timeline from followees' recent posts."""
        self.cache.ensure(user)
        sources = 0
        for author in self.graph.following(user) | {user}:
            if not self.is_pull_author(author) or author == user:
                for pid in self.posts.recent_by_author(author, None, 50):
                    self.cache.insert(user, pid)
                sources += 1
        return sources

    def chronological(self, user: str, cursor: str | None, limit: int = 20) -> FeedPage:
        before = decode_cursor(cursor)
        rebuilt = False
        sources = 0
        candidates: list[int] = []
        if self.strategy is not Strategy.READ:
            if not self.cache.has(user):
                sources += self._rebuild(user)
                rebuilt = True
            candidates += self.cache.page(user, before, limit * 2)  # over-fetch: some entries may be filtered
            sources += 1
        for author in self._pull_sources(user, rebuild=False):
            candidates += self.posts.recent_by_author(author, before, limit)
            sources += 1
        visible = self._filter(user, sorted(set(candidates), reverse=True))
        page = visible[:limit]
        next_cursor = encode_cursor(page[-1].id) if len(page) == limit else None
        return FeedPage(page, next_cursor, sources, rebuilt)

    def _filter(self, user: str, ids: Iterable[int]) -> list[Post]:
        allowed = self.graph.following(user) | {user}
        return [
            p
            for p in self.posts.get_many(list(ids))
            if p.author in allowed and not self.graph.is_blocked(user, p.author)
        ]

    def ranked(self, user: str, now_ms: int, limit: int = 20, window: int = 200) -> list[Post]:
        """Rank a recent candidate window by recency, engagement and affinity (a stand-in for an ML ranker)."""
        candidates = self.chronological(user, None, window).posts
        return sorted(candidates, key=lambda p: score(p, user, now_ms, self.graph), reverse=True)[:limit]


def score(post: Post, viewer: str, now_ms: int, graph: FollowGraph) -> float:
    age_h = max(0.0, (now_ms - timestamp_ms(post.id)) / 3_600_000)
    engagement = math.log1p(len(post.likes) + 2 * len(post.comments))
    mutual = 1.0 if viewer in graph.following(post.author) else 0.0  # the author follows the viewer back
    affinity = 1.0 + 0.5 * mutual
    return (1.0 + engagement) * affinity / math.pow(age_h + 2, 1.5)
