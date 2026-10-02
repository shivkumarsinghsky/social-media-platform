"""Posts, likes and comments. Posts are immutable apart from soft deletion and moderation state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from social.ids import IdGenerator, timestamp_ms


class Visibility(str, Enum):
    VISIBLE = "visible"
    HIDDEN = "hidden"  # moderation
    DELETED = "deleted"


@dataclass
class Post:
    id: int
    author: str
    text: str
    media_keys: list[str] = field(default_factory=list)
    visibility: Visibility = Visibility.VISIBLE
    likes: set[str] = field(default_factory=set)
    comments: list[Comment] = field(default_factory=list)

    @property
    def created_ms(self) -> int:
        return timestamp_ms(self.id)

    @property
    def visible(self) -> bool:
        return self.visibility is Visibility.VISIBLE


@dataclass(frozen=True)
class Comment:
    id: int
    author: str
    text: str


class PostStore:
    """Primary store, keyed by id. Production: sharded by post id; author's posts indexed by (author, id)."""

    def __init__(self, ids: IdGenerator) -> None:
        self._ids = ids
        self._posts: dict[int, Post] = {}
        self._by_author: dict[str, list[int]] = {}

    def create(self, author: str, text: str, media_keys: list[str] | None = None) -> Post:
        post = Post(self._ids.next_id(), author, text, list(media_keys or []))
        self._posts[post.id] = post
        self._by_author.setdefault(author, []).append(post.id)  # ids are increasing → list stays sorted
        return post

    def get(self, post_id: int) -> Post:
        post = self._posts.get(post_id)
        if post is None or post.visibility is Visibility.DELETED:
            raise LookupError("post not found")
        return post

    def get_many(self, ids: list[int]) -> list[Post]:
        return [p for i in ids if (p := self._posts.get(i)) is not None and p.visible]

    def recent_by_author(self, author: str, before: int | None, limit: int) -> list[int]:
        """Newest-first ids by one author, strictly older than `before`."""
        out: list[int] = []
        for pid in reversed(self._by_author.get(author, [])):
            if before is not None and pid >= before:
                continue
            if self._posts[pid].visible:
                out.append(pid)
                if len(out) == limit:
                    break
        return out

    def like(self, post_id: int, user: str) -> bool:
        post = self.get(post_id)
        if user in post.likes:
            return False
        post.likes.add(user)
        return True

    def unlike(self, post_id: int, user: str) -> bool:
        post = self.get(post_id)
        if user not in post.likes:
            return False
        post.likes.discard(user)
        return True

    def comment(self, post_id: int, author: str, text: str) -> Comment:
        post = self.get(post_id)
        c = Comment(self._ids.next_id(), author, text)
        post.comments.append(c)
        return c

    def delete(self, post_id: int, user: str) -> None:
        post = self.get(post_id)
        if post.author != user:
            raise PermissionError("only the author can delete a post")
        post.visibility = Visibility.DELETED
