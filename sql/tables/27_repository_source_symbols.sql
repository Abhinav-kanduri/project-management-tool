create table if not exists public.repository_source_symbols (
    id uuid primary key default gen_random_uuid(),
    snapshot_id uuid not null
        references public.repository_snapshots(id) on delete cascade,
    file_id uuid not null
        references public.repository_source_files(id) on delete cascade,
    symbol_key text not null,
    kind varchar(40) not null
        check (kind in ('MODULE','CLASS','FUNCTION','METHOD','API','SERVICE','TEST','DATABASE_OBJECT','CONFIGURATION','DEPENDENCY')),
    name text not null,
    qualified_name text not null,
    start_line integer not null check (start_line > 0),
    end_line integer not null check (end_line >= start_line),
    signature text,
    visibility varchar(30),
    is_async boolean not null default false,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (snapshot_id, symbol_key)
);

create index if not exists repository_source_symbols_file_kind_idx
    on public.repository_source_symbols(file_id, kind);
create index if not exists repository_source_symbols_snapshot_name_idx
    on public.repository_source_symbols(snapshot_id, name);
create index if not exists repository_source_symbols_snapshot_qualified_idx
    on public.repository_source_symbols(snapshot_id, qualified_name);
