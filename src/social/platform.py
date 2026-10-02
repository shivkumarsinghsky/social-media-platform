"""Wires the services together through domain events (synchronously in the prototype)."""

from __future__ import annotations

from social.events import Bus, Commented, Event, Followed, PostCreated, PostLiked
from social.graph import FollowGraph
from social.ids import IdGenerator
from social.moderation import Moderator
from social.notifications import NotificationService
from social.posts import Comment, Post, PostStore
from social.timeline import FeedService, Strategy, TimelineCache


class ModerationError(ValueError):
    pass


class SocialPlatform:
    def __init__(self, strategy: Strategy = Strategy.HYBRID, celebrity_threshold: int = 10_000, worker_id: int = 1):
        self.bus = Bus()
        self.graph = FollowGraph()
        self.posts = PostStore(IdGenerator(worker_id))
        self.cache = TimelineCache()
        self.feed = FeedService(self.graph, self.posts, self.cache, strategy, celebrity_threshold)
        self.notifications = NotificationService()
        self.moderator = Moderator()
        self.bus.subscribe(PostCreated, self._fan_out)
        self.bus.subscribe(PostCreated, self._notify)
        self.bus.subscribe(PostLiked, self._notify)
        self.bus.subscribe(Commented, self._notify)
        self.bus.subscribe(Followed, self._notify)
        self.bus.subscribe(Followed, self._backfill)

    # --- commands ---------------------------------------------------------------------------------------------
    def register(self, user: str) -> None:
        self.cache.ensure(user)  # active users get a cached timeline

    def follow(self, follower: str, followee: str) -> bool:
        created = self.graph.follow(follower, followee)
        if created:
            self.bus.publish(Followed(follower, followee))
        return created

    def post(self, author: str, text: str, media_keys: list[str] | None = None) -> Post:
        if not self.moderator.check_text(text):
            raise ModerationError("post rejected by content policy")
        post = self.posts.create(author, text, media_keys)
        self.bus.publish(PostCreated(post.id, author, text))
        return post

    def like(self, post_id: int, user: str) -> int:
        post = self.posts.get(post_id)
        if self.graph.is_blocked(post.author, user):
            raise PermissionError("blocked")
        if self.posts.like(post_id, user):
            self.bus.publish(PostLiked(post_id, post.author, user))
        return len(post.likes)

    def comment(self, post_id: int, user: str, text: str) -> Comment:
        post = self.posts.get(post_id)
        if self.graph.is_blocked(post.author, user):
            raise PermissionError("blocked")
        if not self.moderator.check_text(text):
            raise ModerationError("comment rejected by content policy")
        c = self.posts.comment(post_id, user, text)
        self.bus.publish(Commented(post_id, post.author, user, text))
        return c

    # --- event handlers ---------------------------------------------------------------------------------------
    def _fan_out(self, e: Event) -> None:
        assert isinstance(e, PostCreated)
        self.feed.fan_out(self.posts.get(e.post_id))

    def _backfill(self, e: Event) -> None:
        assert isinstance(e, Followed)
        self.feed.on_follow(e.follower, e.followee)

    def _notify(self, e: Event) -> None:
        n = self.notifications
        if isinstance(e, PostCreated):
            for user in n.mentions(e.text):
                n.notify(user, "mention", e.author, e.post_id)
        elif isinstance(e, PostLiked):
            n.notify(e.author, "like", e.user, e.post_id)
        elif isinstance(e, Commented):
            n.notify(e.author, "comment", e.user, e.post_id)
            for user in n.mentions(e.text) - {e.author}:
                n.notify(user, "mention", e.user, e.post_id)
        elif isinstance(e, Followed):
            n.notify(e.followee, "follow", e.follower)
