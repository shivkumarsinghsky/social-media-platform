"""Follow graph with follower counts used to classify high-fan-out accounts."""

from __future__ import annotations

from collections import defaultdict


class FollowGraph:
    def __init__(self) -> None:
        self._followers: dict[str, set[str]] = defaultdict(set)
        self._following: dict[str, set[str]] = defaultdict(set)
        self._blocked: dict[str, set[str]] = defaultdict(set)

    def follow(self, follower: str, followee: str) -> bool:
        if follower == followee:
            raise ValueError("cannot follow yourself")
        if follower in self._blocked[followee]:
            raise PermissionError("blocked")
        if followee in self._following[follower]:
            return False
        self._following[follower].add(followee)
        self._followers[followee].add(follower)
        return True

    def unfollow(self, follower: str, followee: str) -> bool:
        if followee not in self._following[follower]:
            return False
        self._following[follower].discard(followee)
        self._followers[followee].discard(follower)
        return True

    def block(self, user: str, other: str) -> None:
        self._blocked[user].add(other)
        self.unfollow(other, user)
        self.unfollow(user, other)

    def is_blocked(self, user: str, other: str) -> bool:
        return other in self._blocked[user]

    def followers(self, user: str) -> set[str]:
        return set(self._followers[user])

    def following(self, user: str) -> set[str]:
        return set(self._following[user])

    def follower_count(self, user: str) -> int:
        return len(self._followers[user])
