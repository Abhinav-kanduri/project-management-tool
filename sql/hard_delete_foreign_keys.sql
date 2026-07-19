-- Reviewed hard-delete behavior for the ReleaseLens-owned hierarchy.
-- Apply after releaselens.sql and releaselens_security.sql.
begin;

alter table public.projects drop constraint if exists projects_product_space_id_fkey;
alter table public.projects add constraint projects_product_space_id_fkey foreign key (product_space_id) references public.product_spaces(id) on delete cascade;
alter table public.releases drop constraint if exists releases_project_id_fkey;
alter table public.releases add constraint releases_project_id_fkey foreign key (project_id) references public.projects(id) on delete cascade;
alter table public.sprints drop constraint if exists sprints_project_id_fkey;
alter table public.sprints add constraint sprints_project_id_fkey foreign key (project_id) references public.projects(id) on delete cascade;
alter table public.features drop constraint if exists features_project_id_fkey;
alter table public.features add constraint features_project_id_fkey foreign key (project_id) references public.projects(id) on delete cascade;
alter table public.user_stories drop constraint if exists user_stories_feature_id_fkey;
alter table public.user_stories add constraint user_stories_feature_id_fkey foreign key (feature_id) references public.features(id) on delete cascade;
alter table public.acceptance_criteria drop constraint if exists acceptance_criteria_feature_id_fkey;
alter table public.acceptance_criteria add constraint acceptance_criteria_feature_id_fkey foreign key (feature_id) references public.features(id) on delete cascade;
alter table public.acceptance_criteria drop constraint if exists acceptance_criteria_user_story_id_fkey;
alter table public.acceptance_criteria add constraint acceptance_criteria_user_story_id_fkey foreign key (user_story_id) references public.user_stories(id) on delete cascade;
alter table public.project_sequences drop constraint if exists project_sequences_project_id_fkey;
alter table public.project_sequences add constraint project_sequences_project_id_fkey foreign key (project_id) references public.projects(id) on delete cascade;
alter table public.idempotency_keys drop constraint if exists idempotency_keys_project_id_fkey;
alter table public.idempotency_keys add constraint idempotency_keys_project_id_fkey foreign key (project_id) references public.projects(id) on delete cascade;
alter table public.user_stories drop constraint if exists user_stories_sprint_id_fkey;
alter table public.user_stories add constraint user_stories_sprint_id_fkey foreign key (sprint_id) references public.sprints(id) on delete set null;
alter table public.features drop constraint if exists features_ai_generation_id_fkey;
alter table public.features add constraint features_ai_generation_id_fkey foreign key (ai_generation_id) references public.ai_generations(id) on delete set null;
alter table public.user_stories drop constraint if exists user_stories_ai_generation_id_fkey;
alter table public.user_stories add constraint user_stories_ai_generation_id_fkey foreign key (ai_generation_id) references public.ai_generations(id) on delete set null;
alter table public.document_chunks drop constraint if exists document_chunks_doc_id_fkey;
alter table public.document_chunks add constraint document_chunks_doc_id_fkey foreign key (doc_id) references public.documents(doc_id) on delete cascade not valid;

commit;
