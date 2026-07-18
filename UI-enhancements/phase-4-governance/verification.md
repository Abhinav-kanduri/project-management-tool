# Verification and Release Gate — Phase 4

## Automated checks

- API tests for CRUD, archive/restore, optimistic locking, hierarchy, and cross-project isolation.
- Browser tests for navigation, persistence after refresh, generator save, backlog, board, sprint, release, test, and defect flows.
- Python compilation, dependency check, JavaScript syntax check, schema migration test.

## Completion gate

No dead visible actions, hard-coded metrics, cross-tenant leakage, local-only product data, failed tests, or undocumented limitations.
