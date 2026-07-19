create table if not exists public.organization_members (
    organization_id uuid not null references public.organizations(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role varchar(40) not null default 'VIEWER',
    created_at timestamptz not null default now(),
    primary key (organization_id, user_id)
);
