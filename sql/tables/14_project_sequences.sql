create table if not exists public.project_sequences (
    project_id uuid primary key,
    next_feature_number integer not null default 1,
    next_story_number integer not null default 101,
    updated_at timestamptz not null default now(),
    constraint project_sequences_project_id_fkey
        foreign key (project_id) references public.projects(id) on delete cascade
);
