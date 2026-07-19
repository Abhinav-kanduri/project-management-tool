create table if not exists public.chat_sessions (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    product_space_id uuid not null references public.product_spaces(id) on delete cascade,
    project_id uuid not null references public.projects(id) on delete cascade,
    actor_id text not null default 'local-user',
    title text,
    status varchar not null default 'ACTIVE'
        check (status in ('ACTIVE', 'ARCHIVED', 'DELETED')),
    current_intent varchar,
    intent_confidence numeric(5,4)
        check (intent_confidence is null or intent_confidence between 0 and 1),
    resolved_context jsonb not null default '{}'::jsonb,
    conversation_summary text,
    metadata jsonb not null default '{}'::jsonb,
    message_count integer not null default 0 check (message_count >= 0),
    last_message_at timestamptz,
    archived_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists chat_sessions_project_actor_updated_idx
    on public.chat_sessions(project_id, actor_id, updated_at desc);

create index if not exists chat_sessions_space_project_idx
    on public.chat_sessions(product_space_id, project_id);

create index if not exists chat_sessions_resolved_context_gin_idx
    on public.chat_sessions using gin(resolved_context);
