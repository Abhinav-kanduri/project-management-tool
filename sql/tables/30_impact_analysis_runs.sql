create table if not exists public.impact_analysis_runs (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    product_space_id uuid not null references public.product_spaces(id) on delete cascade,
    project_id uuid not null references public.projects(id) on delete cascade,
    release_id uuid references public.releases(id) on delete set null,
    scope_type varchar(20) not null check (scope_type in ('FEATURE','USER_STORY')),
    scope_id uuid not null,
    project_repository_id uuid not null
        references public.project_github_repositories(id) on delete cascade,
    snapshot_id uuid references public.repository_snapshots(id) on delete set null,
    requested_ref text,
    client_request_id uuid not null,
    status varchar(20) not null default 'QUEUED'
        check (status in ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')),
    stage varchar(40) not null default 'SCOPE_RESOLUTION'
        check (stage in ('SCOPE_RESOLUTION','REQUIREMENT_LOADING','DESIGN_CONTEXT','REQUIREMENT_DECOMPOSITION','EXPECTED_GRAPH','GITHUB_SNAPSHOT','SOURCE_PARSING','SOURCE_INDEXING','ACTUAL_GRAPH','EVIDENCE_RETRIEVAL','CONTEXT_BUILDING','LLM_COMPARISON','CLASSIFICATION','SCORING','PERSISTING','COMPLETED','FAILED')),
    progress_percent integer not null default 0 check (progress_percent between 0 and 100),
    message text,
    decomposition_version text not null default 'requirements-v1',
    comparison_version text not null default 'comparison-v1',
    scoring_version text not null default 'completion-v1',
    total_requirements integer not null default 0 check (total_requirements >= 0),
    present_count integer not null default 0 check (present_count >= 0),
    partial_count integer not null default 0 check (partial_count >= 0),
    missing_count integer not null default 0 check (missing_count >= 0),
    unknown_count integer not null default 0 check (unknown_count >= 0),
    score numeric(7,4) check (score between 0 and 100),
    applicable_weight numeric(12,6) check (applicable_weight is null or applicable_weight >= 0),
    excluded_weight numeric(12,6) check (excluded_weight is null or excluded_weight >= 0),
    started_by text not null,
    error_code text,
    error_message text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz not null default now(),
    unique (project_id, client_request_id)
);

create index if not exists impact_analysis_runs_project_created_idx
    on public.impact_analysis_runs(project_id, created_at desc);
create index if not exists impact_analysis_runs_scope_created_idx
    on public.impact_analysis_runs(scope_type, scope_id, created_at desc);
create index if not exists impact_analysis_runs_status_stage_idx
    on public.impact_analysis_runs(status, stage, updated_at);
