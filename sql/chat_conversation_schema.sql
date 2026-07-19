-- ReleaseLens persistent, project-scoped chat business schema.
-- LangGraph checkpoint tables are intentionally separate and must be created by
-- AsyncPostgresSaver.setup() through a controlled initialization command.

begin;

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

create table if not exists public.chat_messages (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references public.chat_sessions(id) on delete cascade,
    sequence_number integer not null check (sequence_number > 0),
    client_message_id varchar,
    role varchar not null check (role in ('USER', 'ASSISTANT', 'SYSTEM', 'TOOL')),
    content text not null,
    status varchar not null default 'COMPLETED'
        check (status in ('PENDING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    model_name varchar,
    prompt_tokens integer check (prompt_tokens is null or prompt_tokens >= 0),
    completion_tokens integer check (completion_tokens is null or completion_tokens >= 0),
    total_tokens integer check (total_tokens is null or total_tokens >= 0),
    latency_ms integer check (latency_ms is null or latency_ms >= 0),
    error_code varchar,
    error_message text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (session_id, sequence_number),
    unique (session_id, client_message_id)
);

create table if not exists public.chat_message_intents (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references public.chat_sessions(id) on delete cascade,
    message_id uuid not null references public.chat_messages(id) on delete cascade,
    primary_intent varchar not null,
    confidence numeric(5,4) not null check (confidence between 0 and 1),
    secondary_intents jsonb not null default '[]'::jsonb,
    extracted_entities jsonb not null default '{}'::jsonb,
    resolved_entities jsonb not null default '{}'::jsonb,
    search_plan jsonb not null default '{}'::jsonb,
    classifier_model varchar,
    created_at timestamptz not null default now(),
    unique (message_id)
);

create table if not exists public.chat_retrieval_events (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references public.chat_sessions(id) on delete cascade,
    user_message_id uuid not null references public.chat_messages(id) on delete cascade,
    retrieval_type varchar not null
        check (retrieval_type in ('NONE', 'STRUCTURED', 'VECTOR', 'HYBRID')),
    original_query text not null,
    normalized_query text,
    filters jsonb not null default '{}'::jsonb,
    source_types jsonb not null default '[]'::jsonb,
    retrieved_results jsonb not null default '[]'::jsonb,
    result_count integer not null default 0 check (result_count >= 0),
    latency_ms integer check (latency_ms is null or latency_ms >= 0),
    created_at timestamptz not null default now()
);

create table if not exists public.chat_runs (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references public.chat_sessions(id) on delete cascade,
    user_message_id uuid not null references public.chat_messages(id) on delete cascade,
    assistant_message_id uuid references public.chat_messages(id) on delete set null,
    status varchar not null default 'RUNNING'
        check (status in ('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    graph_version varchar not null default 'v1',
    last_node varchar,
    error_code varchar,
    error_message text,
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    latency_ms integer check (latency_ms is null or latency_ms >= 0),
    metadata jsonb not null default '{}'::jsonb
);

create index if not exists chat_sessions_project_actor_updated_idx
    on public.chat_sessions(project_id, actor_id, updated_at desc);
create index if not exists chat_sessions_space_project_idx
    on public.chat_sessions(product_space_id, project_id);
create index if not exists chat_messages_session_sequence_idx
    on public.chat_messages(session_id, sequence_number);
create index if not exists chat_messages_session_created_idx
    on public.chat_messages(session_id, created_at);
create index if not exists chat_message_intents_session_created_idx
    on public.chat_message_intents(session_id, created_at);
create index if not exists chat_message_intents_primary_idx
    on public.chat_message_intents(primary_intent);
create index if not exists chat_retrieval_events_session_created_idx
    on public.chat_retrieval_events(session_id, created_at);
create index if not exists chat_runs_session_started_idx
    on public.chat_runs(session_id, started_at desc);
create index if not exists chat_sessions_resolved_context_gin_idx
    on public.chat_sessions using gin(resolved_context);
create index if not exists chat_message_intents_extracted_entities_gin_idx
    on public.chat_message_intents using gin(extracted_entities);
create index if not exists chat_message_intents_resolved_entities_gin_idx
    on public.chat_message_intents using gin(resolved_entities);

alter table public.chat_sessions enable row level security;
alter table public.chat_messages enable row level security;
alter table public.chat_message_intents enable row level security;
alter table public.chat_retrieval_events enable row level security;
alter table public.chat_runs enable row level security;

grant select, insert, update, delete on public.chat_sessions,
    public.chat_messages, public.chat_message_intents,
    public.chat_retrieval_events, public.chat_runs to authenticated;
revoke all on public.chat_sessions, public.chat_messages,
    public.chat_message_intents, public.chat_retrieval_events,
    public.chat_runs from anon;

drop policy if exists chat_sessions_select on public.chat_sessions;
create policy chat_sessions_select on public.chat_sessions for select to authenticated
    using (is_project_member(project_id));

drop policy if exists chat_sessions_insert on public.chat_sessions;
create policy chat_sessions_insert on public.chat_sessions for insert to authenticated
    with check (
        is_project_member(project_id)
        and exists (
            select 1 from public.projects p
            where p.id = project_id
              and p.product_space_id = product_space_id
              and p.organization_id = organization_id
        )
    );

drop policy if exists chat_sessions_update on public.chat_sessions;
create policy chat_sessions_update on public.chat_sessions for update to authenticated
    using (actor_id = auth.uid()::text or can_edit_project(project_id))
    with check (actor_id = auth.uid()::text or can_edit_project(project_id));

drop policy if exists chat_sessions_delete on public.chat_sessions;
create policy chat_sessions_delete on public.chat_sessions for delete to authenticated
    using (actor_id = auth.uid()::text or can_edit_project(project_id));

drop policy if exists chat_messages_access on public.chat_messages;
create policy chat_messages_access on public.chat_messages for all to authenticated
    using (exists (
        select 1 from public.chat_sessions s
        where s.id = session_id and is_project_member(s.project_id)
    ))
    with check (exists (
        select 1 from public.chat_sessions s
        where s.id = session_id and is_project_member(s.project_id)
    ));

drop policy if exists chat_message_intents_access on public.chat_message_intents;
create policy chat_message_intents_access on public.chat_message_intents for all to authenticated
    using (exists (
        select 1 from public.chat_sessions s
        where s.id = session_id and is_project_member(s.project_id)
    ))
    with check (exists (
        select 1 from public.chat_sessions s
        where s.id = session_id and is_project_member(s.project_id)
    ));

drop policy if exists chat_retrieval_events_access on public.chat_retrieval_events;
create policy chat_retrieval_events_access on public.chat_retrieval_events for all to authenticated
    using (exists (
        select 1 from public.chat_sessions s
        where s.id = session_id and is_project_member(s.project_id)
    ))
    with check (exists (
        select 1 from public.chat_sessions s
        where s.id = session_id and is_project_member(s.project_id)
    ));

drop policy if exists chat_runs_access on public.chat_runs;
create policy chat_runs_access on public.chat_runs for all to authenticated
    using (exists (
        select 1 from public.chat_sessions s
        where s.id = session_id and is_project_member(s.project_id)
    ))
    with check (exists (
        select 1 from public.chat_sessions s
        where s.id = session_id and is_project_member(s.project_id)
    ));

commit;
