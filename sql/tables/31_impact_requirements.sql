create table if not exists public.impact_requirements (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.impact_analysis_runs(id) on delete cascade,
    requirement_key varchar(30) not null,
    requirement_text text not null,
    requirement_type varchar(50) not null,
    applicability varchar(40) not null default 'STATICALLY_VERIFIABLE'
        check (applicability in ('STATICALLY_VERIFIABLE','RUNTIME_EVIDENCE_REQUIRED','EXTERNAL_EVIDENCE_REQUIRED')),
    source_type varchar(50) not null,
    source_id text not null,
    source_locator jsonb not null default '{}'::jsonb,
    provenance jsonb not null default '[]'::jsonb,
    weight numeric(10,6) not null check (weight > 0 and weight <= 1),
    expected_predicates jsonb not null default '[]'::jsonb,
    decomposition_metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (run_id, requirement_key)
);

create index if not exists impact_requirements_run_type_idx
    on public.impact_requirements(run_id, requirement_type);
create index if not exists impact_requirements_source_idx
    on public.impact_requirements(source_type, source_id);
