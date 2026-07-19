alter table public.sprints add column if not exists sprint_number integer;
alter table public.sprints add column if not exists display_name text;
alter table public.sprints add column if not exists goal text;
alter table public.sprints add column if not exists archived_at timestamptz;
alter table public.sprints add constraint sprints_number_check check (sprint_number is null or sprint_number > 0);
create unique index if not exists sprints_project_pi_number_idx on public.sprints(project_id,release_id,sprint_number) where sprint_number is not null;
create index if not exists sprints_pi_idx on public.sprints(release_id);
