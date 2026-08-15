from app.impact_analysis.enums import GraphNodeType, GraphRelationshipType


NODE_LABELS: dict[GraphNodeType, str] = {
    item: "RepositorySnapshot" if item == GraphNodeType.REPOSITORY_SNAPSHOT else item.value.title().replace("_", "")
    for item in GraphNodeType
}

RELATIONSHIP_TYPES = {item.value for item in GraphRelationshipType}


def node_label(node_type: GraphNodeType) -> str:
    return NODE_LABELS[node_type]


def relationship_type(value: GraphRelationshipType) -> str:
    if value.value not in RELATIONSHIP_TYPES:
        raise ValueError(f"Unsupported relationship type: {value}")
    return value.value
