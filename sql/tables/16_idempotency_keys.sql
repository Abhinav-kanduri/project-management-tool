create table if not exists public.idempotency_keys (
    key text primary key,
    project_id uuid not null,
    response jsonb,
    created_at timestamptz not null default now(),
    constraint idempotency_keys_project_id_fkey
        foreign key (project_id) references public.projects(id) on delete cascade
);
