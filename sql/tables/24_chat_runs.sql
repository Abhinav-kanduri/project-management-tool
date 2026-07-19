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

create index if not exists chat_runs_session_started_idx
    on public.chat_runs(session_id, started_at desc);
