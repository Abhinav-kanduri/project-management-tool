from __future__ import annotations

import sys

from neo4j import GraphDatabase
from neo4j.exceptions import DriverError, Neo4jError

from neo4j_settings import load_settings

EXPECTED_CONSTRAINTS = {
    "graph_migration_version",
    "product_space_id",
    "project_id",
    "project_key",
    "document_id",
    "document_chunk_id",
    "entity_id",
    "release_id",
    "feature_id",
    "feature_key",
    "user_story_id",
    "user_story_key",
}
EXPECTED_INDEXES = {
    "project_name",
    "document_status",
    "document_checksum",
    "entity_normalized_name",
    "entity_type",
    "release_environment",
    "release_status",
    "feature_status",
    "user_story_status",
    "document_search",
    "document_chunk_search",
    "entity_search",
    "planning_search",
    "document_chunk_embedding",
}


def scalar(driver, database: str, query: str, key: str):
    records, _, _ = driver.execute_query(query, database_=database)
    if not records:
        raise RuntimeError(f"Verification query returned no rows: {query}")
    return records[0][key]


def main() -> int:
    settings = load_settings()
    driver = GraphDatabase.driver(settings.uri, auth=(settings.username, settings.password))
    failures: list[str] = []
    try:
        driver.verify_connectivity()
        version = scalar(
            driver,
            settings.database,
            "CALL dbms.components() YIELD versions RETURN versions[0] AS value",
            "value",
        )
        apoc = scalar(driver, settings.database, "RETURN apoc.version() AS value", "value")
        gds = scalar(
            driver,
            settings.database,
            "CALL gds.version() YIELD gdsVersion RETURN gdsVersion AS value",
            "value",
        )
        constraint_records, _, _ = driver.execute_query(
            "SHOW CONSTRAINTS YIELD name RETURN name", database_=settings.database
        )
        constraints = {record["name"] for record in constraint_records}
        missing_constraints = EXPECTED_CONSTRAINTS - constraints
        if missing_constraints:
            failures.append(f"missing constraints: {sorted(missing_constraints)}")
        index_records, _, _ = driver.execute_query(
            "SHOW INDEXES YIELD name, state RETURN name, state", database_=settings.database
        )
        indexes = {record["name"]: record["state"] for record in index_records}
        missing_indexes = EXPECTED_INDEXES - indexes.keys()
        if missing_indexes:
            failures.append(f"missing indexes: {sorted(missing_indexes)}")
        offline = {
            name: state
            for name, state in indexes.items()
            if name in EXPECTED_INDEXES and state != "ONLINE"
        }
        if offline:
            failures.append(f"indexes not online: {offline}")
        path_count = scalar(
            driver,
            settings.database,
            "MATCH (:ProductSpace {name: 'GMNS AI Platform'})-[:CONTAINS_PROJECT]->"
            "(:Project {project_key: 'RLENS'})-[:HAS_FEATURE]->"
            "(:Feature {feature_key: 'RLENS-F-001'})-[:HAS_USER_STORY]->"
            "(:UserStory {story_key: 'RLENS-101'}) RETURN count(*) AS value",
            "value",
        )
        if path_count != 1:
            failures.append(f"expected one connected seed path, found {path_count}")
        fulltext_count = scalar(
            driver,
            settings.database,
            "CALL db.index.fulltext.queryNodes('document_chunk_search', 'Neo4j AND RAG') "
            "YIELD node RETURN count(node) AS value",
            "value",
        )
        if fulltext_count < 1:
            failures.append("full-text query returned no seed chunks")
        migration_count = scalar(
            driver,
            settings.database,
            "MATCH (m:GraphMigration) RETURN count(m) AS value",
            "value",
        )
        print(f"Neo4j version: {version}")
        print(f"Database: {settings.database}")
        print(f"APOC version: {apoc}")
        print(f"GDS version: {gds}")
        print(f"Migrations: {migration_count}")
        if failures:
            for failure in failures:
                print(f"FAILED: {failure}", file=sys.stderr)
            return 1
        print("Verification passed.")
        return 0
    except (DriverError, Neo4jError, RuntimeError) as error:
        print(f"Neo4j verification failed: {error}", file=sys.stderr)
        return 1
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
