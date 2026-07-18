# Activity and Audit — Phase 4

## Scope

Immutable activity records for create/update/status/assignment/archive/restore/delete/AI/board/sprint events.

## UI

Filter by project, entity, actor, action, and date; display previous/new values.

## Acceptance

- Every successful mutation creates one activity event in the same transaction.
- Failed/rolled-back mutations create none.
