create table if not exists public.repository_source_files (
    id uuid primary key default gen_random_uuid(),
    snapshot_id uuid not null
        references public.repository_snapshots(id) on delete cascade,
    path text not null,
    language text not null,
    blob_sha text,
    content_sha256 text not null,
    size_bytes bigint not null check (size_bytes >= 0),
    line_count integer not null check (line_count >= 0),
    is_generated boolean not null default false,
    is_test boolean not null default false,
    parser_name text,
    parser_version text,
    parser_status varchar(20) not null default 'PENDING'
        check (parser_status in ('PENDING','PARSED','PARTIAL','UNSUPPORTED','FAILED')),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (snapshot_id, path)
);

create index if not exists repository_source_files_snapshot_language_idx
    on public.repository_source_files(snapshot_id, language);
create index if not exists repository_source_files_snapshot_test_idx
    on public.repository_source_files(snapshot_id, is_test) where is_test;
create index if not exists repository_source_files_path_idx
    on public.repository_source_files(path);
