"""Compare fan-out strategies on a synthetic power-law follow graph.

    python -m social.simulation [--users 5000] [--threshold 500] [--seed 7]

Reports write amplification (timeline writes per post) and read cost (sources touched per feed request). The
graph is synthetic; absolute numbers are illustrative, the shape of the trade-off is the point.
"""

from __future__ import annotations

import argparse
import random
import statistics
from dataclasses import dataclass

from social.platform import SocialPlatform
from social.timeline import Strategy


@dataclass(frozen=True)
class Result:
    strategy: Strategy
    writes_per_post_avg: float
    writes_per_post_max: int
    sources_per_read_avg: float
    sources_per_read_max: int


def build(strategy: Strategy, users: int, threshold: int, seed: int, posts: int, reads: int) -> Result:
    rng = random.Random(seed)
    p = SocialPlatform(strategy, celebrity_threshold=threshold)
    names = [f"u{i}" for i in range(users)]
    for u in names:
        p.register(u)
    # Preferential attachment-like popularity: a few accounts get most followers.
    weights = [1 / (i + 1) ** 1.1 for i in range(users)]
    for u in names:
        for followee in set(rng.choices(names, weights=weights, k=rng.randint(5, 60))):
            if followee != u:
                p.graph.follow(u, followee)  # bypass events: no backfill noise while building the graph
    authors = rng.choices(names, weights=weights, k=posts)  # popular accounts also post more
    for a in authors:
        p.post(a, "hello")
    readers = rng.sample(names, k=min(reads, users))
    sources = [p.feed.chronological(r, None, 20).sources_read for r in readers]
    per_post = p.feed.stats.per_post
    return Result(strategy, statistics.mean(per_post), max(per_post), statistics.mean(sources), max(sources))


def run(users: int = 5000, threshold: int = 500, seed: int = 7, posts: int = 2000, reads: int = 500) -> list[Result]:
    return [build(s, users, threshold, seed, posts, reads) for s in Strategy]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--users", type=int, default=5000)
    ap.add_argument("--threshold", type=int, default=500, help="follower count at which an author is pulled")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    print(f"{'strategy':<8} {'writes/post avg':>16} {'max':>6} {'sources/read avg':>17} {'max':>5}")
    for r in run(args.users, args.threshold, args.seed):
        print(
            f"{r.strategy.value:<8} {r.writes_per_post_avg:>16.1f} {r.writes_per_post_max:>6} "
            f"{r.sources_per_read_avg:>17.1f} {r.sources_per_read_max:>5}"
        )


if __name__ == "__main__":
    main()
