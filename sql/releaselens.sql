create extension if not exists pgcrypto with schema extensions;

create table if not exists public.organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.product_spaces (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    name text not null,
    description text,
    archived_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, name)
);

create table if not exists public.projects (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_key varchar(20) not null,
    name text not null,
    owner_name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, project_key)
);

create table if not exists public.releases (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_id uuid not null references public.projects(id),
    name text not null,
    status varchar(30) not null default 'PLANNED',
    start_date date,
    target_date date,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.sprints (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_id uuid not null references public.projects(id),
    release_id uuid references public.releases(id),
    name text not null,
    status varchar(30) not null default 'PLANNED',
    start_date date,
    end_date date,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.ai_generations (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_id uuid not null references public.projects(id),
    generation_type varchar(50) not null,
    input_prompt text not null,
    generated_content jsonb not null,
    model_name varchar(100),
    prompt_version varchar(50) not null default 'v1',
    status varchar(30) not null default 'GENERATED',
    generated_by text not null default 'local-user',
    generated_at timestamptz not null default now(),
    saved_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists public.features (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_id uuid not null references public.projects(id),
    feature_key varchar(50) not null,
    title varchar(500) not null,
    description text,
    business_value text,
    status varchar(30) not null default 'DRAFT',
    priority varchar(30) not null default 'MEDIUM',
    release_id uuid references public.releases(id),
    ai_generation_id uuid references public.ai_generations(id),
    source varchar(30) not null default 'AI_GENERATED',
    archived_at timestamptz,
    version integer not null default 1,
    created_by text not null default 'local-user',
    updated_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (project_id, feature_key)
);

create table if not exists public.user_stories (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_id uuid not null references public.projects(id),
    feature_id uuid references public.features(id) on delete cascade,
    story_key varchar(50) not null,
    title varchar(500) not null,
    story_text text,
    status varchar(30) not null default 'BACKLOG',
    priority varchar(30) not null default 'MEDIUM',
    story_points integer check (story_points between 1 and 100),
    release_id uuid references public.releases(id),
    sprint_id uuid references public.sprints(id),
    ai_generation_id uuid references public.ai_generations(id),
    source varchar(30) not null default 'AI_GENERATED',
    archived_at timestamptz,
    version integer not null default 1,
    created_by text not null default 'local-user',
    updated_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (project_id, story_key)
);

create table if not exists public.acceptance_criteria (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_id uuid not null references public.projects(id),
    feature_id uuid references public.features(id) on delete cascade,
    user_story_id uuid references public.user_stories(id) on delete cascade,
    given_text text,
    when_text text,
    then_text text,
    criteria_order integer not null default 1,
    is_completed boolean not null default false,
    created_by text not null default 'local-user',
    created_at timestamptz not null default now(),
    check (feature_id is not null or user_story_id is not null)
);

create table if not exists public.project_sequences (
    project_id uuid primary key references public.projects(id),
    next_feature_number integer not null default 1,
    next_story_number integer not null default 101,
    updated_at timestamptz not null default now()
);

create table if not exists public.activity_logs (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    product_space_id uuid not null references public.product_spaces(id),
    project_id uuid not null references public.projects(id),
    entity_type varchar(50) not null,
    entity_id uuid,
    action varchar(80) not null,
    performed_by text not null default 'local-user',
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.idempotency_keys (
    key text primary key,
    project_id uuid not null references public.projects(id),
    response jsonb,
    created_at timestamptz not null default now()
);

create index if not exists features_project_idx on public.features(project_id, status);
create index if not exists stories_project_idx on public.user_stories(project_id, status);
create index if not exists activity_project_idx on public.activity_logs(project_id, created_at desc);

with organization as (
    insert into public.organizations (name)
    select 'AI Delivery Platform'
    where not exists (select 1 from public.organizations where name = 'AI Delivery Platform')
    returning id
), org as (
    select id from organization union all
    select id from public.organizations where name = 'AI Delivery Platform' limit 1
), spaces(name, description) as (
    values
      ('Customer Experience', 'AI products that improve the customer journey'),
      ('Restaurant Operations', 'Tools for restaurant teams and guests'),
      ('Enterprise Knowledge', 'Release-aware organizational knowledge')
)
insert into public.product_spaces (organization_id, name, description)
select org.id, spaces.name, spaces.description from org cross join spaces
on conflict (organization_id, name) do nothing;

insert into public.projects (organization_id, product_space_id, project_key, name, owner_name)
select ps.organization_id, ps.id, 'CSB', 'Customer Support Bot', 'Abhinav'
from public.product_spaces ps where ps.name = 'Customer Experience'
on conflict (organization_id, project_key) do nothing;

insert into public.projects (organization_id, product_space_id, project_key, name, owner_name)
select ps.organization_id, ps.id, 'RSA', 'Restaurant Support Assistant', 'Abhinav'
from public.product_spaces ps where ps.name = 'Restaurant Operations'
on conflict (organization_id, project_key) do nothing;

insert into public.projects (organization_id, product_space_id, project_key, name, owner_name)
select ps.organization_id, ps.id, 'RAK', 'Release-Aware Knowledge Base', 'Abhinav'
from public.product_spaces ps where ps.name = 'Enterprise Knowledge'
on conflict (organization_id, project_key) do nothing;

insert into public.project_sequences (project_id)
select id from public.projects on conflict (project_id) do nothing;

insert into public.releases (organization_id, product_space_id, project_id, name, status, start_date, target_date)
select p.organization_id, p.product_space_id, p.id, 'MVP 1.0', 'ACTIVE', current_date, current_date + 60
from public.projects p where p.project_key = 'CSB'
and not exists (select 1 from public.releases r where r.project_id=p.id and r.name='MVP 1.0');

insert into public.sprints (organization_id, product_space_id, project_id, release_id, name, status, start_date, end_date)
select p.organization_id, p.product_space_id, p.id, r.id, 'Sprint 1', 'ACTIVE', current_date, current_date + 13
from public.projects p join public.releases r on r.project_id=p.id and r.name='MVP 1.0'
where p.project_key='CSB'
and not exists (select 1 from public.sprints s where s.project_id=p.id and s.name='Sprint 1');
