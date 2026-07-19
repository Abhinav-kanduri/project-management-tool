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

create index if not exists chat_message_intents_session_created_idx
    on public.chat_message_intents(session_id, created_at);

create index if not exists chat_message_intents_primary_idx
    on public.chat_message_intents(primary_intent);

create index if not exists chat_message_intents_extracted_entities_gin_idx
    on public.chat_message_intents using gin(extracted_entities);

create index if not exists chat_message_intents_resolved_entities_gin_idx
    on public.chat_message_intents using gin(resolved_entities);
