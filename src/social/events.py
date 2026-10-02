"""Domain events and an in-process bus. Production: a partitioned log (Kafka-style) with async consumers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class PostCreated:
    post_id: int
    author: str
    text: str


@dataclass(frozen=True)
class PostLiked:
    post_id: int
    author: str
    user: str


@dataclass(frozen=True)
class Commented:
    post_id: int
    author: str
    user: str
    text: str


@dataclass(frozen=True)
class Followed:
    follower: str
    followee: str


Event = PostCreated | PostLiked | Commented | Followed
Handler = Callable[[Event], None]


class Bus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: Event) -> None:
        for handler in self._handlers[type(event)]:
            handler(event)
