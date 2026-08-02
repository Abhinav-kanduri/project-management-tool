create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

create table if not exists public.github_repositories (
    id uuid primary key default gen_random_uuid(),
    github_repository_id bigint not null unique check (github_repository_id > 0),
    node_id text,
    owner_login text not null,
    name text not null,
    full_name text not null,
    html_url text not null,
    description text,
    default_branch text not null,
    visibility text not null,
    private boolean not null default false,
    archived boolean not null default false,
    is_fork boolean not null default false,
    pushed_at timestamptz,
    github_updated_at timestamptz,
    metadata jsonb not null default '{}'::jsonb,
    synced_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists github_repositories_full_name_idx
    on public.github_repositories(lower(full_name));

create table if not exists public.project_github_repositories (
    id uuid primary key default gen_random_uuid(),
    product_space_id uuid not null
        references public.product_spaces(id) on delete cascade,
    project_id uuid not null
        references public.projects(id) on delete cascade,
    repository_id uuid not null
        references public.github_repositories(id) on delete cascade,
    linked_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique(project_id, repository_id)
);

create index if not exists project_github_repositories_space_idx
    on public.project_github_repositories(product_space_id);

create index if not exists project_github_repositories_project_idx
    on public.project_github_repositories(project_id);

create index if not exists project_github_repositories_repository_idx
    on public.project_github_repositories(repository_id);
