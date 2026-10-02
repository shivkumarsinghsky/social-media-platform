"""Notifications with aggregation ("alice and 2 others liked your post") and @mentions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MENTION = re.compile(r"(?<![\w@])@([a-z0-9_]{1,30})")


@dataclass
class Notification:
    recipient: str
    kind: str  # like | comment | follow | mention
    post_id: int | None
    actors: list[str] = field(default_factory=list)
    read: bool = False

    def summary(self) -> str:
        first, others = self.actors[-1], len(self.actors) - 1
        who = first if others == 0 else f"{first} and {others} other{'s' if others > 1 else ''}"
        verb = {
            "like": "liked your post",
            "comment": "commented on your post",
            "follow": "followed you",
            "mention": "mentioned you",
        }[self.kind]
        return f"{who} {verb}"


class NotificationService:
    def __init__(self) -> None:
        self._items: dict[str, list[Notification]] = {}
        self.push_outbox: list[tuple[str, str]] = []  # (recipient, text) — production: push service via queue

    def notify(self, recipient: str, kind: str, actor: str, post_id: int | None = None) -> Notification | None:
        if recipient == actor:
            return None
        items = self._items.setdefault(recipient, [])
        for n in items:  # aggregate into an unread notification for the same target
            if not n.read and n.kind == kind and n.post_id == post_id and kind in ("like", "follow"):
                if actor not in n.actors:
                    n.actors.append(actor)
                return n
        n = Notification(recipient, kind, post_id, [actor])
        items.append(n)
        if kind in ("comment", "mention"):
            self.push_outbox.append((recipient, n.summary()))
        return n

    def mentions(self, text: str) -> set[str]:
        return set(MENTION.findall(text))

    def list(self, user: str) -> list[Notification]:
        return list(reversed(self._items.get(user, [])))

    def mark_all_read(self, user: str) -> None:
        for n in self._items.get(user, []):
            n.read = True
