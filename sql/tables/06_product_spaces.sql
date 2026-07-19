create table if not exists public.product_spaces (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    name text not null,
    description text,
    archived_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    space_key varchar(20),
    status varchar(30) not null default 'ACTIVE',
    version integer not null default 1,
    unique (organization_id, name)
);

create unique index if not exists product_spaces_org_key_idx
    on public.product_spaces(organization_id, space_key);
