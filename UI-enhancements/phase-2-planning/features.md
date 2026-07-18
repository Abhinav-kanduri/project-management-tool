# Features — Phase 2

## Scope

Database-backed table/card views and detail drawer.

## Actions

- Create, edit, draft/save/save-close, duplicate, archive, restore.
- Assign release, generate stories, view criteria/dependencies/tests/defects/activity.
- Feature archive reports dependent story count and requires an explicit strategy.

## Acceptance

- Optimistic locking rejects stale versions with HTTP 409.
- All feature queries include product-space and project constraints.
