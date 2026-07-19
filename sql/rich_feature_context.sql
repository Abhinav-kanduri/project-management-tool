alter table public.features add column if not exists problem_statement text;
alter table public.features add column if not exists functional_requirements jsonb not null default '[]'::jsonb;
alter table public.features add column if not exists non_functional_requirements jsonb not null default '[]'::jsonb;
alter table public.features add column if not exists dependencies jsonb not null default '[]'::jsonb;
alter table public.features add column if not exists risks jsonb not null default '[]'::jsonb;
alter table public.features add column if not exists assumptions jsonb not null default '[]'::jsonb;
