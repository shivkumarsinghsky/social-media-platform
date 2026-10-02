# ADR-002: Time-Ordered 64-bit Ids and Cursor Pagination

- **Status:** Accepted
- **Date:** 2026-10-02

## Context

Feeds merge posts from several sources and paginate while new posts keep arriving. Offsets shift when items are
inserted; database sequences need coordination across shards.

## Decision

Generate Snowflake-style ids (`timestamp | worker | sequence`) on each node; order and merge by id; paginate with an
opaque, versioned cursor containing the last id (`before`).

## Alternatives Considered

- **UUIDv4** — no coordination, not sortable.
- **UUIDv7 / ULID** — sortable and standard; 128-bit (larger indexes). A good alternative.
- **Offset pagination** — duplicates and gaps under concurrent inserts.

## Trade-offs

Depends on reasonably synchronised clocks (the generator never goes backwards); ids leak creation time; 64-bit ids
must be strings in JSON.

## Consequences

Tests cover monotonicity under clock skew and stable pagination while new posts are created.
