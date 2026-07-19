create table if not exists public.releases (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_id uuid not null,
    name text not null,
    status varchar(30) not null default 'PLANNED',
    start_date date,
    target_date date,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    display_name text,
    year integer,
    pi_number integer,
    description text,
    owner text,
    archived_at timestamptz,
    constraint releases_project_id_fkey
        foreign key (project_id) references public.projects(id) on delete cascade,
    constraint releases_pi_number_check
        check (pi_number is null or pi_number between 1 and 4)
);

create unique index if not exists releases_project_year_pi_idx
    on public.releases(project_id, year, pi_number)
    where year is not null;

create index if not exists releases_project_year_idx
    on public.releases(project_id, year);
