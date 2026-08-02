# Neo4j and LangChain local development

## Architecture

ReleaseLens keeps PostgreSQL as the system of record for transactional planning,
documents, chunks, and chat history. Neo4j stores graph relationships and an
optional copy of chunk text/embeddings for graph-aware retrieval. Records in both
stores should use the same stable application UUID; never join them by Neo4j's
internal node ID.

FastAPI uses one process-scoped official Neo4j driver for parameterized Cypher.
LangChain supplies `Neo4jGraph` for schema-aware graph access and `Neo4jVector`
with `OpenAIEmbeddings` for semantic search. The application loads local graph
credentials from `infra/neo4j/.env` automatically, unless exported environment
variables already override them.

Neo4j uses Cypher (`*.cypher`), not SQL. PostgreSQL migrations remain in `sql/`;
Neo4j migrations live only in `infra/neo4j/migrations/`.

## Prerequisites and first start

- Docker Desktop with Compose v2
- Python 3.10 through 3.14
- An OpenAI API key in the existing root `.env`
- Roughly 2 GB of memory available to Docker

Windows PowerShell:

```powershell
python infra/neo4j/scripts/generate_env.py
python -m pip install -r requirements.txt
docker compose --env-file infra/neo4j/.env -f infra/neo4j/compose.yaml up -d
python infra/neo4j/scripts/wait_for_neo4j.py
python infra/neo4j/scripts/neo4j_migrate.py
python infra/neo4j/scripts/neo4j_verify.py
```

macOS/Linux uses the same commands with `python3` where `python` is unavailable.
The generated password remains in the ignored `infra/neo4j/.env` file and is
never printed. The Compose service binds HTTP and Bolt only to localhost.

VS Code's **Neo4j: Start** task runs container startup, readiness, migrations,
and verification in sequence. Recommended extensions are prompted from
`.vscode/extensions.json`.

## Connections

Neo4j Browser:

- URL: `http://localhost:7474`
- Bolt URI: `neo4j://localhost:7687`
- Username: `neo4j`
- Password: read `infra/neo4j/.env`
- Database: `neo4j`

In Neo4j for VS Code, open the Neo4j Activity Bar icon, choose **Add New
Connection**, enter the values above, then open a `.cypher` file. Use Ctrl+Enter
(Command+Enter on macOS) for the current statement, or the Command Palette to run
a selection/all statements. Results can be viewed as rows or a graph.

FastAPI graph endpoints:

```text
GET  /api/v1/graph/health
GET  /api/v1/graph/schema
POST /api/v1/graph/search  {"query":"graph-aware retrieval", "k":5}
```

Semantic search returns results after `DocumentChunk` nodes contain 1536-value
embeddings. The configured vector dimension must exactly match the OpenAI
embedding model. The development seed intentionally does not create fake vectors.

## Migrations

Migration files follow `VNNN__description.cypher`. The Python runner orders them,
parses comments and quoted semicolons safely, calculates SHA-256 checksums, and
records successful runs as `GraphMigration` nodes. Applied migrations are
immutable: add a new migration instead of editing one. A changed checksum causes
the runner to stop.

```powershell
python infra/neo4j/scripts/neo4j_migrate.py --status
python infra/neo4j/scripts/neo4j_migrate.py --dry-run
python infra/neo4j/scripts/neo4j_migrate.py
```

Developer queries are in `infra/neo4j/queries/development_checks.cypher`.

## Persistence, shutdown, reset, and backup

Named volumes persist data, logs, and downloaded plugins. Normal shutdown keeps
them:

```powershell
docker compose --env-file infra/neo4j/.env -f infra/neo4j/compose.yaml down
```

Reset is destructive and refuses to run without the exact confirmation flag. It
verifies that Compose exposes only the three expected Neo4j volumes before deletion:

```powershell
python infra/neo4j/scripts/neo4j_reset.py --yes-delete-all-local-neo4j-data
```

Do not treat this local Community setup as production. Community Edition does not
provide Enterprise online-backup/clustering features. For important local data,
stop writes and use Neo4j's documented dump/restore workflow or copy a consistent
stopped data volume.

## Troubleshooting

- **Docker daemon unavailable:** start Docker Desktop and rerun `docker info`.
- **Ports 7474/7687 busy:** stop the conflicting process or change the two port
  values in `infra/neo4j/.env`; keep `NEO4J_URI` aligned with the Bolt port.
- **Authentication fails after editing the password:** `NEO4J_AUTH` initializes
  only a new data volume. Restore the old password or use the protected local reset.
- **Container unhealthy:** inspect `docker compose --env-file infra/neo4j/.env -f
  infra/neo4j/compose.yaml logs neo4j`.
- **APOC/GDS unavailable or plugin download fails:** confirm internet access on
  first start, the `neo4j_plugins` volume, and the `apoc` / `graph-data-science`
  names. Restart after correcting the problem.
- **Migration checksum mismatch:** restore the already-applied file and create a
  new higher-numbered migration.
- **Vector dimension mismatch:** keep the index, `OPENAI_EMBEDDING_DIMENSIONS`, and
  embedding model at 1536, or add a deliberate replacement-index migration.
- **Vector index is POPULATING:** wait and check `SHOW VECTOR INDEXES`; do not query
  it until its state is `ONLINE`.
- **Windows bind-mount permission error:** ensure Docker Desktop can access this
  repository and that `infra/neo4j/import` exists.
- **macOS memory pressure:** give Docker Desktop at least 2 GB or reduce the local
  heap/page-cache values together.
- **Linux Docker socket denied:** add your account to the Docker group according
  to Docker's install guide, then start a new login session.
- **VS Code cannot connect:** verify `/api/v1/graph/health`, confirm Bolt port 7687,
  select database `neo4j`, and re-read the ignored local password.

Official references: [Neo4j Docker](https://neo4j.com/docs/operations-manual/current/docker/introduction/),
[Docker plugins](https://neo4j.com/docs/operations-manual/current/docker/plugins/),
[Neo4j Python driver](https://neo4j.com/docs/python-manual/current/), and
[LangChain Neo4j integration](https://pypi.org/project/langchain-neo4j/).
