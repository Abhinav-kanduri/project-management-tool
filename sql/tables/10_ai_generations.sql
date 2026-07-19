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
