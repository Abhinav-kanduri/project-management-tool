create extension if not exists vector with schema public;

create table if not exists public.github_repository_summary_documents (
    id uuid primary key,
    repository_url text not null,
    repository_owner text not null,
    repository_name text not null,
    repository_full_name text not null,
    branch text not null,
    commit_sha text not null,
    markdown_path text not null,
    chunks_path text,
    manifest_path text,
    summary_sha256 text not null,
    status text not null check (
        status in (
            'SUMMARY_GENERATED', 'CHUNKING', 'EMBEDDING',
            'INDEXING', 'COMPLETED', 'FAILED'
        )
    ),
    chunk_count integer not null default 0 check (chunk_count >= 0),
    summary_format_version text not null,
    summary_model text not null,
    embedding_model text not null,
    embedding_dimensions integer not null check (embedding_dimensions > 0),
    response_payload jsonb not null default '{}'::jsonb,
    error_message text,
    generated_at timestamptz not null,
    indexed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (
        repository_full_name, branch, commit_sha,
        summary_format_version, summary_model,
        embedding_model, embedding_dimensions
    )
);

create table if not exists public.github_repository_summary_chunks (
    id uuid primary key,
    document_id uuid not null references public.github_repository_summary_documents(id)
        on delete cascade,
    chunk_index integer not null check (chunk_index >= 0),
    heading_path jsonb not null default '[]'::jsonb,
    section_title text,
    start_line integer not null check (start_line > 0),
    end_line integer not null check (end_line >= start_line),
    token_count integer not null check (token_count > 0),
    content_sha256 text not null,
    content text not null,
    embedding_model text not null,
    embedding_dimensions integer not null check (embedding_dimensions > 0),
    embedding vector(1536) not null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique(document_id, chunk_index)
);

create index if not exists idx_summary_documents_repository
    on public.github_repository_summary_documents(repository_full_name);
create index if not exists idx_summary_documents_commit
    on public.github_repository_summary_documents(commit_sha);
create index if not exists idx_summary_chunks_document
    on public.github_repository_summary_chunks(document_id);
create index if not exists idx_summary_chunks_section
    on public.github_repository_summary_chunks(section_title);
create index if not exists idx_summary_chunks_embedding_hnsw
    on public.github_repository_summary_chunks
    using hnsw (embedding vector_cosine_ops);
