from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException
from neo4j.exceptions import DriverError, Neo4jError
from pydantic import BaseModel, Field

from app.config import NEO4J_DATABASE, NEO4J_ENABLED, NEO4J_URI
from app.neo4j_client import get_neo4j_client
from app.services.graph_rag import graph_schema, semantic_search

router = APIRouter(prefix="/api/v1/graph", tags=["Graph RAG"])


class GraphSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    k: int = Field(default=5, ge=1, le=20)


def unavailable(error: Exception) -> NoReturn:
    raise HTTPException(
        status_code=503,
        detail={
            "code": "NEO4J_UNAVAILABLE",
            "message": "The local Neo4j graph service is unavailable.",
        },
    ) from error


@router.get("/health")
def graph_health() -> dict[str, Any]:
    if not NEO4J_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NEO4J_NOT_CONFIGURED",
                "message": "Create infra/neo4j/.env.",
            },
        )
    try:
        client = get_neo4j_client()
        client.verify_connectivity()
        version = client.execute_read(
            "CALL dbms.components() YIELD versions RETURN versions[0] AS version"
        )[0]["version"]
        return {
            "status": "ok",
            "uri": NEO4J_URI,
            "database": NEO4J_DATABASE,
            "version": version,
            "framework": "LangChain",
        }
    except (DriverError, Neo4jError, RuntimeError, OSError) as error:
        unavailable(error)


@router.get("/schema")
def schema() -> dict[str, str]:
    try:
        return {"schema": graph_schema()}
    except (DriverError, Neo4jError, RuntimeError, OSError) as error:
        unavailable(error)


@router.post("/search")
def search(request: GraphSearchRequest) -> dict[str, Any]:
    try:
        results = semantic_search(request.query, request.k)
        return {"query": request.query, "results": results, "count": len(results)}
    except (DriverError, Neo4jError, RuntimeError, OSError) as error:
        unavailable(error)
