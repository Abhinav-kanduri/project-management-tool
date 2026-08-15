create table if not exists public.generated_changes (
    id uuid primary key default gen_random_uuid(),
    finding_id uuid not null references public.impact_findings(id) on delete cascade,
    snapshot_id uuid not null references public.repository_snapshots(id) on delete restrict,
    status varchar(30) not null default 'REQUESTED'
        check (status in ('REQUESTED','GENERATING','GENERATED','VALIDATING','VALIDATION_FAILED','VALIDATED','APPROVED','REJECTED','PR_CREATED','MERGED','FAILED')),
    prompt_version text not null,
    base_commit_sha text not null,
    proposed_files jsonb not null default '[]'::jsonb,
    patch text,
    explanation text,
    tests_proposed jsonb not null default '[]'::jsonb,
    validation_summary jsonb not null default '{}'::jsonb,
    requested_by text not null,
    approved_by text,
    approval_comment text,
    approved_at timestamptz,
    branch_name text,
    commit_sha text,
    pull_request_number bigint,
    pull_request_url text,
    metadata jsonb not null default '{}'::jsonb,
    error_code text,
    error_message text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists generated_changes_finding_created_idx
    on public.generated_changes(finding_id, created_at desc);
create index if not exists generated_changes_status_idx
    on public.generated_changes(status, updated_at);
