create table if not exists public.generated_change_validations (
    id uuid primary key default gen_random_uuid(),
    generated_change_id uuid not null references public.generated_changes(id) on delete cascade,
    check_type varchar(30) not null
        check (check_type in ('PATH_SAFETY','FORMAT','LINT','COMPILE','TYPE_CHECK','UNIT_TEST','INTEGRATION_TEST','SECURITY','POLICY')),
    command text,
    status varchar(20) not null check (status in ('PENDING','RUNNING','PASSED','FAILED','SKIPPED','TIMED_OUT')),
    exit_code integer,
    log_excerpt text,
    artifact_ref text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists generated_change_validations_change_idx
    on public.generated_change_validations(generated_change_id, created_at);
create index if not exists generated_change_validations_status_idx
    on public.generated_change_validations(status, check_type);
