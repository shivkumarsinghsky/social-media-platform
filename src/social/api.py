"""HTTP API of the prototype. `X-User` stands in for the subject of a verified access token.

Post ids are 64-bit integers and are returned as strings so JavaScript clients do not lose precision.
"""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from social.platform import ModerationError, SocialPlatform
from social.posts import Post
from social.timeline import Strategy

User = Annotated[str, Header(alias="X-User", pattern=r"^[a-z0-9_]{1,30}$")]


class NewPost(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    media_keys: list[str] = Field(default_factory=list, max_length=4)


class NewComment(BaseModel):
    text: str = Field(min_length=1, max_length=500)


def out(p: Post) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "author": p.author,
        "text": p.text,
        "mediaKeys": p.media_keys,
        "likes": len(p.likes),
        "comments": len(p.comments),
        "createdMs": p.created_ms,
    }


def create_app(platform: SocialPlatform | None = None) -> FastAPI:
    sp = platform or SocialPlatform(Strategy.HYBRID, celebrity_threshold=10_000)
    app = FastAPI(title="Social Media Platform — reference prototype", version="1.0.0")

    def pid(post_id: str) -> int:
        if not post_id.isdigit():
            raise HTTPException(404, "post not found")
        return int(post_id)

    def guard(fn: Any, *args: Any) -> Any:
        try:
            return fn(*args)
        except LookupError as e:
            raise HTTPException(404, str(e)) from e
        except PermissionError as e:
            raise HTTPException(403, str(e)) from e
        except ModerationError as e:
            raise HTTPException(422, str(e)) from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.put("/v1/users/{target}/follow")
    def follow(target: str, user: User) -> dict[str, bool]:
        sp.register(user)
        return {"created": guard(sp.follow, user, target)}

    @app.delete("/v1/users/{target}/follow")
    def unfollow(target: str, user: User) -> dict[str, bool]:
        return {"removed": sp.graph.unfollow(user, target)}

    @app.put("/v1/users/{target}/block", status_code=204)
    def block(target: str, user: User) -> None:
        sp.graph.block(user, target)

    @app.get("/v1/users/{target}")
    def profile(target: str) -> dict[str, Any]:
        return {
            "user": target,
            "followers": sp.graph.follower_count(target),
            "following": len(sp.graph.following(target)),
            "pulledAtReadTime": sp.feed.is_pull_author(target),
        }

    @app.get("/v1/users/{target}/posts")
    def user_posts(target: str, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[dict[str, Any]]:
        return [out(p) for p in sp.posts.get_many(sp.posts.recent_by_author(target, None, limit))]

    @app.post("/v1/posts", status_code=201)
    def create_post(body: NewPost, user: User) -> dict[str, Any]:
        sp.register(user)
        return out(guard(sp.post, user, body.text, body.media_keys))

    @app.get("/v1/posts/{post_id}")
    def get_post(post_id: str) -> dict[str, Any]:
        post = guard(sp.posts.get, pid(post_id))
        if not post.visible:
            raise HTTPException(404, "post not found")
        return out(post)

    @app.delete("/v1/posts/{post_id}", status_code=204)
    def delete_post(post_id: str, user: User) -> None:
        guard(sp.posts.delete, pid(post_id), user)

    @app.put("/v1/posts/{post_id}/like")
    def like(post_id: str, user: User) -> dict[str, int]:
        return {"likes": guard(sp.like, pid(post_id), user)}

    @app.delete("/v1/posts/{post_id}/like")
    def unlike(post_id: str, user: User) -> dict[str, int]:
        guard(sp.posts.unlike, pid(post_id), user)
        return {"likes": len(guard(sp.posts.get, pid(post_id)).likes)}

    @app.post("/v1/posts/{post_id}/comments", status_code=201)
    def comment(post_id: str, body: NewComment, user: User) -> dict[str, str]:
        c = guard(sp.comment, pid(post_id), user, body.text)
        return {"id": str(c.id), "author": c.author, "text": c.text}

    @app.post("/v1/posts/{post_id}/report")
    def report(post_id: str, user: User) -> dict[str, bool]:
        post = guard(sp.posts.get, pid(post_id))
        return {"hidden": guard(sp.moderator.report, post, user)}

    @app.get("/v1/feed")
    def feed(
        user: User,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        mode: Literal["chronological", "ranked"] = "chronological",
    ) -> dict[str, Any]:
        if mode == "ranked":
            return {"items": [out(p) for p in sp.feed.ranked(user, int(time.time() * 1000), limit)], "next": None}
        page = guard(sp.feed.chronological, user, cursor, limit)
        return {"items": [out(p) for p in page.posts], "next": page.next_cursor}

    @app.get("/v1/notifications")
    def notifications(user: User) -> list[dict[str, Any]]:
        return [
            {"kind": n.kind, "postId": str(n.post_id) if n.post_id else None, "text": n.summary(), "read": n.read}
            for n in sp.notifications.list(user)
        ]

    @app.post("/v1/notifications/read", status_code=204)
    def mark_read(user: User) -> None:
        sp.notifications.mark_all_read(user)

    return app
