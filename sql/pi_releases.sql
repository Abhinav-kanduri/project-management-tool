alter table public.releases add column if not exists display_name text;
alter table public.releases add column if not exists year integer;
alter table public.releases add column if not exists pi_number integer;
alter table public.releases add column if not exists description text;
alter table public.releases add column if not exists owner text;
alter table public.releases add column if not exists archived_at timestamptz;
alter table public.releases add constraint releases_pi_number_check check (pi_number is null or pi_number between 1 and 4);
create unique index if not exists releases_project_year_pi_idx on public.releases(project_id,year,pi_number) where year is not null;
create index if not exists releases_project_year_idx on public.releases(project_id,year);
create index if not exists features_pi_release_idx on public.features(release_id);
create index if not exists stories_pi_release_idx on public.user_stories(release_id);

do $$
declare p record; y integer; n integer; start_month integer; release_uuid uuid;
begin
  for p in select id,organization_id,product_space_id from public.projects loop
    foreach y in array array[2026,2027] loop
      for n in 1..4 loop
        start_month := 1 + ((n-1)*3);
        insert into public.releases(organization_id,product_space_id,project_id,name,display_name,year,pi_number,start_date,target_date,status)
        values(p.organization_id,p.product_space_id,p.id,y||' PI '||n,y||' PI '||n,y,n,make_date(y,start_month,1),(make_date(y,start_month,1)+interval '3 months - 1 day')::date,'PLANNED')
        on conflict(project_id,year,pi_number) where year is not null do nothing;
      end loop;
    end loop;
    select id into release_uuid from public.releases where project_id=p.id and year=2026 and pi_number=1;
    update public.features set release_id=release_uuid where project_id=p.id and release_id is null;
    update public.user_stories us set release_id=f.release_id from public.features f where us.feature_id=f.id and us.release_id is null;
  end loop;
end $$;

alter table public.features alter column release_id set not null;
alter table public.user_stories alter column release_id set not null;
