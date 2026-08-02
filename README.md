# ReleaseLens Backend

ReleaseLens is a FastAPI and PostgreSQL application for organizing product-planning work and generating Features and User Stories with OpenAI.

## GitHub repository summary, artifacts, and semantic search

ReleaseLens includes `POST /api/v1/github/summary` plus Markdown download, chunk inspection, and pgvector semantic-search APIs. The end-to-end architecture, backend-only PAT placement, environment variables, PostgreSQL migration, Docker commands, PowerShell/cURL examples, artifact paths, cache and force-refresh behavior, troubleshooting, and test commands are documented in [docs/github-summary-indexing.md](docs/github-summary-indexing.md).

The workspace sidebar also lists repositories available to the backend GitHub PAT and lets a user link a repository by its stable GitHub ID to the selected Product Space and Project. Repository metadata is re-fetched server-side before it is stored.

For local Docker startup, copy `.env.example` to `.env`, set `GITHUB_TOKEN` and `OPENAI_API_KEY` only in that backend file, then run `docker compose up --build`. Swagger is served at `http://127.0.0.1:8001/docs`.

The application hierarchy is:

```text
Organization
└── Product Space
    └── Project
        ├── PI Releases
        ├── Sprints
        ├── Features
        │   ├── Feature Acceptance Criteria
        │   └── User Stories
        │       └── Story Acceptance Criteria
        └── AI generations, sequences, members, and activity logs
```

## Running the application

Requirements:

- Python 3.11 or newer
- PostgreSQL/Supabase database initialized with the files in `sql/`
- OpenAI API key

Create `.env` from `.env.example`, install dependencies, and start FastAPI:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The default local URLs are:

- Application: `http://127.0.0.1:8000/`
- OpenAPI/Swagger: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Health check: `http://127.0.0.1:8000/health`

### Optional Neo4j + LangChain graph RAG

The easiest local setup uses the included Neo4j Community Docker Compose service:

```powershell
python infra/neo4j/scripts/generate_env.py
python -m pip install -r requirements.txt
docker compose --env-file infra/neo4j/.env -f infra/neo4j/compose.yaml up -d
python infra/neo4j/scripts/wait_for_neo4j.py
python infra/neo4j/scripts/neo4j_migrate.py
python infra/neo4j/scripts/neo4j_verify.py
```

FastAPI exposes graph health, LangChain schema, and vector-search routes under
`/api/v1/graph`. See [Neo4j local development](docs/neo4j-local-development.md)
for connections, migrations, VS Code tasks, persistence, and troubleshooting.

## Configuration

| Variable | Required | Purpose |
|---|---:|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string. |
| `OPENAI_API_KEY` | Yes | OpenAI credential used by generation endpoints. |
| `OPENAI_CHAT_MODEL` | No | Generation model; defaults to `gpt-5-mini`. |
| `APP_ENV` | No | Environment name; defaults to `development`. |
| `ENABLE_APPLICATION_DATA_RESET` | No | Must equal `true` before the reset API is available. |
| `ADMIN_RESET_TOKEN` | For reset | Secret supplied through `X-Admin-Token`. Never put it in frontend code. |
| `NEO4J_URI` | For graph RAG | Bolt URI; defaults to `neo4j://localhost:7687`. |
| `NEO4J_USERNAME` | For graph RAG | Defaults to `neo4j`. |
| `NEO4J_PASSWORD` | For graph RAG | Loaded automatically from the ignored `infra/neo4j/.env`. |
| `NEO4J_DATABASE` | No | Defaults to `neo4j`. |

## API conventions

- Workspace and deletion APIs use the `/api/v1` prefix.
- AI generation APIs currently use their original unversioned paths.
- IDs are UUID values unless stated otherwise.
- JSON endpoints use `Content-Type: application/json`.
- Generation endpoints use `multipart/form-data`.
- Archived records have `archived_at` set and are hidden from normal lists.
- Permanent deletion removes rows and cannot be restored.
- Every cascade deletion is executed in one database transaction.

## Chat persistence schema

The database includes the application-owned tables needed for persistent, project-scoped conversations:

| Table | Purpose |
|---|---|
| `chat_sessions` | Conversation identity, owner, Project scope, resolved context, summary, and message counters. The session UUID is intended to become the LangGraph `thread_id`. |
| `chat_messages` | Ordered USER, ASSISTANT, SYSTEM, and TOOL messages with optional browser idempotency IDs and token/latency metadata. |
| `chat_message_intents` | One classified intent and resolved/search context for each User message. |
| `chat_retrieval_events` | Structured, vector, or hybrid retrieval evidence and timing. |
| `chat_runs` | Per-turn graph execution status, node, error, and timing information. |

The schema is defined in `sql/chat_conversation_schema.sql`. All five tables use Project-derived row-level security and cascade from `chat_sessions`; sessions cascade from their Project.

This is currently persistence infrastructure only. Chat HTTP endpoints and LangGraph checkpoint tables have not yet been implemented. Checkpoint tables must be created by the installed LangGraph PostgreSQL checkpointer through a controlled setup command; their names are deliberately not guessed in this migration.

## Chat API contract and initial implementation

> **Availability:** The JSON conversation create/list/history/message, convenience Chat, and permanent-delete routes are now registered in FastAPI. They provide persistent Project-scoped turns, structured database grounding, OpenAI answers, intents, and sources. SSE streaming, metadata update, archive, and LangGraph checkpoint orchestration remain planned.

Base path:

```text
/api/v1/chat
```

The conversation `session_id` will also be used as the LangGraph `thread_id`. Reuse the same `session_id` to continue a conversation.

### Chat endpoint summary

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/chat/conversations` | Create a persistent Project-scoped conversation. |
| `GET` | `/api/v1/chat/conversations` | List conversations for an actor and Project. |
| `GET` | `/api/v1/chat/conversations/{session_id}` | Get conversation metadata and resolved context. |
| `PATCH` | `/api/v1/chat/conversations/{session_id}` | Rename or update a conversation. |
| `POST` | `/api/v1/chat/conversations/{session_id}/archive` | Archive a conversation without deleting messages. |
| `DELETE` | `/api/v1/chat/conversations/{session_id}` | Permanently delete a conversation and its chat records. |
| `GET` | `/api/v1/chat/conversations/{session_id}/messages` | Get persisted message history. |
| `POST` | `/api/v1/chat/conversations/{session_id}/messages` | Send a message and receive one JSON response. |
| `POST` | `/api/v1/chat/conversations/{session_id}/messages/stream` | Send a message and receive Server-Sent Events. |
| `POST` | `/api/v1/chat` | Convenience endpoint that creates or continues a conversation. |

All routes are intended to accept an `X-Actor` header. During local development its value may be `local-user`. Production identity must come from a server-verified authentication token.

### Create a conversation

```http
POST /api/v1/chat/conversations
Content-Type: application/json
X-Actor: local-user
```

```json
{
  "product_space_id": "<product-space-uuid>",
  "project_id": "<project-uuid>",
  "release_id": null,
  "feature_id": null,
  "sprint_id": null,
  "user_story_id": null,
  "title": null,
  "metadata": {}
}
```

`product_space_id` and `project_id` are required. Optional hierarchy IDs must belong to the same Project.

Planned response:

```json
{
  "session_id": "<session-uuid>",
  "thread_id": "<same-session-uuid>",
  "title": "New conversation",
  "status": "ACTIVE",
  "project": {
    "id": "<project-uuid>",
    "name": "Customer Support Assistant"
  },
  "resolved_context": {
    "release_id": null,
    "feature_id": null,
    "sprint_id": null,
    "user_story_id": null
  },
  "created_at": "2026-07-18T20:00:00Z"
}
```

Store `session_id` in the client. It is required to continue the same conversation.

### Send a message

```http
POST /api/v1/chat/conversations/{session_id}/messages
Content-Type: application/json
X-Actor: local-user
```

```json
{
  "message": "Show Feature CSA-BOT-F-001.",
  "client_message_id": "msg-001",
  "context": {
    "release_id": null,
    "feature_id": null,
    "sprint_id": null,
    "user_story_id": null
  },
  "response_mode": "NORMAL"
}
```

`client_message_id` should be a browser-generated unique value. Reusing it with the same content prevents duplicate model execution during retries. Reusing it with different content should return `409 DUPLICATE_MESSAGE_CONFLICT`.

Planned response:

```json
{
  "session_id": "<session-uuid>",
  "thread_id": "<same-session-uuid>",
  "run_id": "<run-uuid>",
  "user_message_id": "<message-uuid>",
  "assistant_message_id": "<message-uuid>",
  "answer": "CSA-BOT-F-001 is the Chat Orchestrator Feature.",
  "intent": {
    "name": "FEATURE_LOOKUP",
    "confidence": 0.98,
    "previous_intent": null
  },
  "resolved_context": {
    "release_id": "<release-uuid>",
    "release_name": "2026 PI 1",
    "feature_id": "<feature-uuid>",
    "feature_key": "CSA-BOT-F-001",
    "sprint_id": null,
    "user_story_id": null
  },
  "sources": [
    {
      "source_type": "FEATURE",
      "source_id": "<feature-uuid>",
      "source_key": "CSA-BOT-F-001",
      "title": "Chat Orchestrator",
      "snippet": "End-to-end message processing pipeline",
      "score": 1.0,
      "metadata": {
        "status": "DRAFT",
        "release": "2026 PI 1"
      }
    }
  ],
  "search": {
    "retrieval_type": "STRUCTURED",
    "result_count": 1,
    "latency_ms": 24
  },
  "usage": {
    "prompt_tokens": 500,
    "completion_tokens": 120,
    "total_tokens": 620
  }
}
```

### Continue the conversation

Use the same `session_id` with a new `client_message_id`:

```json
{
  "message": "What User Stories are under it?",
  "client_message_id": "msg-002",
  "context": {},
  "response_mode": "NORMAL"
}
```

The persisted context should resolve “it” to `CSA-BOT-F-001`. A different `session_id` starts isolated conversation state.

### Stream a response

```http
POST /api/v1/chat/conversations/{session_id}/messages/stream
Accept: text/event-stream
Content-Type: application/json
X-Actor: local-user
```

The request body is the same as the normal message endpoint. Planned SSE events:

```text
event: run_started
data: {"session_id":"...","run_id":"..."}

event: intent
data: {"name":"FEATURE_LOOKUP","confidence":0.98}

event: sources
data: {"items":[{"source_type":"FEATURE","source_id":"..."}]}

event: token
data: {"text":"CSA-BOT-F-001"}

event: completed
data: {"assistant_message_id":"...","usage":{"total_tokens":620}}
```

Failures should use an `error` event containing the standard Chat error object. A client disconnect should cancel or safely finish the run without leaving it permanently `RUNNING`.

### Convenience Chat endpoint

```http
POST /api/v1/chat
Content-Type: application/json
X-Actor: local-user
```

Planned request:

```json
{
  "session_id": null,
  "product_space_id": "<product-space-uuid>",
  "project_id": "<project-uuid>",
  "message": "Summarize this Project's backlog.",
  "client_message_id": "msg-001",
  "response_mode": "NORMAL"
}
```

If `session_id` is `null`, the endpoint creates a conversation before processing the message. If it is supplied, the endpoint continues that conversation after validating its Project scope.

### List conversations

```http
GET /api/v1/chat/conversations?projectId=<project-uuid>&status=ACTIVE&limit=20&search=backlog
X-Actor: local-user
```

Supported parameters:

| Parameter | Description |
|---|---|
| `projectId` | Required Project scope. |
| `status` | `ACTIVE`, `ARCHIVED`, or `DELETED`. |
| `limit` | Page size. |
| `cursor` | Cursor returned by the previous page. |
| `search` | Title/message-preview search text. |

Planned response:

```json
{
  "items": [
    {
      "session_id": "<session-uuid>",
      "title": "PI 1 Feature Discussion",
      "status": "ACTIVE",
      "current_intent": "FEATURE_LOOKUP",
      "message_count": 8,
      "last_message_preview": "What Stories belong to it?",
      "last_message_at": "2026-07-18T20:10:00Z",
      "created_at": "2026-07-18T20:00:00Z",
      "updated_at": "2026-07-18T20:10:00Z"
    }
  ],
  "next_cursor": null
}
```

### Get conversation metadata

```http
GET /api/v1/chat/conversations/{session_id}
X-Actor: local-user
```

Returns the session’s Project, title, status, current/previous intent context, resolved entities, conversation summary, message count, and timestamps. It must not expose LangGraph checkpoint internals.

### Get message history

```http
GET /api/v1/chat/conversations/{session_id}/messages?limit=50&afterSequence=0
X-Actor: local-user
```

Pagination parameters:

- `limit`
- `beforeSequence`
- `afterSequence`

Each User message includes its persisted intent. Assistant messages include their structured sources and usage metadata.

### Rename or update a conversation

```http
PATCH /api/v1/chat/conversations/{session_id}
Content-Type: application/json
X-Actor: local-user
```

```json
{
  "title": "PI 1 Feature Discussion",
  "status": "ACTIVE",
  "metadata": {}
}
```

The parent Project cannot be changed after creation.

### Archive a conversation

```http
POST /api/v1/chat/conversations/{session_id}/archive
X-Actor: local-user
```

Sets the status to `ARCHIVED` and retains all messages. Archived sessions reject new messages until restored through a future supported update.

### Permanently delete a conversation

```http
DELETE /api/v1/chat/conversations/{session_id}
X-Actor: local-user
```

Deletes Chat runs, retrieval events, intents, messages, the session, and its LangGraph checkpoints. It does not delete Project planning records or documents.

### Read-only behavior

The first Chat release is designed for Project-scoped read operations only. It may search, retrieve, summarize, count, compare, and explain. It must not create, edit, archive, delete, or reset application data.

Mutation requests should return the `UNSUPPORTED_ACTION` intent with an explanation directing the user to the appropriate Project Management API.

### Intent names

Supported planned intents:

```text
GENERAL_CONVERSATION       PROJECT_OVERVIEW
PLANNING_SUMMARY           RELEASE_LOOKUP
RELEASE_SEARCH             SPRINT_LOOKUP
SPRINT_SEARCH              FEATURE_LOOKUP
FEATURE_SEARCH             USER_STORY_LOOKUP
USER_STORY_SEARCH          ACCEPTANCE_CRITERIA_LOOKUP
BACKLOG_SUMMARY            STATUS_SUMMARY
DOCUMENT_SEARCH            KNOWLEDGE_QUESTION
TRACEABILITY_QUERY         IMPACT_ANALYSIS
COMPARISON                 FOLLOW_UP
HELP                       UNSUPPORTED_ACTION
UNKNOWN
```

### Chat errors

Planned error body:

```json
{
  "code": "CHAT_SESSION_ARCHIVED",
  "message": "This conversation is archived and cannot accept new messages.",
  "details": {
    "session_id": "<session-uuid>"
  }
}
```

| Status | Codes |
|---:|---|
| `403` | `CHAT_ACCESS_DENIED` |
| `404` | `CHAT_SESSION_NOT_FOUND`, `PROJECT_NOT_FOUND`, `FEATURE_NOT_FOUND` |
| `409` | `CHAT_SESSION_ARCHIVED`, `DUPLICATE_MESSAGE_CONFLICT`, `CHAT_TURN_ALREADY_RUNNING` |
| `422` | `INVALID_PROJECT_CONTEXT`, `INVALID_HIERARCHY_CONTEXT`, `EMPTY_CHAT_MESSAGE`, `CHAT_MESSAGE_TOO_LONG` |
| `500` | `CHAT_PERSISTENCE_FAILED` |
| `502` | `CHAT_MODEL_FAILED` |
| `504` | `CHAT_TIMEOUT` |

Typical errors:

| Status | Meaning |
|---:|---|
| `404` | The requested entity does not exist or is unavailable. |
| `409` | Dependencies prevent a non-cascade delete, or an optimistic-lock update conflicted. |
| `422` | Request validation failed or selected hierarchy values do not belong together. |
| `502` | OpenAI generation failed. |

## Health and application routes

### `GET /`

Returns the ReleaseLens single-page application.

### `GET /health`

Checks whether the API process is running.

```json
{"status": "ok"}
```

## AI generation APIs

### `POST /feature/generation`

Generates a structured Feature from text or a supported document. When `feature_id` is supplied, the API loads that saved Feature and regenerates it using its complete database context.

Multipart fields:

| Field | Required | Description |
|---|---:|---|
| `product_space_id` | Yes | Selected Product Space. |
| `project_id` | Yes | Selected Project. |
| `pi_release_id` | Yes | PI Release that must belong to the Project. |
| `feature_id` | No | Existing Feature to regenerate. |
| `text` | Conditional | Requirements text or regeneration instructions. |
| `file` | Conditional | `.txt`, `.md`, `.pdf`, or `.docx` source document. |

The response contains a generated Feature with description, problem statement, business value, requirements, dependencies, risks, assumptions, suggested stories, and Acceptance Criteria. Generation does not save the Feature automatically.

### `POST /userstories/generation`

Generates 1–20 User Stories from a saved Feature. The API loads the Feature’s full context and validates the Project, Product Space, PI Release, and optional Sprint.

Multipart fields:

| Field | Required | Description |
|---|---:|---|
| `count` | Yes | Number of Stories, from 1 through 20. |
| `feature_id` | Yes | Parent Feature. |
| `project_id` | Yes | Parent Project. |
| `product_space_id` | Yes | Parent Product Space. |
| `pi_release_id` | Yes | Must match the Feature’s PI Release. |
| `sprint_id` | No | Sprint context for generation. |
| `additional_instructions` | No | Extra guidance for OpenAI. |

The response contains generated Stories and Acceptance Criteria. It does not save them automatically.

## Workspace and hierarchy APIs

### `GET /api/v1/workspace`

Returns the active Organization, Product Spaces, Projects, PI Releases, and Sprints used to populate application selectors.

### `POST /api/v1/product-spaces`

Creates a Product Space under the first configured Organization.

```json
{
  "name": "Customer Experience",
  "key": "CX",
  "description": "Customer-facing products"
}
```

### `PATCH /api/v1/product-spaces/{space_id}`

Updates the Product Space name, key, and description. It increments the row version.

### `POST /api/v1/product-spaces/{space_id}/archive`

Soft-deletes the Product Space and marks its Projects, Features, and User Stories as archived. Database rows are retained.

### `POST /api/v1/product-spaces/{space_id}/projects`

Creates a Project, initializes its Feature/Story sequence, and creates four quarterly PI Releases for 2026.

Request body uses the same `name`, `key`, and `description` fields as Product Space creation.

### `PATCH /api/v1/projects/{project_id}`

Updates a Project’s name, key, and description and increments its version.

### `POST /api/v1/projects/{project_id}/archive`

Soft-deletes the Project and its Features and User Stories by setting `archived_at`. It does not permanently remove records.

### `POST /api/v1/projects/{project_id}/pi-releases/generate-year`

Idempotently creates four quarterly PI Releases for a calendar year.

```json
{"year": 2027}
```

### `POST /api/v1/projects/{project_id}/pi-releases/{pi_release_id}/generate-sprints`

Creates numbered Sprints inside a PI Release. Existing Sprint numbers are skipped.

```json
{
  "count": 6,
  "duration_days": 14
}
```

### `GET /api/v1/product-spaces/{product_space_id}/overview`

Returns Product Space totals and a Project → Feature → User Story hierarchy. Totals include Projects, Features, Stories, in-progress work, completed work, and backlog work.

### `GET /api/v1/projects/{project_id}/backlog`

Returns active Features and User Stories for a Project.

Optional query parameters:

| Parameter | Behavior |
|---|---|
| `piReleaseId` | Limits Features and Stories to a PI Release. |
| `featureId` | Limits results to one Feature and its Stories. |
| `sprintId` | Limits Stories to a Sprint; use `unassigned` for Stories without a Sprint. |
| `userStoryId` | Limits Stories to one Story. |

### `GET /api/v1/projects/{project_id}/planning-hierarchy`

Returns nested PI Release → Feature → Sprint → User Story data for planning screens. It accepts the same planning query parameters as the backlog endpoint.

### `GET /api/v1/projects/{project_id}/planning-options`

Returns filtered PI Release, Feature, Sprint, and User Story options for the shared Planning Context controls.

Supported query parameters are `piReleaseId`, `featureId`, and `sprintId`.

### `GET /api/v1/features/{feature_id}/generation-context`

Returns the complete saved Feature context used for regeneration, including Acceptance Criteria and PI Release information.

### `PUT /api/v1/features/{feature_id}/regenerated`

Saves a regenerated Feature in place, replaces Feature-level Acceptance Criteria, increments its version, and records an activity log.

```json
{
  "pi_release_id": "<uuid>",
  "status": "DRAFT",
  "feature": {
    "title": "Chat orchestration",
    "description": "...",
    "problem_statement": "...",
    "business_value": "...",
    "functional_requirements": ["..."],
    "non_functional_requirements": [],
    "dependencies": [],
    "risks": [],
    "assumptions": [],
    "priority": "MEDIUM",
    "suggested_user_stories": [],
    "acceptance_criteria": [
      {"given": "...", "when": "...", "then": "..."}
    ]
  }
}
```

## Work-item APIs

### `POST /api/v1/projects/{project_id}/work-items`

Creates a manual Feature or User Story and records an activity log.

```json
{
  "item_type": "FEATURE",
  "title": "Feature title",
  "description": "Feature scope",
  "status": "BACKLOG",
  "priority": "HIGH",
  "story_points": null,
  "parent_feature_id": null,
  "pi_release_id": "<uuid>"
}
```

For `USER_STORY`, `parent_feature_id` is required, `story_points` may be supplied, and the Story inherits its parent Feature’s PI Release.

### `PATCH /api/v1/projects/{project_id}/work-items/{item_type}/{item_id}`

Updates a Feature or Story. `item_type` is `feature` or `story`. The request must contain the current `version`; stale versions return `409`.

```json
{
  "title": "Updated title",
  "status": "IN_PROGRESS",
  "priority": "HIGH",
  "version": 2
}
```

### `POST /api/v1/projects/{project_id}/work-items/{item_type}/{item_id}/archive`

Soft-deletes a work item by setting `archived_at`. Archiving a Feature also archives its active User Stories.

### `POST /api/v1/projects/{project_id}/work-items/{item_type}/{item_id}/restore`

Clears `archived_at` for one archived Feature or Story. Restoring a Feature does not automatically restore its archived Stories.

### `POST /api/v1/projects/{project_id}/generated-work-items`

Transactionally saves generated Features, Stories, Acceptance Criteria, an AI-generation record, sequence updates, and an activity log.

Requires an `Idempotency-Key` header containing 8–200 characters. Repeating the same key for the same Project returns the stored response instead of inserting duplicates.

Important body fields:

- `product_space_id` and `project_id`
- `release_id`
- Optional `sprint_id` and `parent_feature_id`
- `save_mode`: `DRAFT`, `BACKLOG`, or `SPRINT`
- Optional generated `feature`
- Up to 20 generated `user_stories`

## Permanent deletion APIs

Deletion is different from Archive. These APIs permanently remove database records and return structured row counts.

The optional `X-Actor` header identifies the actor. The bundled local UI uses `local-user`. When it contains a UUID, the deletion service checks Project, Product Space, or Organization membership and administrative roles.

### `GET /api/v1/features/{feature_id}/deletion-preview`

Locks and loads a Feature and returns dependent User Story and Acceptance Criteria counts for the confirmation dialog. It does not delete anything.

### `DELETE /api/v1/user-stories/{story_id}`

Permanently deletes:

1. Story Acceptance Criteria
2. Story-specific activity logs
3. The User Story
4. Any AI generation in the Project that is no longer referenced

### `DELETE /api/v1/features/{feature_id}`

Without `cascade=true`, returns `409` when dependent Stories or Acceptance Criteria exist.

### `DELETE /api/v1/features/{feature_id}?cascade=true`

Permanently deletes Feature/Story Acceptance Criteria, related activity logs, dependent User Stories, the Feature, and unreferenced AI generations.

Example response:

```json
{
  "deleted": true,
  "entity_type": "FEATURE",
  "entity_id": "<uuid>",
  "deleted_counts": {
    "acceptance_criteria": 12,
    "activity_logs": 4,
    "user_stories": 4,
    "features": 1,
    "ai_generations": 1
  }
}
```

### `DELETE /api/v1/sprints/{sprint_id}`

Sets `user_stories.sprint_id` to `NULL`, then deletes the Sprint. Stories remain available as unassigned/backlog work.

### `DELETE /api/v1/releases/{release_id}`

Returns `409` if the Release has Sprints, Features, or User Stories.

### `DELETE /api/v1/releases/{release_id}?cascade=true`

Deletes Acceptance Criteria, activity logs, User Stories, Features, Sprints, the Release, and unreferenced AI generations in dependency-safe order.

### `DELETE /api/v1/projects/{project_id}`

Returns `409` when Project planning records exist.

### `DELETE /api/v1/projects/{project_id}?cascade=true`

Deletes the Project’s Acceptance Criteria, Stories, Features, Sprints, Releases, AI generations, sequences, idempotency keys, activity logs, Project members, and finally the Project. It does not delete the Product Space, Organization, or other Projects.

### `DELETE /api/v1/product-spaces/{space_id}`

Returns `409` when the Product Space contains Projects.

### `DELETE /api/v1/product-spaces/{space_id}?cascade=true`

Runs complete Project cleanup for every contained Project, deletes Product Space members, and deletes the Product Space. The Organization remains.

### `DELETE /api/v1/organizations/{organization_id}`

Returns `409` when the Organization contains Product Spaces.

### `DELETE /api/v1/organizations/{organization_id}?cascade=true`

Deletes every contained Project and Product Space, then Organization members and the Organization. It never deletes `auth.users`.

### Deprecated empty-only deletion routes

These compatibility routes only delete empty containers:

- `DELETE /api/v1/projects/{project_id}/empty`
- `DELETE /api/v1/product-spaces/{space_id}/empty`

New integrations should use the normal deletion endpoints with an explicit `cascade` choice.

## Administrative data reset

### `DELETE /api/v1/admin/application-data`

Deletes all ReleaseLens application rows while preserving tables, indexes, functions, extensions, RLS policies, migrations, and `auth.users`.

The API is available only when:

1. `ENABLE_APPLICATION_DATA_RESET=true`
2. `APP_ENV` is not `production`
3. `X-Admin-Token` exactly matches `ADMIN_RESET_TOKEN`
4. The confirmation text and environment both match

Example:

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/admin/application-data \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: replace-with-server-secret" \
  -H "X-Actor: administrator@example.com" \
  -d '{
    "confirmation": "DELETE ALL RELEASELENS DATA",
    "environment": "development"
  }'
```

Tables included:

- `chat_runs`, `chat_retrieval_events`, `chat_message_intents`, `chat_messages`, `chat_sessions`
- `acceptance_criteria`, `user_stories`, `features`, `sprints`, `releases`
- `ai_generations`, `project_sequences`, `idempotency_keys`, `activity_logs`
- `project_members`, `product_space_members`, `organization_members`
- `projects`, `product_spaces`, `organizations`
- `document_chunks`, `documents`
- `connection_test`, `escalated_table`

The reset endpoint does not run automatically during startup.

For a manual local administrator reset, use `sql/reset_application_data.sql`. That script truncates rows with `RESTART IDENTITY CASCADE`; it does not drop schema objects.

## Database migrations

Apply the base SQL files in their documented order, followed by relevant incremental migrations. Hard-delete foreign-key behavior is defined in:

```text
sql/hard_delete_foreign_keys.sql
```

Important rules include:

- Project-owned hierarchy records cascade from their parent.
- `user_stories.sprint_id` uses `ON DELETE SET NULL`.
- Feature and Story AI-generation references use `ON DELETE SET NULL`.
- `document_chunks.doc_id` cascades from `documents.doc_id`.
- Organization membership deletion does not delete users from Supabase Auth.

## Tests and validation

Run the integration tests against a development/test database:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app main.py tests
node --check app/static/app.js
```

The deletion integration tests create temporary records inside transactions and roll them back after every test.

## Authentication note

The database schema contains membership roles and RLS helper functions. The current bundled browser UI still operates in local-user mode because JWT middleware has not yet been connected to FastAPI. Production deployment must derive `X-Actor`/actor identity from a verified token at the server boundary; clients must not be trusted to assert their own identity.

The administrative reset token must remain a server-side secret and must never be embedded in the SPA.
