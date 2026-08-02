CREATE FULLTEXT INDEX document_search IF NOT EXISTS
FOR (n:Document) ON EACH [n.title];

CREATE FULLTEXT INDEX document_chunk_search IF NOT EXISTS
FOR (n:DocumentChunk) ON EACH [n.text];

CREATE FULLTEXT INDEX entity_search IF NOT EXISTS
FOR (n:Entity) ON EACH [n.name, n.normalized_name];

CREATE FULLTEXT INDEX planning_search IF NOT EXISTS
FOR (n:Feature|UserStory) ON EACH [n.name, n.description, n.title];
