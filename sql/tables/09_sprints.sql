create table if not exists public.sprints (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_id uuid not null,
    release_id uuid references public.releases(id),
    name text not null,
    status varchar(30) not null default 'PLANNED',
    start_date date,
    end_date date,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    sprint_number integer,
    display_name text,
    goal text,
    archived_at timestamptz,
    constraint sprints_project_id_fkey
        foreign key (project_id) references public.projects(id) on delete cascade,
    constraint sprints_number_check
        check (sprint_number is null or sprint_number > 0)
);

create unique index if not exists sprints_project_pi_number_idx
    on public.sprints(project_id, release_id, sprint_number)
    where sprint_number is not null;

create index if not exists sprints_pi_idx
    on public.sprints(release_id);
