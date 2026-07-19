create table if not exists public.projects (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null,
    project_key varchar(20) not null,
    name text not null,
    owner_name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    description text,
    status varchar(30) not null default 'ACTIVE',
    health varchar(30) not null default 'ON_TRACK',
    version integer not null default 1,
    archived_at timestamptz,
    constraint projects_product_space_id_fkey
        foreign key (product_space_id) references public.product_spaces(id) on delete cascade,
    unique (organization_id, project_key)
);
