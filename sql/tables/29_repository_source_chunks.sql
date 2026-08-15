create table if not exists public.repository_source_chunks (
    id uuid primary key default gen_random_uuid(),
    snapshot_id uuid not null
        references public.repository_snapshots(id) on delete cascade,
    file_id uuid not null
        references public.repository_source_files(id) on delete cascade,
    symbol_id uuid references public.repository_source_symbols(id) on delete set null,
    chunk_key text not null,
    chunk_type varchar(30) not null
        check (chunk_type in ('FILE_HEADER','IMPORT_BLOCK','CLASS','FUNCTION','METHOD','API','TEST','MIGRATION','CONFIGURATION','GENERIC')),
    start_line integer not null check (start_line > 0),
    end_line integer not null check (end_line >= start_line),
    content text not null,
    content_sha256 text not null,
    token_count integer not null check (token_count > 0),
    embedding vector(1536),
    embedding_model text,
    embedding_dimensions integer check (embedding_dimensions is null or embedding_dimensions = 1536),
    search_vector tsvector generated always as (to_tsvector('english', content)) stored,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (snapshot_id, chunk_key)
);

create index if not exists repository_source_chunks_file_idx
    on public.repository_source_chunks(file_id, start_line);
create index if not exists repository_source_chunks_symbol_idx
    on public.repository_source_chunks(symbol_id) where symbol_id is not null;
create index if not exists repository_source_chunks_fts_idx
    on public.repository_source_chunks using gin(search_vector);
create index if not exists repository_source_chunks_embedding_hnsw_idx
    on public.repository_source_chunks using hnsw (embedding vector_cosine_ops)
    where embedding is not null;
