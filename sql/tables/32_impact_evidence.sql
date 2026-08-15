create table if not exists public.impact_evidence (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.impact_analysis_runs(id) on delete cascade,
    requirement_id uuid not null references public.impact_requirements(id) on delete cascade,
    snapshot_id uuid references public.repository_snapshots(id) on delete set null,
    evidence_type varchar(40) not null
        check (evidence_type in ('SOURCE_CODE','TEST','CONFIGURATION','DATABASE_MIGRATION','DEPENDENCY','ARCHITECTURE_DOCUMENT','KNOWLEDGE_BASE','GRAPH_PATH','RETRIEVAL_TRACE','REPOSITORY_SUMMARY')),
    direction varchar(30) not null
        check (direction in ('SUPPORTS','CONTRADICTS','CONTEXT','SEARCHED_NO_MATCH')),
    retrieval_method varchar(40) not null,
    source_ref text,
    file_id uuid references public.repository_source_files(id) on delete set null,
    symbol_id uuid references public.repository_source_symbols(id) on delete set null,
    chunk_id uuid references public.repository_source_chunks(id) on delete set null,
    file_path text,
    symbol text,
    start_line integer check (start_line is null or start_line > 0),
    end_line integer check (end_line is null or end_line >= start_line),
    description text not null,
    excerpt text,
    content_sha256 text,
    rank integer check (rank is null or rank > 0),
    score numeric,
    metadata jsonb not null default '{}'::jsonb,
    evidence_key text not null,
    created_at timestamptz not null default now(),
    unique (run_id, requirement_id, evidence_key),
    check ((start_line is null and end_line is null) or (start_line is not null and end_line is not null))
);

create index if not exists impact_evidence_requirement_type_idx
    on public.impact_evidence(requirement_id, evidence_type);
create index if not exists impact_evidence_file_symbol_idx
    on public.impact_evidence(file_id, symbol_id);
create index if not exists impact_evidence_snapshot_idx
    on public.impact_evidence(snapshot_id) where snapshot_id is not null;
