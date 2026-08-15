create table if not exists public.repository_source_edges (
    id uuid primary key default gen_random_uuid(),
    snapshot_id uuid not null
        references public.repository_snapshots(id) on delete cascade,
    from_file_id uuid references public.repository_source_files(id) on delete cascade,
    from_symbol_id uuid references public.repository_source_symbols(id) on delete cascade,
    to_file_id uuid references public.repository_source_files(id) on delete cascade,
    to_symbol_id uuid references public.repository_source_symbols(id) on delete cascade,
    edge_type varchar(40) not null
        check (edge_type in ('DEFINES','DECLARES_API','IMPORTS','CALLS','USES','TESTS','REFERENCES','READS_FROM','WRITES_TO')),
    target_text text,
    detection_source varchar(30) not null
        check (detection_source in ('PARSER','RESOLVER','MANIFEST','CONFIG','VALIDATED_INFERENCE')),
    confidence numeric(5,4) not null default 1 check (confidence between 0 and 1),
    start_line integer check (start_line is null or start_line > 0),
    end_line integer check (end_line is null or end_line >= start_line),
    metadata jsonb not null default '{}'::jsonb,
    edge_key text not null,
    created_at timestamptz not null default now(),
    unique (snapshot_id, edge_key),
    check (from_file_id is not null or from_symbol_id is not null),
    check (to_file_id is not null or to_symbol_id is not null or target_text is not null)
);

create index if not exists repository_source_edges_snapshot_type_idx
    on public.repository_source_edges(snapshot_id, edge_type);
create index if not exists repository_source_edges_from_symbol_idx
    on public.repository_source_edges(from_symbol_id) where from_symbol_id is not null;
create index if not exists repository_source_edges_to_symbol_idx
    on public.repository_source_edges(to_symbol_id) where to_symbol_id is not null;
