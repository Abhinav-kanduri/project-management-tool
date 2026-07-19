create table if not exists public.documents (
    doc_id text primary key,
    doc_nm text not null,
    doc_type text not null,
    doc_raw_text text not null,
    doc_status text not null,
    create_timestamp timestamptz default now(),
    last_update_timestamp timestamptz default now()
);
