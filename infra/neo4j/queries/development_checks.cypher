CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions[0] AS version, edition;
RETURN apoc.version();
CALL gds.version() YIELD gdsVersion RETURN gdsVersion;
SHOW CONSTRAINTS;
SHOW INDEXES;

MATCH (n)
RETURN labels(n) AS labels, count(*) AS count
ORDER BY count DESC;

MATCH path =
  (:ProductSpace {name: 'GMNS AI Platform'})-[:CONTAINS_PROJECT]->
  (:Project {project_key: 'RLENS'})-[:HAS_FEATURE]->
  (:Feature {feature_key: 'RLENS-F-001'})-[:HAS_USER_STORY]->
  (:UserStory {story_key: 'RLENS-101'})
RETURN path;

MATCH (d:Document)-[:HAS_CHUNK]->(chunk:DocumentChunk)
RETURN d.title, chunk.chunk_index, chunk.text
ORDER BY chunk.chunk_index;

CALL db.index.fulltext.queryNodes('document_chunk_search', 'Neo4j AND RAG')
YIELD node, score
RETURN node.id, node.text, score
ORDER BY score DESC;
