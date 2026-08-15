CREATE INDEX impact_node_project IF NOT EXISTS
FOR (n:ImpactNode) ON (n.project_id);

CREATE INDEX impact_node_run IF NOT EXISTS
FOR (n:ImpactNode) ON (n.run_id);

CREATE INDEX impact_node_snapshot IF NOT EXISTS
FOR (n:ImpactNode) ON (n.snapshot_id);

CREATE INDEX impact_node_type IF NOT EXISTS
FOR (n:ImpactNode) ON (n.node_type);

CREATE INDEX requirement_key IF NOT EXISTS
FOR (n:ImpactNode) ON (n.requirement_key);
