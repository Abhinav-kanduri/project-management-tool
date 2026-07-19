create table if not exists public.product_space_members (
    product_space_id uuid not null references public.product_spaces(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role varchar(40) not null default 'VIEWER',
    created_at timestamptz not null default now(),
    primary key (product_space_id, user_id)
);
