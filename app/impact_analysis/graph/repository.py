from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.impact_analysis.enums import GraphNodeType, GraphRelationshipType
from app.impact_analysis.graph.models import GraphBatch
from app.impact_analysis.graph.policy import node_label, relationship_type
from app.neo4j_client import Neo4jClient, get_neo4j_client


class ImpactGraphRepository:
    def __init__(self, client: Neo4jClient | None = None) -> None:
        self.client = client or get_neo4j_client()

    def upsert(self, batch: GraphBatch, *, run_id: str) -> None:
        node_groups: dict[GraphNodeType, list[dict[str, Any]]] = defaultdict(list)
        for node in batch.nodes:
            node_groups[node.type].append(
                {
                    "id": node.id,
                    "label": node.label,
                    "properties": node.properties,
                    "type": node.type.value,
                }
            )
        for node_type, rows in node_groups.items():
            label = node_label(node_type)
            self.client.execute_write(
                f"""
                UNWIND $rows AS row
                MERGE (n:ImpactNode:{label} {{id: row.id}})
                SET n.display_label=row.label, n.node_type=row.type,
                    n += row.properties, n.updated_at=datetime()
                """,
                {"rows": rows},
            )

        edge_groups: dict[GraphRelationshipType, list[dict[str, Any]]] = defaultdict(list)
        for edge in batch.edges:
            edge_groups[edge.type].append(
                {
                    "id": edge.id,
                    "source": edge.source,
                    "target": edge.target,
                    "confidence": edge.confidence,
                    "inferred": edge.inferred,
                    "evidence_ids": [str(item) for item in edge.evidence_ids],
                    "run_id": run_id,
                }
            )
        for edge_type, rows in edge_groups.items():
            relationship = relationship_type(edge_type)
            self.client.execute_write(
                f"""
                UNWIND $rows AS row
                MATCH (source:ImpactNode {{id: row.source}})
                MATCH (target:ImpactNode {{id: row.target}})
                MERGE (source)-[r:{relationship} {{id: row.id}}]->(target)
                SET r.confidence=row.confidence, r.inferred=row.inferred,
                    r.evidence_ids=row.evidence_ids, r.run_id=row.run_id,
                    r.updated_at=datetime()
                """,
                {"rows": rows},
            )

    def subgraph(self, *, run_id: str) -> dict[str, list[dict[str, Any]]]:
        rows = self.client.execute_read(
            """
            MATCH (source:ImpactNode)-[r]->(target:ImpactNode)
            WHERE r.run_id=$run_id
            RETURN source, r, target
            ORDER BY r.id
            """,
            {"run_id": run_id},
        )
        nodes: dict[str, dict[str, Any]] = {}
        edges = []
        for row in rows:
            source = dict(row["source"])
            target = dict(row["target"])
            relation = dict(row["r"])
            nodes[source["id"]] = source
            nodes[target["id"]] = target
            edges.append(relation)
        return {"nodes": list(nodes.values()), "edges": edges}
