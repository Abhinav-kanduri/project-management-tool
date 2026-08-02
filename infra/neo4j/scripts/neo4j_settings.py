from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

NEO4J_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = NEO4J_ROOT.parents[1]


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str
    username: str
    password: str
    database: str


def load_settings() -> Neo4jSettings:
    load_dotenv(NEO4J_ROOT / ".env", override=False)
    values = {
        "uri": os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
        "username": os.getenv("NEO4J_USERNAME", "neo4j"),
        "password": os.getenv("NEO4J_PASSWORD", ""),
        "database": os.getenv("NEO4J_DATABASE", "neo4j"),
    }
    if not values["password"]:
        raise RuntimeError(
            "NEO4J_PASSWORD is missing. Run generate_env.py or create infra/neo4j/.env."
        )
    return Neo4jSettings(**values)
