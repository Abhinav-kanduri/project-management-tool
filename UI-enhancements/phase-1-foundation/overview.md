# Overview Tab — Phase 1

## Scope

Display database-derived product-space and project summaries. Switching product space filters projects; switching project refreshes every project-scoped panel.

## Backend

- `GET /api/v1/product-spaces/{id}/overview`
- Return projects, feature/story counts, status totals, current release/sprint, owner, health, and recent activity.
- Enforce product-space ownership in every join.

## UI

- Product-space metric cards and expandable project cards.
- Expanded cards visibly render `Project → Feature → User Story`; stories never render outside their parent feature.
- Feature rows expose add-story, edit, and archive actions; project rows expose open, expand/collapse, and add-feature actions.
- Actions: open project, add feature, add story.
- Loading, empty, and error states; no hard-coded counters.

## Acceptance

- Data survives refresh and never crosses project boundaries.
- Opening a project updates selectors and all project-scoped views.
- Overview story totals equal the number of nested database stories.
