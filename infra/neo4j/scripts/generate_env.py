from __future__ import annotations

import secrets
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def main() -> int:
    if ENV_FILE.exists():
        print("Neo4j environment already exists; leaving it unchanged.")
        return 0
    password = secrets.token_urlsafe(24)
    ENV_FILE.write_text(
        "\n".join(
            (
                "NEO4J_USERNAME=neo4j",
                f"NEO4J_PASSWORD={password}",
                "NEO4J_DATABASE=neo4j",
                "NEO4J_URI=neo4j://localhost:7687",
                "NEO4J_HTTP_PORT=7474",
                "NEO4J_BOLT_PORT=7687",
                "NEO4J_VECTOR_DIMENSIONS=1536",
                "",
            )
        ),
        encoding="utf-8",
    )
    print("Created infra/neo4j/.env with a generated local password (not displayed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
