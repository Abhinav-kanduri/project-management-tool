create table if not exists public.acceptance_criteria (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_id uuid not null references public.projects(id),
    feature_id uuid,
    user_story_id uuid,
    given_text text,
    when_text text,
    then_text text,
    criteria_order integer not null default 1,
    is_completed boolean not null default false,
    created_by text not null default 'local-user',
    created_at timestamptz not null default now(),
    constraint acceptance_criteria_feature_id_fkey
        foreign key (feature_id) references public.features(id) on delete cascade,
    constraint acceptance_criteria_user_story_id_fkey
        foreign key (user_story_id) references public.user_stories(id) on delete cascade,
    check (feature_id is not null or user_story_id is not null)
);
