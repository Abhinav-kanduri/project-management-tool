# ReleaseLens local Neo4j

This folder contains the isolated Neo4j Community development service, versioned
Cypher migrations, validation queries, and automation. From the repository root:

```powershell
python infra/neo4j/scripts/generate_env.py
python -m pip install -r infra/neo4j/requirements.txt
docker compose --env-file infra/neo4j/.env -f infra/neo4j/compose.yaml up -d
python infra/neo4j/scripts/wait_for_neo4j.py
python infra/neo4j/scripts/neo4j_migrate.py
python infra/neo4j/scripts/neo4j_verify.py
```

See [the full local-development guide](../../docs/neo4j-local-development.md).
