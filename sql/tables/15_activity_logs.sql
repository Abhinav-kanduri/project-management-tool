create table if not exists public.activity_logs (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_id uuid not null references public.projects(id),
    entity_type varchar(50) not null,
    entity_id uuid,
    action varchar(80) not null,
    performed_by text not null default 'local-user',
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists activity_project_idx
    on public.activity_logs(project_id, created_at desc);
