create table if not exists public.project_members (
    project_id uuid not null references public.projects(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role varchar(40) not null default 'VIEWER',
    created_at timestamptz not null default now(),
    primary key (project_id, user_id)
);
