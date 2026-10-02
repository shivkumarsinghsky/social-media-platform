# ADR-004: Layered Moderation (Pre-Publication Checks, Reports, Human Review)

- **Status:** Accepted
- **Date:** 2026-10-02

## Context

Harmful content must be limited quickly, but heavy analysis cannot block every post, and automated systems make
mistakes.

## Decision

Cheap synchronous checks before publication; asynchronous analysis after publication; distinct-user reports above a
threshold hide content pending human review; feeds filter hidden content at read time.

## Alternatives Considered

- **Manual review before publication** — does not scale; adds latency.
- **Post-hoc only** — harmful content spreads before removal.

## Trade-offs

False positives (appeals needed); report thresholds can be gamed (weight reporters by reputation).

## Consequences

The prototype implements term-based pre-checks, report thresholds with a review queue, and read-time filtering.
