# Implementation Flow

```mermaid
flowchart TD
    UI[ReleaseMind GitHub Screen] -->|POST repository_url| API[FastAPI Summary Endpoint]
    API --> URL[Validate GitHub URL]
    URL --> META[GitHub Metadata API]
    META --> REF[Resolve Branch and Commit SHA]
    REF --> CACHE{Cached by Commit?}
    CACHE -->|Yes| RESULT[Return Structured Summary]
    CACHE -->|No| ARCHIVE[Download GitHub Tarball]
    ARCHIVE --> SAFE[Safe Temporary Extraction]
    SAFE --> SCAN[Scan Supported Files]
    SCAN --> FILTER[Skip Generated/Binary/Sensitive Files]
    FILTER --> REDACT[Redact Secret Patterns]
    REDACT --> PRIORITY[Prioritize Important Files]
    PRIORITY --> BATCH[Create Evidence Batches]
    BATCH --> MAP[LLM Batch Summaries]
    MAP --> REDUCE[LLM Final Repository Summary]
    REDUCE --> SAVE[Cache Result]
    SAVE --> RESULT
```
