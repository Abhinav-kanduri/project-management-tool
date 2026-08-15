create table if not exists public.impact_findings (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.impact_analysis_runs(id) on delete cascade,
    requirement_id uuid not null references public.impact_requirements(id) on delete cascade,
    status varchar(20) not null check (status in ('PRESENT','PARTIAL','MISSING','UNKNOWN')),
    what_present text not null default '',
    what_missing text not null default '',
    reason_code varchar(60) not null,
    technical_reason text not null,
    explanation text not null,
    impacts jsonb not null default '[]'::jsonb,
    recommendation text not null,
    confidence numeric(5,4) not null check (confidence between 0 and 1),
    completion numeric(3,2) check (completion in (0, 0.5, 1)),
    score_contribution numeric(12,6) check (score_contribution is null or score_contribution >= 0),
    code_generation_available boolean not null default false,
    predicate_results jsonb not null default '[]'::jsonb,
    model_name text,
    prompt_version text not null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (run_id, requirement_id),
    check ((status = 'UNKNOWN' and completion is null) or (status <> 'UNKNOWN' and completion is not null))
);

create index if not exists impact_findings_run_status_idx
    on public.impact_findings(run_id, status);
create index if not exists impact_findings_code_generation_idx
    on public.impact_findings(code_generation_available) where code_generation_available;
