# AI Generator — Phase 1

## Scope

Generate a feature or a requested number of stories from text/PDF/DOCX/TXT/MD for the selected project.

## Backend

- Existing `/feature/generation` and `/userstories/generation` use Structured Outputs.
- Save raw generation to `ai_generations`.
- Bulk save through `/api/v1/projects/{id}/generated-work-items` in one transaction.
- Idempotency key prevents duplicate saves.

## UI

- Select product space, project, release, sprint, and parent feature where required.
- Story generation loads the complete selected Feature context from PostgreSQL through `/api/v1/features/{id}/generation-context`; browser text is not trusted as the generation source.
- Editable preview; save draft or backlog; visible provider errors.
- Feature mode can select an existing saved Feature, load its complete PostgreSQL context, regenerate it, and update the same Feature record and criteria transactionally without creating a duplicate.

## Acceptance

- Exact requested story count.
- Generated items receive project-scoped keys and immediately refresh project work.
