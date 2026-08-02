MERGE (space:ProductSpace {id: 'seed-product-space-gmns'})
ON CREATE SET space.created_at = datetime()
SET space.name = 'GMNS AI Platform', space.updated_at = datetime()
MERGE (project:Project {id: 'seed-project-releaselens'})
ON CREATE SET project.created_at = datetime()
SET project.project_key = 'RLENS', project.name = 'ReleaseLens',
    project.description = 'AI-assisted release planning and knowledge retrieval',
    project.updated_at = datetime()
MERGE (space)-[:CONTAINS_PROJECT]->(project)
MERGE (release:Release {id: 'seed-release-2026-pi-3'})
SET release.name = '2026 PI 3', release.environment = 'development',
    release.status = 'PLANNED', release.start_date = date('2026-07-01'),
    release.end_date = date('2026-09-30')
MERGE (feature:Feature {id: 'seed-feature-knowledge-graph'})
SET feature.feature_key = 'RLENS-F-001', feature.name = 'Knowledge Graph Retrieval',
    feature.description = 'Retrieve project knowledge through graph and semantic relationships',
    feature.status = 'PLANNED'
MERGE (story:UserStory {id: 'seed-story-graph-retrieval'})
SET story.story_key = 'RLENS-101',
    story.title = 'Retrieve documents through graph relationships',
    story.description = 'As a planner, I want graph-aware retrieval so related evidence is easy to discover.',
    story.status = 'BACKLOG'
MERGE (document:Document {id: 'seed-document-architecture'})
ON CREATE SET document.created_at = datetime()
SET document.title = 'ReleaseLens Architecture Overview', document.source = 'development-seed',
    document.source_uri = 'seed://releaselens/architecture', document.status = 'READY',
    document.checksum = 'development-seed-architecture-v1', document.updated_at = datetime()
MERGE (chunk1:DocumentChunk {id: 'seed-chunk-architecture-1'})
SET chunk1.chunk_index = 0,
    chunk1.text = 'ReleaseLens uses PostgreSQL for transactional planning records and Neo4j for graph relationships and RAG traversal.',
    chunk1.token_count = 18, chunk1.created_at = datetime()
MERGE (chunk2:DocumentChunk {id: 'seed-chunk-architecture-2'})
SET chunk2.chunk_index = 1,
    chunk2.text = 'LangChain connects OpenAI embeddings to the Neo4j document chunk vector index for semantic retrieval.',
    chunk2.token_count = 15, chunk2.created_at = datetime()
MERGE (neo4j:Entity {id: 'seed-entity-neo4j'})
SET neo4j.name = 'Neo4j', neo4j.normalized_name = 'neo4j', neo4j.entity_type = 'TECHNOLOGY', neo4j.created_at = datetime()
MERGE (postgres:Entity {id: 'seed-entity-postgresql'})
SET postgres.name = 'PostgreSQL', postgres.normalized_name = 'postgresql', postgres.entity_type = 'TECHNOLOGY', postgres.created_at = datetime()
MERGE (rag:Entity {id: 'seed-entity-rag'})
SET rag.name = 'RAG', rag.normalized_name = 'rag', rag.entity_type = 'PATTERN', rag.created_at = datetime()
MERGE (releaseLens:Entity {id: 'seed-entity-releaselens'})
SET releaseLens.name = 'ReleaseLens', releaseLens.normalized_name = 'releaselens', releaseLens.entity_type = 'PRODUCT', releaseLens.created_at = datetime()
MERGE (project)-[:HAS_RELEASE]->(release)
MERGE (project)-[:HAS_FEATURE]->(feature)
MERGE (project)-[:HAS_DOCUMENT]->(document)
MERGE (release)-[:CONTAINS_FEATURE]->(feature)
MERGE (feature)-[:HAS_USER_STORY]->(story)
MERGE (feature)-[:REFERENCES_DOCUMENT]->(document)
MERGE (story)-[:REFERENCES_DOCUMENT]->(document)
MERGE (document)-[:HAS_CHUNK]->(chunk1)
MERGE (document)-[:HAS_CHUNK]->(chunk2)
MERGE (chunk1)-[:MENTIONS]->(neo4j)
MERGE (chunk1)-[:MENTIONS]->(postgres)
MERGE (chunk1)-[:MENTIONS]->(rag)
MERGE (chunk2)-[:MENTIONS]->(neo4j)
MERGE (chunk2)-[:MENTIONS]->(rag)
MERGE (chunk2)-[:MENTIONS]->(releaseLens)
MERGE (neo4j)-[:RELATED_TO]->(rag)
MERGE (rag)-[:RELATED_TO]->(releaseLens);
