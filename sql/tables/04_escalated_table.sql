create table if not exists public.escalated_table (
    order_id text primary key,
    order_nm text not null,
    approved_by text,
    review_by text,
    email_status text,
    task_status text
);
