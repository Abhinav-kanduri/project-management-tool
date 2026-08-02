# Local Neo4j development

This directory contains the Docker Compose configuration, Cypher migrations,
automation scripts, and sample graph used to run Neo4j locally for ReleaseLens.

The local service uses:

- Neo4j Community Edition `2026.06.0`
- APOC `2026.06.0`
- Graph Data Science `2026.06.0`
- Bolt on `neo4j://localhost:7687`
- Neo4j Browser on `http://localhost:7474`
- Persistent Docker volumes for data, logs, and plugins

## Prerequisites

Install and start the following:

1. Docker Desktop for Windows.
2. WSL 2 with Virtual Machine Platform enabled.
3. Python 3.10 or newer.
4. The project virtual environment at `.venv`.

Verify WSL and Docker from PowerShell:

```powershell
wsl --status
docker desktop status
docker version
```

Docker Desktop must report `running`, and `docker version` must display both a
Client and Server section.

## First-time setup

Run every command in this guide from the repository root:

```powershell
cd C:\Users\abhin\AIBatch6\RleaseLens-backend\project-management-tool
```

### 1. Install Python dependencies

Use the project interpreter rather than the global `python` command:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

Confirm the Neo4j and LangChain packages are available:

```powershell
.\.venv\Scripts\python.exe -c "import neo4j, langchain_neo4j, langchain_openai; print('Dependencies OK')"
```

### 2. Create the local environment file

Check whether the ignored local configuration already exists:

```powershell
Test-Path .\infra\neo4j\.env
```

If the result is `False`, generate it:

```powershell
.\.venv\Scripts\python.exe .\infra\neo4j\scripts\generate_env.py
```

The script creates a strong local password without printing it. The real
`infra/neo4j/.env` file is ignored by Git. Do not commit or share it.

### 3. Start Neo4j

```powershell
docker compose --env-file .\infra\neo4j\.env -f .\infra\neo4j\compose.yaml up -d
```

The first startup can take several minutes while Docker downloads the image and
installs APOC and Graph Data Science.

Check the container:

```powershell
docker compose --env-file .\infra\neo4j\.env -f .\infra\neo4j\compose.yaml ps
```

The expected state is similar to:

```text
releaselens-neo4j   neo4j:2026.06.0   Up (...) (healthy)
```

### 4. Wait for Bolt connectivity

```powershell
.\.venv\Scripts\python.exe .\infra\neo4j\scripts\wait_for_neo4j.py
```

Expected output:

```text
Neo4j is ready after 1 attempt(s).
```

### 5. Apply Cypher migrations

```powershell
.\.venv\Scripts\python.exe .\infra\neo4j\scripts\neo4j_migrate.py
```

The first run applies six migrations. Later runs safely skip them because their
versions and SHA-256 checksums are stored in Neo4j.

Display migration status without changing the database:

```powershell
.\.venv\Scripts\python.exe .\infra\neo4j\scripts\neo4j_migrate.py --status
```

Never edit an applied migration. Create a new higher-numbered `.cypher` file
instead.

### 6. Verify the installation

```powershell
.\.venv\Scripts\python.exe .\infra\neo4j\scripts\neo4j_verify.py
```

A successful local installation reports:

```text
Neo4j version: 2026.06.0
Database: neo4j
APOC version: 2026.06.0
GDS version: 2026.06.0
Migrations: 6
Verification passed.
```

## Open Neo4j Browser and display the graph

Open this URL:

```text
http://localhost:7474
```

Use these connection values:

```text
URI: neo4j://localhost:7687
Username: neo4j
Password: read from infra/neo4j/.env
Database: neo4j
```

Open `infra/neo4j/.env` locally to read the password. Do not paste the password
into source code, screenshots, chat messages, or committed files.

Run this query in Neo4j Browser to display the seeded planning hierarchy:

```cypher
MATCH path =
  (:ProductSpace {name: 'GMNS AI Platform'})
  -[:CONTAINS_PROJECT]->
  (:Project {project_key: 'RLENS'})
  -[:HAS_FEATURE]->
  (:Feature {feature_key: 'RLENS-F-001'})
  -[:HAS_USER_STORY]->
  (:UserStory {story_key: 'RLENS-101'})
RETURN path;
```

Select the graph icon in the result panel if Neo4j Browser initially displays a
table.

Display documents, chunks, and mentioned entities:

```cypher
MATCH path =
  (:Project)-[:HAS_DOCUMENT]->
  (:Document)-[:HAS_CHUNK]->
  (:DocumentChunk)-[:MENTIONS]->
  (:Entity)
RETURN path;
```

More validation queries are available in
`infra/neo4j/queries/development_checks.cypher`.

## Run ReleaseLens with Neo4j

Keep Neo4j running and open another PowerShell terminal:

```powershell
cd C:\Users\abhin\AIBatch6\RleaseLens-backend\project-management-tool
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8003
```

Open:

- ReleaseLens: `http://127.0.0.1:8003`
- Swagger: `http://127.0.0.1:8003/docs`
- API health: `http://127.0.0.1:8003/health`
- Neo4j health: `http://127.0.0.1:8003/api/v1/graph/health`

The graph health response should resemble:

```json
{
  "status": "ok",
  "uri": "neo4j://localhost:7687",
  "database": "neo4j",
  "version": "2026.06.0",
  "framework": "LangChain"
}
```

## Daily startup

After the first setup, use:

```powershell
cd C:\Users\abhin\AIBatch6\RleaseLens-backend\project-management-tool
docker compose --env-file .\infra\neo4j\.env -f .\infra\neo4j\compose.yaml up -d
.\.venv\Scripts\python.exe .\infra\neo4j\scripts\wait_for_neo4j.py
.\.venv\Scripts\python.exe .\infra\neo4j\scripts\neo4j_migrate.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8003
```

## Logs, restart, and shutdown

View logs:

```powershell
docker compose --env-file .\infra\neo4j\.env -f .\infra\neo4j\compose.yaml logs -f neo4j
```

Press `Ctrl+C` to leave the logs without stopping the database.

Restart Neo4j:

```powershell
docker compose --env-file .\infra\neo4j\.env -f .\infra\neo4j\compose.yaml restart neo4j
```

Stop Neo4j without deleting its data:

```powershell
docker compose --env-file .\infra\neo4j\.env -f .\infra\neo4j\compose.yaml down
```

The named Docker volumes preserve the database across normal shutdowns.

## Protected local reset

Reset deletes all local ReleaseLens Neo4j data and reruns the migrations. It does
not delete PostgreSQL data. Run it only when the local graph can be discarded:

```powershell
.\.venv\Scripts\python.exe .\infra\neo4j\scripts\neo4j_reset.py --yes-delete-all-local-neo4j-data
```

The script refuses to run without the complete confirmation option and verifies
the Compose volume names before deleting them.

## Troubleshooting

### Compose cannot find `.env`

You are probably in the wrong directory. Return to the repository root:

```powershell
cd C:\Users\abhin\AIBatch6\RleaseLens-backend\project-management-tool
Test-Path .\infra\neo4j\.env
```

### Docker Desktop is stopped

```powershell
docker desktop status
wsl --status
```

Start Docker Desktop and wait until its status is `running`. Docker Desktop on
Windows requires WSL 2 and Virtual Machine Platform. A newly enabled Windows
optional component requires a Windows restart before Docker can use it.

### Container is restarting or unhealthy

```powershell
docker compose --env-file .\infra\neo4j\.env -f .\infra\neo4j\compose.yaml ps
docker compose --env-file .\infra\neo4j\.env -f .\infra\neo4j\compose.yaml logs --tail 200 neo4j
```

### FastAPI reports `NEO4J_UNAVAILABLE`

First run the standalone verification:

```powershell
.\.venv\Scripts\python.exe .\infra\neo4j\scripts\neo4j_verify.py
```

If verification passes, stop the existing Uvicorn process with `Ctrl+C` and
restart it so that it reloads the current code and environment.

### Python cannot import `neo4j`

The global Python interpreter is being used. Install and run through `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8003
```

### Authentication fails after changing the password

`NEO4J_AUTH` initializes credentials only when the data volume is first created.
Changing `infra/neo4j/.env` does not change the password inside an existing data
volume. Restore the original local password or use the protected reset if the
local graph data can be deleted.

### Ports 7474 or 7687 are already in use

Inspect the conflict:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 7474,7687
```

Stop the conflicting local service, or change the host port values in the ignored
`infra/neo4j/.env` and keep `NEO4J_URI` aligned with the selected Bolt port.

## Important files

| Path | Purpose |
|---|---|
| `infra/neo4j/compose.yaml` | Neo4j Community Docker service and health check. |
| `infra/neo4j/.env` | Ignored local credentials and ports. |
| `infra/neo4j/.env.example` | Safe configuration template. |
| `infra/neo4j/migrations/` | Immutable versioned Cypher migrations. |
| `infra/neo4j/scripts/neo4j_migrate.py` | Checksum-tracked migration runner. |
| `infra/neo4j/scripts/neo4j_verify.py` | Neo4j, plugin, schema, index, and seed verification. |
| `infra/neo4j/queries/development_checks.cypher` | Queries for manual graph inspection. |

This Compose configuration is intended for local development, not production.

