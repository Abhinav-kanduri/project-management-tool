do $$
declare
  target_space_id uuid;
  target_org_id uuid;
begin
  select id, organization_id into target_space_id, target_org_id
  from public.product_spaces where name='Customer Experience' limit 1;

  insert into public.projects(organization_id, product_space_id, project_key, name, owner_name)
  values(target_org_id, target_space_id, 'CFA', 'Customer Feedback Analyzer', 'Abhinav')
  on conflict (organization_id, project_key) do update
    set product_space_id=excluded.product_space_id, name=excluded.name, updated_at=now();

  update public.projects set product_space_id=target_space_id, updated_at=now()
  where organization_id=target_org_id and project_key='RAK';

  update public.projects p set product_space_id=ps.id, updated_at=now()
  from public.product_spaces ps
  where ps.organization_id=target_org_id and ps.name='Restaurant Operations'
    and p.organization_id=target_org_id and p.project_key='RSA';

  insert into public.project_sequences(project_id)
  select id from public.projects where product_space_id=target_space_id
  on conflict(project_id) do nothing;

  insert into public.releases(organization_id,product_space_id,project_id,name,status,start_date,target_date)
  select p.organization_id,p.product_space_id,p.id,'MVP 1.0','ACTIVE',current_date,current_date+60
  from public.projects p where p.product_space_id=target_space_id
    and not exists(select 1 from public.releases r where r.project_id=p.id and r.name='MVP 1.0');

  insert into public.sprints(organization_id,product_space_id,project_id,release_id,name,status,start_date,end_date)
  select p.organization_id,p.product_space_id,p.id,r.id,'Sprint 1','ACTIVE',current_date,current_date+13
  from public.projects p join public.releases r on r.project_id=p.id and r.name='MVP 1.0'
  where p.product_space_id=target_space_id
    and not exists(select 1 from public.sprints s where s.project_id=p.id and s.name='Sprint 1');
end $$;
