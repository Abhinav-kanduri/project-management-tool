# Impact Analysis backend

Impact Analysis compares Project Management and approved design context (expected
truth) with a source index pinned to an immutable GitHub commit (actual truth).
It is implemented under `app/impact_analysis` and exposed under
`/api/v1/impact-analysis`.

## Setup

1. Apply `sql/tables/00_prerequisites.sql` and the numbered application table
   migrations in order, including `25` through `37`.
2. Apply `sql/impact_analysis_security.sql` after the base ReleaseLens security
   script.
3. Run Neo4j migrations `V007` and `V008` with the existing migration runner.
4. Configure the existing PostgreSQL, GitHub and Neo4j environment variables.

Every Impact Analysis endpoint requires an `X-Actor` header containing the
authenticated Supabase `auth.users.id`. The user must be a member of the
selected Project. The local `local-user` bypass used by older endpoints is
deliberately not accepted.

In production, `X-Actor` is an internal trust-boundary header. Next.js must
derive it from a server-side Supabase session and must discard any browser-
supplied `X-Actor` value. Do not expose FastAPI directly to untrusted clients
unless the ingress strips `X-Actor` and supplies a verified identity. The
Next.js proxy also forwards the session bearer token; it never forwards a
browser-provided bearer token.

### Provision a Project member

Authentication creates the identity in `auth.users`; authorization requires a
matching `project_members` row. After the user has signed up through Supabase
or the selected identity provider, run:

```powershell
.venv\Scripts\python.exe scripts\provision_project_member.py `
  --project-id <selected-project-uuid> `
  --user-id <existing-auth.users-id> `
  --role PROJECT_ADMIN
```

Use `--check-only` first when validating production input. The command:

- refuses a user ID that is absent from `auth.users`;
- refuses a Project ID that is absent from `projects`;
- accepts only known Project roles;
- inserts or updates the one `project_members` association; and
- never creates an Auth user or generates a UUID.

Run it with a database principal allowed to read `auth.users` and manage
`project_members`. A session without membership receives `403`; a missing
Next.js session receives `401`.

For local development only, Next.js may use
`PROJECT_MANAGEMENT_ACTOR_ID=<existing-auth.users-id>`. That UUID still needs
a `project_members` row. Never use a random UUID, configure this fallback in
production, or expose it through a `NEXT_PUBLIC_*` variable.

## GitHub branch refresh and source sync

The repository-summary UI uses a separate read-only branch selector:

- `GET /api/v1/github/repositories/branches?repository_url={url}` returns
  `name`, `commit_sha`, and `protected` for every branch visible to the backend
  GitHub token.
- It does not require `X-Actor` because it does not load Project snapshots,
  write source intelligence, or unlink an association.
- `POST /api/v1/github/summary` accepts `repository_url`, `branch`, and
  `force_refresh` and returns the structured repository, analysis, summary,
  component, endpoint, and artifact DTO used by the frontend tables.

The GitHub Data Source uses the Project-repository association ID rather than a
raw GitHub repository ID. Both operations require the same authorized `X-Actor`:

- `GET /api/v1/github/project-repositories/{project_repository_id}/branches`
  reads every GitHub branch page and returns the current commit, protection
  state, refresh timestamp, and latest completed source-snapshot timestamp.
- `POST /api/v1/github/project-repositories/{project_repository_id}/sync`
  accepts `{"branch":"feature/name","force_refresh":true}` and downloads,
  parses, and indexes that exact branch into the existing repository snapshot,
  file, symbol, edge, and chunk tables.
- `DELETE /api/v1/github/project-repositories/{project_repository_id}` unlinks
  the repository from the Project. It requires a Project Admin, Product Owner,
  or Admin and returns `409 REPOSITORY_LINK_HAS_DEPENDENCIES` when snapshots or
  Impact Analysis runs exist. It never deletes the provider repository or the
  shared GitHub catalog record.

`refreshed_at` means the branch list was read from GitHub. `last_synced_at`
means the selected commit completed source indexing. These timestamps are not
interchangeable. Sync remains server-side; GitHub credentials and repository
archives are never returned to the browser.

## Read-only analysis workflow

`POST /api/v1/impact-analysis/runs` accepts a Feature or User Story scope and a
linked Project repository. A background task then:

1. resolves and authorizes Project context;
2. loads approved architecture/technical-design chunks;
3. creates validated atomic requirements and expected graph nodes;
4. resolves the branch to a commit SHA and indexes source files, symbols, calls,
   dependencies, tests, configuration and SQL objects;
5. synchronizes the actual implementation graph;
6. combines structured-symbol, PostgreSQL full-text and optional injected vector
   retrieval without sending the whole repository to a model;
7. creates bounded evidence packages and classifies each requirement as
   `PRESENT`, `PARTIAL`, `MISSING` or `UNKNOWN`;
8. calculates the score deterministically, excluding `UNKNOWN`; and
9. persists findings, citations and score history.

The default requirement decomposition and comparison are deterministic. Vector
embeddings require an explicitly injected provider; source content is not sent
to an external service by default.

### Read endpoints

- `GET /runs/{run_id}`
- `GET /runs/{run_id}/requirements`
- `GET /runs/{run_id}/findings`
- `GET /findings/{finding_id}`
- `GET /findings/{finding_id}/evidence`
- `GET /runs/{run_id}/graph`
- `GET /history`
- `POST /runs/{run_id}/reanalyze`
- `GET /runs/{run_id}/comparison`

## Approval-gated remediation

Only completed `PARTIAL` or `MISSING` statically verifiable findings can create a
generated-change record. The workflow is:

1. request a change;
2. build repository-aware context from the pinned commit and evidence;
3. generate or explicitly submit a unified diff;
4. enforce path, diff-format, secret and destructive-SQL policy checks;
5. validate in an isolated workspace;
6. obtain an explicit human decision;
7. publish a branch and pull request; and
8. re-run analysis after merge.

Generation, isolated workspace validation and GitHub publication are provider
interfaces. No default provider is installed, so those endpoints return `503`
and no source transfer or GitHub write occurs until a trusted adapter is
configured. Approval remains blocked unless path safety, format, policy, lint,
compile, unit-test and security checks all pass.

### Remediation endpoints

- `POST /findings/{finding_id}/generated-changes`
- `GET /generated-changes/{change_id}`
- `GET /generated-changes/{change_id}/context`
- `POST /generated-changes/{change_id}/generate`
- `PUT /generated-changes/{change_id}/proposal`
- `POST /generated-changes/{change_id}/validate`
- `POST /generated-changes/{change_id}/approve`
- `POST /generated-changes/{change_id}/pull-request`

## Verification

Run:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m compileall -q app tests\impact_analysis
```
