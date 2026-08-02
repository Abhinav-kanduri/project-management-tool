# GitHub repository summary indexing

The GitHub summary API validates a repository URL, downloads a GitHub archive, scans supported files, creates a structured OpenAI summary, renders `summary.md`, creates Markdown-aware chunks, embeds them, and stores the document and chunks in PostgreSQL with pgvector. Artifacts are written under `artifacts/{owner}/{repository}/{commit_sha}/` and include `summary.md`, `summary.chunks.jsonl`, and `summary.manifest.json`.

## Configuration and token security

Copy `.env.example` to `.env` in the project root. Put the GitHub PAT in this backend-only file as `GITHUB_TOKEN=github_pat_...`; never place it in frontend code, a request body, a Git URL, or source control. Set `OPENAI_API_KEY`, `OPENAI_MODEL` or `GITHUB_SUMMARY_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `DATABASE_ENABLED=true`, `DATABASE_URL`, and the chunking variables documented in the example file. The scanner excludes known secret files and redacts credential patterns before AI generation and embedding.

The SQL migration is `sql/github_repository_summaries.sql`. It enables pgvector, creates document and chunk tables, and adds repository, commit, section, and HNSW cosine indexes. The checked-in migration uses `vector(1536)` and must be changed together with `EMBEDDING_DIMENSIONS` if a different vector size is selected.

## Start with Docker

PowerShell and other shells use the same startup command:

```powershell
Copy-Item .env.example .env
notepad .env
docker compose up --build
```

Swagger is available at `http://127.0.0.1:8001/docs`; health is at `http://127.0.0.1:8001/health`. PostgreSQL data uses a named volume and artifacts are bind-mounted to the host `artifacts` directory.

## API examples

### Repository dropdown and Project association

The sidebar repository dropdown calls the backend with the current Project ID. GitHub credentials never reach the browser:

```http
GET /api/v1/github/repositories?page=1&per_page=100&project_id=PROJECT_UUID
```

Each option includes the stable numeric GitHub `id`, repository metadata, and an `imported` flag for the selected Project. Link the selected option to the current hierarchy with:

```http
POST /api/v1/github/repositories/import
Content-Type: application/json

{
  "github_repository_id": 123456789,
  "product_space_id": "PRODUCT_SPACE_UUID",
  "project_id": "PROJECT_UUID"
}
```

The backend re-fetches the repository by ID, verifies that the Project belongs to the Product Space, upserts current GitHub metadata, and creates an idempotent Project association. Saved associations can be read without contacting GitHub:

```http
GET /api/v1/github/repositories/imported?project_id=PROJECT_UUID
```

Apply `sql/github_repository_catalog.sql` after the Product Space and Project table migrations. Docker Compose applies it automatically for a new database volume.

PowerShell summary request:

```powershell
$body = @{
  repository_url = "https://github.com/owner/repository"
  branch = "main"
  force_refresh = $false
} | ConvertTo-Json

$result = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8001/api/v1/github/summary" `
  -ContentType "application/json" -Body $body
```

cURL summary request:

```bash
curl -X POST http://127.0.0.1:8001/api/v1/github/summary \
  -H "Content-Type: application/json" \
  -d '{"repository_url":"https://github.com/owner/repository","branch":"main","force_refresh":false}'
```

The response contains the structured summary, rendered Markdown, analysis counts, and an `artifact` object with `document_id`, paths, hash, chunk count, embedding metadata, and retrieval URLs.

Download and inspect:

```powershell
Invoke-WebRequest "http://127.0.0.1:8001/api/v1/github/summary/$documentId/markdown" -OutFile summary.md
Invoke-RestMethod "http://127.0.0.1:8001/api/v1/github/summary/$documentId/chunks?offset=0&limit=50"
```

```bash
curl -OJ http://127.0.0.1:8001/api/v1/github/summary/DOCUMENT_UUID/markdown
curl "http://127.0.0.1:8001/api/v1/github/summary/DOCUMENT_UUID/chunks?offset=0&limit=50"
```

Semantic search:

```powershell
$search = @{ document_id = $documentId; query = "How is authentication implemented?"; top_k = 5 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/api/v1/github/summary/search" -ContentType "application/json" -Body $search
```

```bash
curl -X POST http://127.0.0.1:8001/api/v1/github/summary/search \
  -H "Content-Type: application/json" \
  -d '{"repository_url":"https://github.com/owner/repository","branch":"main","query":"How is authentication implemented?","top_k":5}'
```

Search scores are `1 - pgvector cosine distance`; higher values are more similar.

## Cache and troubleshooting

Completed results are keyed by repository, branch, commit SHA, summary format version, summary model, embedding model, and dimensions. An identical completed commit returns `cache_hit=true` without calling either model. `force_refresh=true` regenerates artifacts and atomically replaces chunks while retaining the existing document identity.

- `401`/`403`: verify that `GITHUB_TOKEN` has access to the repository.
- `503 DATABASE_UNAVAILABLE`: confirm PostgreSQL is healthy and apply the migration.
- `ARTIFACT_NOT_FOUND`: confirm the artifacts bind mount exists and is writable.
- Embedding dimension failures: keep the environment value and SQL vector dimension aligned.
- Health `degraded`: inspect the individual database, pgvector, token, model, and artifact fields.

Run credential-free tests with `python -m pytest`. Verify imports with `python -m compileall -q app main.py tests`, and validate Compose with `docker compose config`.
