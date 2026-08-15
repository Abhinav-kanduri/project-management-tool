from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time

from app.neo4j_client import Neo4jClient, get_neo4j_client


class ImpactGraphContractView:
    def __init__(self, client: Neo4jClient | None = None) -> None:
        self.client = client or get_neo4j_client()

    def get(self, *, run_id: str, view: str) -> dict:
        rows = self.client.execute_read(
            """
            MATCH (source:ImpactNode)-[r]->(target:ImpactNode)
            WHERE r.run_id=$run_id
              AND ($view='comparison' OR
                   ($view='expected' AND source.truth_side='EXPECTED'
                    AND target.truth_side='EXPECTED') OR
                   ($view='actual' AND source.truth_side='ACTUAL'
                    AND target.truth_side='ACTUAL'))
            RETURN properties(source) AS source_properties,
                   source.id AS source_id,
                   type(r) AS relationship_type,
                   properties(r) AS relationship,
                   properties(target) AS target_properties,
                   target.id AS target_id
            ORDER BY r.id
            """,
            {"run_id": run_id, "view": view},
        )
        nodes = {}
        edges = []
        for row in rows:
            for key, identifier in (
                ("source_properties", row["source_id"]),
                ("target_properties", row["target_id"]),
            ):
                value = self._json_safe(dict(row[key]))
                truth = str(value.get("truth_side") or "").casefold()
                nodes[identifier] = {
                    "id": identifier,
                    "label": value.get("display_label") or value.get("label") or identifier,
                    "type": value.get("node_type"),
                    "status": self._node_status(view, truth),
                    "group": truth or None,
                    "metadata": value,
                }
            relationship = self._json_safe(dict(row["relationship"]))
            edges.append(
                {
                    "id": relationship.get("id"),
                    "source": row["source_id"],
                    "target": row["target_id"],
                    "type": row["relationship_type"],
                    "label": row["relationship_type"].replace("_", " ").casefold(),
                    "status": "unknown" if view == "comparison" else None,
                    "metadata": relationship,
                }
            )
        return {"view": view, "nodes": list(nodes.values()), "edges": edges}

    @classmethod
    def _json_safe(cls, value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Mapping):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [cls._json_safe(item) for item in value]
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        iso_format = getattr(value, "iso_format", None)
        if callable(iso_format):
            return iso_format()
        return str(value)

    @staticmethod
    def _node_status(view: str, truth: str) -> str | None:
        if view != "comparison":
            return None
        return "matching" if truth == "actual" else "unknown"
