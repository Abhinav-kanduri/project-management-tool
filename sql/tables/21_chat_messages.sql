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

create index if not exists chat_messages_session_sequence_idx
    on public.chat_messages(session_id, sequence_number);

create index if not exists chat_messages_session_created_idx
    on public.chat_messages(session_id, created_at);
