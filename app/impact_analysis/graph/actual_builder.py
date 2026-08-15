from __future__ import annotations

from uuid import UUID, uuid5

from app.impact_analysis.enums import GraphNodeType, GraphRelationshipType
from app.impact_analysis.graph.models import GraphBatch, GraphEdge, GraphNode


ACTUAL_NAMESPACE = UUID("6276282d-d2a7-4941-9f9b-c4e5413c7653")


class ActualGraphBuilder:
    def build(
        self,
        *,
        run_id: UUID,
        snapshot_id: UUID,
        repository_name: str,
        project_id: UUID,
        rows: dict[str, list[dict]],
    ) -> GraphBatch:
        nodes: dict[str, GraphNode] = {}
        edges: dict[str, GraphEdge] = {}
        snapshot_node = f"snapshot:{snapshot_id}"
        nodes[snapshot_node] = GraphNode(
            id=snapshot_node,
            type=GraphNodeType.REPOSITORY_SNAPSHOT,
            label=repository_name,
            properties={
                "source_id": str(snapshot_id),
                "snapshot_id": str(snapshot_id),
                "project_id": str(project_id),
                "truth_side": "ACTUAL",
            },
        )
        file_nodes: dict[UUID, str] = {}
        symbol_nodes: dict[UUID, str] = {}
        symbols_by_name: dict[str, str] = {}
        for file in rows["files"]:
            node_id = f"file:{file['id']}"
            file_nodes[file["id"]] = node_id
            nodes[node_id] = GraphNode(
                id=node_id,
                type=GraphNodeType.FILE,
                label=file["path"],
                properties={
                    "source_id": str(file["id"]),
                    "snapshot_id": str(snapshot_id),
                    "project_id": str(project_id),
                    "path": file["path"],
                    "language": file["language"],
                    "truth_side": "ACTUAL",
                },
            )
            edge_id = f"{run_id}:{snapshot_node}:CONTAINS_FILE:{node_id}"
            edges[edge_id] = GraphEdge(
                id=edge_id,
                type=GraphRelationshipType.CONTAINS_FILE,
                source=snapshot_node,
                target=node_id,
            )
        for symbol in rows["symbols"]:
            node_id = f"symbol:{symbol['id']}"
            symbol_nodes[symbol["id"]] = node_id
            symbols_by_name[symbol["name"].casefold()] = node_id
            symbols_by_name[symbol["qualified_name"].casefold()] = node_id
            nodes[node_id] = GraphNode(
                id=node_id,
                type=self._node_type(symbol["kind"]),
                label=symbol["qualified_name"],
                properties={
                    "source_id": str(symbol["id"]),
                    "snapshot_id": str(snapshot_id),
                    "project_id": str(project_id),
                    "file_id": str(symbol["file_id"]),
                    "kind": symbol["kind"],
                    "name": symbol["name"],
                    "qualified_name": symbol["qualified_name"],
                    "start_line": symbol["start_line"],
                    "end_line": symbol["end_line"],
                    "truth_side": "ACTUAL",
                },
            )
            file_node = file_nodes[symbol["file_id"]]
            edge_id = f"{run_id}:{file_node}:DEFINES:{node_id}"
            edges[edge_id] = GraphEdge(
                id=edge_id,
                type=GraphRelationshipType.DEFINES,
                source=file_node,
                target=node_id,
            )
        for edge in rows["edges"]:
            source = symbol_nodes.get(edge.get("from_symbol_id")) or file_nodes.get(
                edge.get("from_file_id")
            )
            if not source:
                continue
            target = symbol_nodes.get(edge.get("to_symbol_id"))
            target_text = edge.get("target_text") or ""
            if not target and target_text:
                target = self._resolve_target(target_text, symbols_by_name)
            if not target and target_text:
                placeholder_id = f"unresolved:{uuid5(ACTUAL_NAMESPACE, f'{snapshot_id}:{target_text}')}"
                nodes.setdefault(
                    placeholder_id,
                    GraphNode(
                        id=placeholder_id,
                        type=(
                            GraphNodeType.DEPENDENCY
                            if edge["edge_type"] == "IMPORTS"
                            else GraphNodeType.FUNCTION
                        ),
                        label=target_text,
                        properties={
                            "snapshot_id": str(snapshot_id),
                            "project_id": str(project_id),
                            "truth_side": "ACTUAL",
                            "resolved": False,
                        },
                    ),
                )
                target = placeholder_id
            if not target:
                continue
            relationship = self._relationship(edge["edge_type"])
            edge_id = f"{run_id}:{edge['edge_key']}"
            edges[edge_id] = GraphEdge(
                id=edge_id,
                type=relationship,
                source=source,
                target=target,
                confidence=float(edge["confidence"]),
            )
        return GraphBatch(nodes=list(nodes.values()), edges=list(edges.values()))

    @staticmethod
    def _resolve_target(target: str, symbols: dict[str, str]) -> str | None:
        lowered = target.casefold()
        if lowered in symbols:
            return symbols[lowered]
        leaf = lowered.rsplit(".", 1)[-1]
        return symbols.get(leaf)

    @staticmethod
    def _node_type(kind: str) -> GraphNodeType:
        return {
            "CLASS": GraphNodeType.CLASS,
            "SERVICE": GraphNodeType.SERVICE,
            "FUNCTION": GraphNodeType.FUNCTION,
            "METHOD": GraphNodeType.FUNCTION,
            "API": GraphNodeType.API,
            "TEST": GraphNodeType.TEST,
            "DATABASE_OBJECT": GraphNodeType.DATABASE,
            "CONFIGURATION": GraphNodeType.COMPONENT,
            "DEPENDENCY": GraphNodeType.DEPENDENCY,
        }.get(kind, GraphNodeType.COMPONENT)

    @staticmethod
    def _relationship(value: str) -> GraphRelationshipType:
        return {
            "DEFINES": GraphRelationshipType.DEFINES,
            "DECLARES_API": GraphRelationshipType.DECLARES_API,
            "IMPORTS": GraphRelationshipType.IMPORTS,
            "CALLS": GraphRelationshipType.CALLS,
            "USES": GraphRelationshipType.USES,
            "TESTS": GraphRelationshipType.TESTED_BY,
            "READS_FROM": GraphRelationshipType.USES,
            "WRITES_TO": GraphRelationshipType.USES,
        }.get(value, GraphRelationshipType.USES)
