-- Administrator-only local reset. This removes rows, never schema objects or auth.users.
-- The list reflects the tables defined by this repository as of this migration.
begin;
truncate table
  public.chat_runs,
  public.chat_retrieval_events,
  public.chat_message_intents,
  public.chat_messages,
  public.chat_sessions,
  public.acceptance_criteria,
  public.user_stories,
  public.features,
  public.sprints,
  public.releases,
  public.ai_generations,
  public.project_sequences,
  public.idempotency_keys,
  public.activity_logs,
  public.project_members,
  public.product_space_members,
  public.organization_members,
  public.projects,
  public.product_spaces,
  public.organizations,
  public.document_ingestion_events,
  public.document_ingestion_jobs,
  public.document_chunks,
  public.documents,
  public.connection_test,
  public.escalated_table
restart identity cascade;
commit;
