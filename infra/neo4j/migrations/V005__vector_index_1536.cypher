// This dimension must match OPENAI_EMBEDDING_DIMENSIONS.
CREATE VECTOR INDEX document_chunk_embedding IF NOT EXISTS
FOR (n:DocumentChunk) ON (n.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}};
