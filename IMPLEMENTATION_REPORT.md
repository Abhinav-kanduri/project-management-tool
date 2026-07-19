# ReleaseLens Implementation Report

## Completed

- FastAPI health, feature-generation, and story-generation endpoints.
- OpenAI Responses API Structured Outputs and document extraction.
- Supabase PostgreSQL organization → product space → project hierarchy.
- Project-agnostic isolation across Customer Experience and Restaurant Operations, with independent sequences, releases, and sprints.
- Transactional AI save, idempotency, activity snapshots, and backlog retrieval.
- Feature/story manual create, edit, optimistic locking, and archive.
- Supabase RLS membership model and removal of anonymous table access.
- Database-driven selectors, project work, project metrics, and product-space Overview.
- Expandable Overview hierarchy rendering Project → Feature → User Story with contextual database-backed work-item actions.
- Working SPA views for Generator, Overview, Backlog, Features, and User Stories.
- Phase specifications under `UI-enhancements/`.
- Mandatory Product Space → Project → Feature → User Story hierarchy enforced by API validation and a database `NOT NULL` constraint.
- PI Release foundation: four calendar PIs per year, idempotent year generation, mandatory feature/story PI mapping, inheritance, and project-scoped validation.
- Feature-to-Story generation now uses complete saved PostgreSQL Feature context (description, business value, requirements, criteria, dependencies, risks, assumptions, priority, status, and PI) rather than browser text/title alone.
- Rich structured Feature and traceable Story response models and database persistence.
- Existing Feature regeneration: database selector, server-side context loading, LLM regeneration, and update-in-place transactional save with duplicate prevention.
- PI-scoped Sprint generation and dropdown filtering; User Story generation combines saved Feature context, optional Sprint, and additional instructions.
- Canonical project planning hierarchy endpoint and UI: PI Release → Feature → Sprint → User Story. Feature selectors filter by the selected PI and each Feature renders exactly once under its database PI.

## Database migrations

- `sql/releaselens.sql`
- `sql/releaselens_security.sql`
- `sql/seed_customer_experience_projects.sql`

## Verification run

- Shared hierarchy bar added to AI Generator, Overview, Backlog, Features, and User Stories with PI → Feature → Sprint → Story cascading controls.
- Selections are stored in `piReleaseId`, `featureId`, `sprintId`, and `userStoryId` URL parameters and survive tab changes, refresh, and browser history navigation.
- Added project-scoped `GET /api/v1/projects/{projectId}/planning-options`; archived and cross-project records are excluded and server-side PI/Feature/Sprint filters are applied.
- `python -m compileall -q app main.py`
- `node --check app/static/app.js`
- Live planning-options API returned 4 PI releases, 1 PI-linked feature, 6 PI-linked sprints, and 4 mapped stories for the seeded Customer Support Bot project.
- FastAPI TestClient health/workspace/overview/backlog checks.
- Cross-project CRUD isolation for CSB, CFA, RSA, and RAK.
- PostgreSQL RLS/grant audit and authenticated isolation check.

## Remaining phases

- Phase 2: persisted ranking/bulk backlog operations, Kanban drag/drop, complete sprint lifecycle, restore/duplicate, acceptance-criteria editor.
- Phase 3: roadmap timeline, release lifecycle/readiness, dependency graph/validation, test-case and defect schemas/APIs/UIs.
- Phase 4: Supabase login/JWT enforcement in FastAPI, administration screens, full audit UI, and browser automation suite.

Navigation for unfinished modules is intentionally intercepted with a roadmap notification rather than presenting dead controls.
