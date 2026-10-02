# ADR-001: Hybrid Fan-Out for the Home Feed

- **Status:** Accepted
- **Date:** 2026-10-02

## Context

Feed reads dominate traffic, so reads must be cheap. Follower counts are power-law distributed: pushing every post
to every follower makes posts by very popular accounts cost millions of writes, while pulling for every read makes
each read touch hundreds of sources.

## Decision

Fan-out on write for authors below a follower threshold; fan-out on read for authors above it. The feed service
merges the reader's cached timeline with recent posts of the followed high-follower authors. Fan-out skips users
without a cached timeline (inactive); their timeline is rebuilt on the next read.

## Alternatives Considered

- **Pure fan-out on write** — fastest reads; write storms and delays for celebrity posts.
- **Pure fan-out on read** — no write amplification; read cost too high at scale.
- **Push to active followers only** for celebrities — reduces writes but still large for top accounts.

## Trade-offs

Two read paths to merge; a threshold to tune; posts by accounts crossing the threshold may appear from both paths
(de-duplicated by id).

## Consequences

The prototype implements all three strategies behind one interface; tests check they return identical feeds, and a
simulation quantifies write amplification vs. read cost.
