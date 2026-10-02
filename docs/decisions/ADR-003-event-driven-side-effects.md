# ADR-003: Event-Driven Side Effects (Fan-Out, Notifications, Indexing)

- **Status:** Accepted
- **Date:** 2026-10-02

## Context

Creating a post triggers fan-out, notifications, indexing, moderation and analytics. Doing these synchronously makes
the write path slow and fragile.

## Decision

The post, engagement and graph services persist their change and publish domain events (via an outbox, see
[event-driven-platform](https://github.com/shivkumarsinghsky/event-driven-platform)). Independent consumer groups
handle each side effect idempotently.

## Alternatives Considered

- **Synchronous calls** — simpler, couples latency and availability.
- **Database triggers / CDC only** — decoupled, but events lose domain meaning.

## Trade-offs

Eventual consistency (followers see posts after a delay); operating an event log; consumer lag monitoring.

## Consequences

The prototype uses an in-process bus with the same event types; handlers are idempotent (timeline inserts are
set-like, like notifications aggregate by actor).
