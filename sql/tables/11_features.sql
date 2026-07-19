create table if not exists public.features (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_id uuid not null,
    feature_key varchar(50) not null,
    title varchar(500) not null,
    description text,
    business_value text,
    status varchar(30) not null default 'DRAFT',
    priority varchar(30) not null default 'MEDIUM',
    release_id uuid not null references public.releases(id),
    ai_generation_id uuid,
    source varchar(30) not null default 'AI_GENERATED',
    archived_at timestamptz,
    version integer not null default 1,
    created_by text not null default 'local-user',
    updated_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    problem_statement text,
    functional_requirements jsonb not null default '[]'::jsonb,
    non_functional_requirements jsonb not null default '[]'::jsonb,
    dependencies jsonb not null default '[]'::jsonb,
    risks jsonb not null default '[]'::jsonb,
    assumptions jsonb not null default '[]'::jsonb,
    constraint features_project_id_fkey
        foreign key (project_id) references public.projects(id) on delete cascade,
    constraint features_ai_generation_id_fkey
        foreign key (ai_generation_id) references public.ai_generations(id) on delete set null,
    unique (project_id, feature_key)
);

create index if not exists features_project_idx
    on public.features(project_id, status);

create index if not exists features_pi_release_idx
    on public.features(release_id);
