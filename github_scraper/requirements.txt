# GitHub Repository Summary API

A separate FastAPI service that accepts a GitHub repository URL, downloads a secure branch snapshot through the GitHub REST API, scans source code and documentation, and generates a structured repository summary using the OpenAI Responses API.

The caller only needs to provide:

```json
{
  "repository_url": "https://github.com/Abhinav-kanduri/Customer-Support-AI-Chatbot"
}
```

The GitHub token and OpenAI key remain server-side in `.env`.

## What the API returns

- Executive summary and problem statement
- Primary capabilities
- Confirmed architecture and processing flow
- Technology stack
- Key components with repository-relative paths
- Confirmed API endpoints
- Data and storage design
- Setup and run instructions
- Strengths, risks, gaps, and recommended next steps
- Evidence file paths
- A ready-to-display Markdown summary
- Repository metadata, analyzed commit SHA, language distribution, and scan statistics

## Security behavior

- Only HTTPS repository-root URLs from configured GitHub hosts are accepted.
- Tokens are never accepted in the public request body.
- Private repositories use the server-side `GITHUB_TOKEN` header.
- The service downloads a GitHub tarball instead of placing a token in a Git clone URL.
- Archive paths are validated before extraction.
- Symlinks and hard links in archives are rejected.
- `.env`, private keys, credential files, Terraform state, binaries, generated folders, and oversized files are skipped.
- Common GitHub, AWS, private-key, password, and API-key patterns are redacted before code is sent to the LLM.
- OpenAI requests set `store: false`.

## Project structure

```text
github-repository-summary-api/
├── app/
│   ├── api/routes.py
│   ├── services/
│   │   ├── archive.py
│   │   ├── cache.py
│   │   ├── github_client.py
│   │   ├── openai_client.py
│   │   ├── scanner.py
│   │   └── summary_service.py
│   ├── utils/
│   │   ├── github_url.py
│   │   └── security.py
│   ├── config.py
│   ├── main.py
│   └── schemas.py
├── tests/
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## 1. Configure credentials

Copy the example configuration:

### Windows PowerShell

```powershell
Copy-Item .env.example .env
notepad .env
```

### macOS/Linux

```bash
cp .env.example .env
```

Set your credentials:

```env
GITHUB_TOKEN=github_pat_your_fine_grained_token
OPENAI_API_KEY=sk_your_openai_api_key
OPENAI_MODEL=gpt-5-mini
```

For the public example repository, the GitHub token is optional, but using it provides authenticated API limits. A private repository requires a token with access to that repository and read access to repository contents and metadata.

Do not put `.env` in Git. It is already ignored.

## 2. Run with Docker

```bash
docker compose up --build
```

Open Swagger:

```text
http://localhost:8000/docs
```

Health endpoint:

```text
http://localhost:8000/health
```

## 3. Run without Docker

Python 3.11 or newer is required.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

## 4. Generate a summary

### cURL

```bash
curl -X POST "http://localhost:8000/api/v1/github/summary" \
  -H "Content-Type: application/json" \
  -d '{
    "repository_url": "https://github.com/Abhinav-kanduri/Customer-Support-AI-Chatbot"
  }'
```

### Windows PowerShell

```powershell
$body = @{
  repository_url = "https://github.com/Abhinav-kanduri/Customer-Support-AI-Chatbot"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/github/summary" `
  -ContentType "application/json" `
  -Body $body
```

### Select a branch or commit

```json
{
  "repository_url": "https://github.com/Abhinav-kanduri/Customer-Support-AI-Chatbot",
  "branch": "main",
  "force_refresh": false
}
```

## 5. Example response shape

```json
{
  "status": "completed",
  "generated_at": "2026-08-01T23:55:00Z",
  "duration_seconds": 18.42,
  "repository": {
    "owner": "Abhinav-kanduri",
    "name": "Customer-Support-AI-Chatbot",
    "full_name": "Abhinav-kanduri/Customer-Support-AI-Chatbot",
    "url": "https://github.com/Abhinav-kanduri/Customer-Support-AI-Chatbot",
    "default_branch": "main",
    "analyzed_ref": "main",
    "commit_sha": "...",
    "language_bytes": {
      "Python": 123456
    }
  },
  "analysis": {
    "archive_bytes": 1234567,
    "discovered_files": 90,
    "analyzed_files": 55,
    "skipped_files": 35,
    "analyzed_characters": 240000,
    "batches": 6,
    "cache_hit": false
  },
  "summary": {
    "title": "...",
    "executive_summary": "...",
    "problem_statement": "...",
    "primary_capabilities": [],
    "architecture": [],
    "technology_stack": [],
    "key_components": [],
    "api_endpoints": [],
    "data_and_storage": [],
    "request_or_processing_flow": [],
    "setup_and_run": [],
    "strengths": [],
    "risks_and_gaps": [],
    "recommended_next_steps": [],
    "evidence_files": []
  },
  "summary_markdown": "# ...",
  "model": "gpt-5-mini"
}
```

## How summarization works

```text
Repository URL
    ↓
Validate GitHub host and owner/repository path
    ↓
GitHub repository metadata + language API
    ↓
Resolve default branch and commit SHA
    ↓
Download branch tarball with server-side token
    ↓
Safe temporary extraction
    ↓
Skip binaries, generated folders, secrets and oversized files
    ↓
Prioritize README, architecture, setup, manifests, entrypoints,
API routes, services, models, database files and tests
    ↓
Extract file outlines and redact secret patterns
    ↓
Group evidence into bounded batches
    ↓
Generate structured evidence summaries
    ↓
Consolidate them into one repository summary
    ↓
Cache by repository + ref + commit SHA + model
```

The map-reduce approach prevents one very large repository prompt and helps keep evidence grouped into manageable model requests.

## Integrate with ReleaseMind

Your ReleaseMind frontend can call this backend route:

```typescript
const response = await fetch(
  "http://localhost:8000/api/v1/github/summary",
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      repository_url:
        "https://github.com/Abhinav-kanduri/Customer-Support-AI-Chatbot",
    }),
  },
);

if (!response.ok) {
  throw new Error(await response.text());
}

const result = await response.json();
console.log(result.summary.executive_summary);
console.log(result.summary_markdown);
```

In production, call the API through your ReleaseMind backend rather than directly from a public browser, and add your existing user/session authorization to the route.

## Run tests

```bash
pytest -q
```

## Important production improvements

- Put `GITHUB_TOKEN` and `OPENAI_API_KEY` in Vault, AWS Secrets Manager, Azure Key Vault, or your Kubernetes secret provider.
- Add authentication and authorization before exposing the summary endpoint.
- Move long repository summaries to a queue such as Celery, Dramatiq, or a Kubernetes job.
- Store results in PostgreSQL keyed by product space, project, repository, ref, and commit SHA.
- Add webhook-based re-summarization when the default branch changes.
- Add per-project repository allowlists and request rate limits.
- Add cost and token usage telemetry.
