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

create index if not exists chat_retrieval_events_session_created_idx
    on public.chat_retrieval_events(session_id, created_at);
