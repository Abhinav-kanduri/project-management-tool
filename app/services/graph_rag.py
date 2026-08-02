from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_neo4j import Neo4jGraph, Neo4jVector
from langchain_openai import OpenAIEmbeddings

from app.config import (
    NEO4J_DATABASE,
    NEO4J_ENABLED,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USERNAME,
    NEO4J_VECTOR_INDEX,
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_DIMENSIONS,
    OPENAI_EMBEDDING_MODEL,
)


def _connection_kwargs() -> dict[str, Any]:
    if not NEO4J_ENABLED or not NEO4J_PASSWORD:
        raise RuntimeError("Neo4j is not configured.")
    return {
        "url": NEO4J_URI,
        "username": NEO4J_USERNAME,
        "password": NEO4J_PASSWORD,
        "database": NEO4J_DATABASE,
    }


@lru_cache(maxsize=1)
def get_graph() -> Neo4jGraph:
    """Return LangChain's graph wrapper without refreshing schema on every request."""
    return Neo4jGraph(**_connection_kwargs(), refresh_schema=False)


@lru_cache(maxsize=1)
def get_vector_store() -> Neo4jVector:
    embeddings = OpenAIEmbeddings(
        api_key=OPENAI_API_KEY,
        model=OPENAI_EMBEDDING_MODEL,
        dimensions=OPENAI_EMBEDDING_DIMENSIONS,
    )
    return Neo4jVector.from_existing_index(
        embeddings,
        **_connection_kwargs(),
        index_name=NEO4J_VECTOR_INDEX,
        node_label="DocumentChunk",
        text_node_property="text",
        embedding_node_property="embedding",
    )


def graph_schema() -> str:
    graph = get_graph()
    graph.refresh_schema()
    return graph.schema


def semantic_search(query: str, k: int = 5) -> list[dict[str, Any]]:
    results = get_vector_store().similarity_search_with_score(query, k=k)
    return [
        {
            "text": document.page_content,
            "score": score,
            "metadata": document.metadata,
        }
        for document, score in results
    ]


def close_langchain_resources() -> None:
    """Close integration-owned drivers while tolerating LangChain API changes."""
    for factory in (get_vector_store, get_graph):
        if not factory.cache_info().currsize:
            continue
        resource = factory()
        close = getattr(resource, "close", None)
        if callable(close):
            close()
        else:
            driver = getattr(resource, "_driver", None)
            if driver is not None:
                driver.close()
        factory.cache_clear()
