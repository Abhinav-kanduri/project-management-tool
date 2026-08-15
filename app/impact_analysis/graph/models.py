from app.impact_analysis.schemas import GraphEdge, GraphNode, GraphResponse


class GraphBatch(GraphResponse):
    """A validated, idempotent set of graph nodes and relationships."""

    def node_rows(self) -> list[dict]:
        return [node.model_dump(mode="json") for node in self.nodes]

    def edge_rows(self) -> list[dict]:
        return [edge.model_dump(mode="json") for edge in self.edges]


__all__ = ["GraphBatch", "GraphEdge", "GraphNode"]
