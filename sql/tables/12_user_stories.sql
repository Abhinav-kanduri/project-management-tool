create table if not exists public.user_stories (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_id uuid not null references public.projects(id),
    feature_id uuid not null,
    story_key varchar(50) not null,
    title varchar(500) not null,
    story_text text,
    status varchar(30) not null default 'BACKLOG',
    priority varchar(30) not null default 'MEDIUM',
    story_points integer check (story_points between 1 and 100),
    release_id uuid not null references public.releases(id),
    sprint_id uuid,
    ai_generation_id uuid,
    source varchar(30) not null default 'AI_GENERATED',
    archived_at timestamptz,
    version integer not null default 1,
    created_by text not null default 'local-user',
    updated_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint user_stories_feature_id_fkey
        foreign key (feature_id) references public.features(id) on delete cascade,
    constraint user_stories_sprint_id_fkey
        foreign key (sprint_id) references public.sprints(id) on delete set null,
    constraint user_stories_ai_generation_id_fkey
        foreign key (ai_generation_id) references public.ai_generations(id) on delete set null,
    unique (project_id, story_key)
);

create index if not exists stories_project_idx
    on public.user_stories(project_id, status);

create index if not exists stories_pi_release_idx
    on public.user_stories(release_id);
