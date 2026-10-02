"""Moderation: pre-publication checks and report-driven hiding pending human review."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from social.posts import Post, Visibility


@dataclass
class Moderator:
    blocked_terms: frozenset[str] = frozenset({"spamlink.example"})
    report_threshold: int = 3
    review_queue: list[int] = field(default_factory=list)
    _reports: dict[int, set[str]] = field(default_factory=dict)

    def check_text(self, text: str) -> bool:
        """True if the text may be published. Production: ML classifiers plus rules, run asynchronously too."""
        words = set(re.findall(r"[\w.]+", text.lower()))
        return not (words & self.blocked_terms)

    def report(self, post: Post, reporter: str) -> bool:
        """Record a report; hide the post when enough distinct users report it. Returns True if newly hidden."""
        if reporter == post.author:
            raise ValueError("cannot report your own post")
        reporters = self._reports.setdefault(post.id, set())
        reporters.add(reporter)
        if len(reporters) >= self.report_threshold and post.visibility is Visibility.VISIBLE:
            post.visibility = Visibility.HIDDEN
            self.review_queue.append(post.id)
            return True
        return False
