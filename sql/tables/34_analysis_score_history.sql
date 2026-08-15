create table if not exists public.analysis_score_history (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    product_space_id uuid not null references public.product_spaces(id) on delete cascade,
    project_id uuid not null references public.projects(id) on delete cascade,
    scope_type varchar(20) not null check (scope_type in ('FEATURE','USER_STORY')),
    scope_id uuid not null,
    run_id uuid not null references public.impact_analysis_runs(id) on delete cascade,
    score numeric(7,4) check (score between 0 and 100),
    applicable_weight numeric(12,6) not null check (applicable_weight >= 0),
    excluded_weight numeric(12,6) not null check (excluded_weight >= 0),
    present_count integer not null default 0 check (present_count >= 0),
    partial_count integer not null default 0 check (partial_count >= 0),
    missing_count integer not null default 0 check (missing_count >= 0),
    unknown_count integer not null default 0 check (unknown_count >= 0),
    calculation_version text not null,
    created_at timestamptz not null default now(),
    unique (run_id)
);

create index if not exists analysis_score_history_scope_created_idx
    on public.analysis_score_history(project_id, scope_type, scope_id, created_at desc);
