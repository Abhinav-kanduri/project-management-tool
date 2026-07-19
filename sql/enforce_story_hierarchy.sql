do $$
begin
  if exists(select 1 from public.user_stories where feature_id is null and archived_at is null) then
    raise exception 'Cannot enforce hierarchy: active unassigned user stories exist';
  end if;
end $$;

alter table public.user_stories alter column feature_id set not null;
