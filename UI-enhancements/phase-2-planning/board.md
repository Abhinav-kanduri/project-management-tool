# Board — Phase 2

## Scope

Kanban columns: Backlog, Ready, In Progress, Code Review, Testing, Blocked, Done.

## Behavior

- Cards are real user stories scoped to the selected project/sprint.
- Drag updates status and rank transactionally, logs activity, and rolls back UI on failure.
- Quick edit, open, assign, archive.

## Acceptance

- Refresh retains card status/order.
- Board, backlog, and overview counts remain consistent.
