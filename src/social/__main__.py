"""Run the prototype API: python -m social [--port 8000] [--strategy hybrid] [--threshold 10000]"""

from __future__ import annotations

import argparse

import uvicorn

from social.api import create_app
from social.platform import SocialPlatform
from social.timeline import Strategy


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--strategy", choices=[s.value for s in Strategy], default="hybrid")
    p.add_argument("--threshold", type=int, default=10_000)
    args = p.parse_args()
    platform = SocialPlatform(Strategy(args.strategy), args.threshold)
    uvicorn.run(create_app(platform), host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
