create table if not exists public.organization_members (
    organization_id uuid not null references public.organizations(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role varchar(40) not null default 'VIEWER',
    created_at timestamptz not null default now(),
    primary key (organization_id, user_id)
);

create table if not exists public.product_space_members (
    product_space_id uuid not null references public.product_spaces(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role varchar(40) not null default 'VIEWER',
    created_at timestamptz not null default now(),
    primary key (product_space_id, user_id)
);

create table if not exists public.project_members (
    project_id uuid not null references public.projects(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role varchar(40) not null default 'VIEWER',
    created_at timestamptz not null default now(),
    primary key (project_id, user_id)
);

create or replace function public.is_organization_member(target_id uuid)
returns boolean language sql stable security definer set search_path = public, auth
as $$ select exists(select 1 from organization_members where organization_id=target_id and user_id=auth.uid()) $$;

create or replace function public.is_product_space_member(target_id uuid)
returns boolean language sql stable security definer set search_path = public, auth
as $$
  select exists(select 1 from product_space_members where product_space_id=target_id and user_id=auth.uid())
  or exists(select 1 from product_spaces ps join organization_members om on om.organization_id=ps.organization_id where ps.id=target_id and om.user_id=auth.uid());
$$;

create or replace function public.is_project_member(target_id uuid)
returns boolean language sql stable security definer set search_path = public, auth
as $$
  select exists(select 1 from project_members where project_id=target_id and user_id=auth.uid())
  or exists(select 1 from projects p join product_space_members psm on psm.product_space_id=p.product_space_id where p.id=target_id and psm.user_id=auth.uid())
  or exists(select 1 from projects p join organization_members om on om.organization_id=p.organization_id where p.id=target_id and om.user_id=auth.uid());
$$;

create or replace function public.can_manage_organization(target_id uuid)
returns boolean language sql stable security definer set search_path = public, auth
as $$ select exists(select 1 from organization_members where organization_id=target_id and user_id=auth.uid() and role in ('ORGANIZATION_ADMIN','ADMIN')) $$;

create or replace function public.can_manage_product_space(target_id uuid)
returns boolean language sql stable security definer set search_path = public, auth
as $$
  select exists(select 1 from product_space_members where product_space_id=target_id and user_id=auth.uid() and role in ('PRODUCT_SPACE_ADMIN','ADMIN'))
  or exists(select 1 from product_spaces ps join organization_members om on om.organization_id=ps.organization_id where ps.id=target_id and om.user_id=auth.uid() and om.role in ('ORGANIZATION_ADMIN','ADMIN'));
$$;

create or replace function public.can_edit_project(target_id uuid)
returns boolean language sql stable security definer set search_path = public, auth
as $$
  select exists(select 1 from project_members where project_id=target_id and user_id=auth.uid() and role in ('PROJECT_ADMIN','PRODUCT_OWNER','SCRUM_MASTER','DEVELOPER','QA_ENGINEER','ADMIN'))
  or exists(select 1 from projects p join product_space_members psm on psm.product_space_id=p.product_space_id where p.id=target_id and psm.user_id=auth.uid() and psm.role in ('PRODUCT_SPACE_ADMIN','ADMIN'))
  or exists(select 1 from projects p join organization_members om on om.organization_id=p.organization_id where p.id=target_id and om.user_id=auth.uid() and om.role in ('ORGANIZATION_ADMIN','ADMIN'));
$$;

revoke all on public.organizations, public.product_spaces, public.projects, public.releases,
  public.sprints, public.ai_generations, public.features, public.user_stories,
  public.acceptance_criteria, public.project_sequences, public.activity_logs,
  public.idempotency_keys, public.organization_members, public.product_space_members,
  public.project_members from anon, authenticated;

grant select on public.organizations, public.product_spaces, public.projects, public.releases,
  public.sprints, public.ai_generations, public.features, public.user_stories,
  public.acceptance_criteria, public.activity_logs, public.organization_members,
  public.product_space_members, public.project_members to authenticated;
grant insert, update on public.organizations, public.product_spaces, public.projects,
  public.releases, public.sprints, public.features, public.user_stories,
  public.acceptance_criteria, public.organization_members, public.product_space_members,
  public.project_members to authenticated;

alter table public.organizations enable row level security;
alter table public.product_spaces enable row level security;
alter table public.projects enable row level security;
alter table public.releases enable row level security;
alter table public.sprints enable row level security;
alter table public.ai_generations enable row level security;
alter table public.features enable row level security;
alter table public.user_stories enable row level security;
alter table public.acceptance_criteria enable row level security;
alter table public.project_sequences enable row level security;
alter table public.activity_logs enable row level security;
alter table public.idempotency_keys enable row level security;
alter table public.organization_members enable row level security;
alter table public.product_space_members enable row level security;
alter table public.project_members enable row level security;

drop policy if exists organizations_select on public.organizations;
create policy organizations_select on public.organizations for select to authenticated using (is_organization_member(id));
drop policy if exists organizations_update on public.organizations;
create policy organizations_update on public.organizations for update to authenticated using (can_manage_organization(id)) with check (can_manage_organization(id));

drop policy if exists product_spaces_select on public.product_spaces;
create policy product_spaces_select on public.product_spaces for select to authenticated using (is_product_space_member(id));
drop policy if exists product_spaces_write on public.product_spaces;
create policy product_spaces_write on public.product_spaces for all to authenticated using (can_manage_product_space(id)) with check (can_manage_organization(organization_id));

drop policy if exists projects_select on public.projects;
create policy projects_select on public.projects for select to authenticated using (is_project_member(id));
drop policy if exists projects_write on public.projects;
create policy projects_write on public.projects for all to authenticated using (can_edit_project(id)) with check (can_manage_product_space(product_space_id));

drop policy if exists releases_member_access on public.releases;
create policy releases_member_access on public.releases for all to authenticated using (is_project_member(project_id)) with check (can_edit_project(project_id));
drop policy if exists sprints_member_access on public.sprints;
create policy sprints_member_access on public.sprints for all to authenticated using (is_project_member(project_id)) with check (can_edit_project(project_id));
drop policy if exists features_member_access on public.features;
create policy features_member_access on public.features for all to authenticated using (is_project_member(project_id)) with check (can_edit_project(project_id));
drop policy if exists stories_member_access on public.user_stories;
create policy stories_member_access on public.user_stories for all to authenticated using (is_project_member(project_id)) with check (can_edit_project(project_id));
drop policy if exists criteria_member_access on public.acceptance_criteria;
create policy criteria_member_access on public.acceptance_criteria for all to authenticated using (is_project_member(project_id)) with check (can_edit_project(project_id));
drop policy if exists generations_member_read on public.ai_generations;
create policy generations_member_read on public.ai_generations for select to authenticated using (is_project_member(project_id));
drop policy if exists activity_member_read on public.activity_logs;
create policy activity_member_read on public.activity_logs for select to authenticated using (is_project_member(project_id));

drop policy if exists organization_members_read on public.organization_members;
create policy organization_members_read on public.organization_members for select to authenticated using (user_id=auth.uid() or can_manage_organization(organization_id));
drop policy if exists organization_members_manage on public.organization_members;
create policy organization_members_manage on public.organization_members for all to authenticated using (can_manage_organization(organization_id)) with check (can_manage_organization(organization_id));
drop policy if exists product_space_members_read on public.product_space_members;
create policy product_space_members_read on public.product_space_members for select to authenticated using (user_id=auth.uid() or can_manage_product_space(product_space_id));
drop policy if exists product_space_members_manage on public.product_space_members;
create policy product_space_members_manage on public.product_space_members for all to authenticated using (can_manage_product_space(product_space_id)) with check (can_manage_product_space(product_space_id));
drop policy if exists project_members_read on public.project_members;
create policy project_members_read on public.project_members for select to authenticated using (user_id=auth.uid() or can_edit_project(project_id));
drop policy if exists project_members_manage on public.project_members;
create policy project_members_manage on public.project_members for all to authenticated using (can_edit_project(project_id)) with check (can_edit_project(project_id));

revoke all on function public.is_organization_member(uuid), public.is_product_space_member(uuid),
  public.is_project_member(uuid), public.can_manage_organization(uuid),
  public.can_manage_product_space(uuid), public.can_edit_project(uuid) from public, anon;
grant execute on function public.is_organization_member(uuid), public.is_product_space_member(uuid),
  public.is_project_member(uuid), public.can_manage_organization(uuid),
  public.can_manage_product_space(uuid), public.can_edit_project(uuid) to authenticated;
