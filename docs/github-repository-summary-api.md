# GitHub Repository Summary API

The repository summary endpoint is part of the existing ReleaseLens FastAPI server:

```text
POST /api/v1/github/summary
```

## Configuration

Copy the variables from `.env.github-summary.example` into the main `.env`. The existing
`OPENAI_API_KEY` is reused. `GITHUB_TOKEN` is optional for public repositories and required
for private repositories. Never send either credential from the client.

```env
GITHUB_TOKEN=github_pat_replace_me
GITHUB_API_VERSION=2026-03-10
GITHUB_SUMMARY_MODEL=gpt-5-mini
```

Install the main dependency set and run the existing application:

```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Swagger remains available at `http://localhost:8000/docs`, and the existing health check is
`GET http://localhost:8000/health`.

## Request

Only `repository_url` is required. `branch` and `force_refresh` are optional.

```json
{
  "repository_url": "https://github.com/Abhinav-kanduri/Customer-Support-AI-Chatbot"
}
```

```powershell
$body = @{
  repository_url = "https://github.com/Abhinav-kanduri/Customer-Support-AI-Chatbot"
} | ConvertTo-Json

$result = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/github/summary" `
  -ContentType "application/json" `
  -Body $body

$result.summary
$result.summary_markdown
```

The endpoint downloads a GitHub tarball with the backend token, validates archive paths,
filters generated/binary/sensitive files, redacts common secret patterns, creates bounded
evidence batches, requests strict structured output from the OpenAI Responses API with
storage disabled, and caches the final response by repository commit and model.

