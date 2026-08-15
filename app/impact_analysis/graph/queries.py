EXPECTED_GRAPH_QUERY = """
MATCH (source:ImpactNode)-[r]->(target:ImpactNode)
WHERE r.run_id=$run_id
  AND coalesce(source.truth_side, 'EXPECTED')='EXPECTED'
  AND coalesce(target.truth_side, 'EXPECTED')='EXPECTED'
RETURN source, r, target
ORDER BY r.id
"""
