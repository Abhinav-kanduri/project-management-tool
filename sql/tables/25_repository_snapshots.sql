create table if not exists public.repository_snapshots (
    id uuid primary key default gen_random_uuid(),
    project_repository_id uuid not null
        references public.project_github_repositories(id) on delete cascade,
    repository_id uuid not null
        references public.github_repositories(id) on delete cascade,
    product_space_id uuid not null
        references public.product_spaces(id) on delete cascade,
    project_id uuid not null
        references public.projects(id) on delete cascade,
    branch text not null,
    commit_sha text not null,
    tree_sha text,
    status varchar(30) not null default 'PENDING'
        check (status in ('PENDING','DOWNLOADING','SCANNING','INDEXING','COMPLETED','FAILED')),
    scanner_version text not null,
    manifest jsonb not null default '[]'::jsonb,
    discovered_files integer not null default 0 check (discovered_files >= 0),
    indexed_files integer not null default 0 check (indexed_files >= 0),
    skipped_files integer not null default 0 check (skipped_files >= 0),
    coverage_percent numeric(5,2) check (coverage_percent between 0 and 100),
    error_code text,
    error_message text,
    created_at timestamptz not null default now(),
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz not null default now(),
    unique (project_repository_id, commit_sha, scanner_version)
);

create index if not exists repository_snapshots_project_created_idx
    on public.repository_snapshots(project_id, created_at desc);
create index if not exists repository_snapshots_repository_commit_idx
    on public.repository_snapshots(repository_id, commit_sha);
create index if not exists repository_snapshots_status_idx
    on public.repository_snapshots(status, updated_at);
