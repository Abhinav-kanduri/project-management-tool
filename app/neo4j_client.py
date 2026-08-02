from __future__ import annotations

from threading import Lock
from typing import Any

from neo4j import Driver, GraphDatabase, RoutingControl

from app.config import (
    NEO4J_DATABASE,
    NEO4J_ENABLED,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USERNAME,
)


class Neo4jClient:
    """Process-scoped Neo4j driver with parameterized read/write helpers."""

    def __init__(self) -> None:
        if not NEO4J_ENABLED or not NEO4J_PASSWORD:
            raise RuntimeError(
                "Neo4j is not configured. Create infra/neo4j/.env first."
            )
        self._driver: Driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
        )

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    def execute_read(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        records, _, _ = self._driver.execute_query(
            query,
            parameters_=parameters or {},
            database_=NEO4J_DATABASE,
            routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]

    def execute_write(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        records, _, _ = self._driver.execute_query(
            query,
            parameters_=parameters or {},
            database_=NEO4J_DATABASE,
            routing_=RoutingControl.WRITE,
        )
        return [record.data() for record in records]

    def close(self) -> None:
        self._driver.close()


_client: Neo4jClient | None = None
_client_lock = Lock()


def get_neo4j_client() -> Neo4jClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = Neo4jClient()
    return _client


def close_neo4j_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
