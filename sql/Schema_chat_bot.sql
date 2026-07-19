-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

## Table `connection_test`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `int4` | Primary |
| `message` | `varchar` |  Nullable |
| `created_at` | `timestamp` |  Nullable |

## Table `document_chunks`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `int8` | Primary |
| `doc_id` | `text` |  |
| `chunk_id` | `text` |  |
| `chunk_text` | `text` |  |
| `chunk_vector` | `vector` |  |
| `created_timestamp` | `timestamptz` |  Nullable |
| `last_updated` | `timestamptz` |  Nullable |

## Table `documents`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `doc_id` | `text` | Primary |
| `doc_nm` | `text` |  |
| `doc_type` | `text` |  |
| `doc_raw_text` | `text` |  |
| `doc_status` | `text` |  |
| `create_timestamp` | `timestamptz` |  Nullable |
| `last_update_timestamp` | `timestamptz` |  Nullable |

## Table `escalated_table`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `order_id` | `text` | Primary |
| `order_nm` | `text` |  |
| `approved_by` | `text` |  Nullable |
| `review_by` | `text` |  Nullable |
| `email_status` | `text` |  Nullable |
| `task_status` | `text` |  Nullable |

## Table `organizations`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `name` | `text` |  |
| `created_at` | `timestamptz` |  |
| `updated_at` | `timestamptz` |  |

## Table `product_spaces`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `organization_id` | `uuid` |  |
| `name` | `text` |  |
| `description` | `text` |  Nullable |
| `archived_at` | `timestamptz` |  Nullable |
| `created_at` | `timestamptz` |  |
| `updated_at` | `timestamptz` |  |
| `space_key` | `varchar` |  Nullable |
| `status` | `varchar` |  |
| `version` | `int4` |  |

## Table `projects`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `organization_id` | `uuid` |  |
| `product_space_id` | `uuid` |  |
| `project_key` | `varchar` |  |
| `name` | `text` |  |
| `owner_name` | `text` |  Nullable |
| `created_at` | `timestamptz` |  |
| `updated_at` | `timestamptz` |  |
| `description` | `text` |  Nullable |
| `status` | `varchar` |  |
| `health` | `varchar` |  |
| `version` | `int4` |  |
| `archived_at` | `timestamptz` |  Nullable |

## Table `releases`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `organization_id` | `uuid` |  |
| `product_space_id` | `uuid` |  |
| `project_id` | `uuid` |  |
| `name` | `text` |  |
| `status` | `varchar` |  |
| `start_date` | `date` |  Nullable |
| `target_date` | `date` |  Nullable |
| `created_at` | `timestamptz` |  |
| `updated_at` | `timestamptz` |  |
| `display_name` | `text` |  Nullable |
| `year` | `int4` |  Nullable |
| `pi_number` | `int4` |  Nullable |
| `description` | `text` |  Nullable |
| `owner` | `text` |  Nullable |
| `archived_at` | `timestamptz` |  Nullable |

## Table `sprints`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `organization_id` | `uuid` |  |
| `product_space_id` | `uuid` |  |
| `project_id` | `uuid` |  |
| `release_id` | `uuid` |  Nullable |
| `name` | `text` |  |
| `status` | `varchar` |  |
| `start_date` | `date` |  Nullable |
| `end_date` | `date` |  Nullable |
| `created_at` | `timestamptz` |  |
| `updated_at` | `timestamptz` |  |
| `sprint_number` | `int4` |  Nullable |
| `display_name` | `text` |  Nullable |
| `goal` | `text` |  Nullable |
| `archived_at` | `timestamptz` |  Nullable |

## Table `ai_generations`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `organization_id` | `uuid` |  |
| `product_space_id` | `uuid` |  |
| `project_id` | `uuid` |  |
| `generation_type` | `varchar` |  |
| `input_prompt` | `text` |  |
| `generated_content` | `jsonb` |  |
| `model_name` | `varchar` |  Nullable |
| `prompt_version` | `varchar` |  |
| `status` | `varchar` |  |
| `generated_by` | `text` |  |
| `generated_at` | `timestamptz` |  |
| `saved_at` | `timestamptz` |  Nullable |
| `created_at` | `timestamptz` |  |

## Table `features`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `organization_id` | `uuid` |  |
| `product_space_id` | `uuid` |  |
| `project_id` | `uuid` |  |
| `feature_key` | `varchar` |  |
| `title` | `varchar` |  |
| `description` | `text` |  Nullable |
| `business_value` | `text` |  Nullable |
| `status` | `varchar` |  |
| `priority` | `varchar` |  |
| `release_id` | `uuid` |  |
| `ai_generation_id` | `uuid` |  Nullable |
| `source` | `varchar` |  |
| `archived_at` | `timestamptz` |  Nullable |
| `version` | `int4` |  |
| `created_by` | `text` |  |
| `updated_by` | `text` |  Nullable |
| `created_at` | `timestamptz` |  |
| `updated_at` | `timestamptz` |  |
| `problem_statement` | `text` |  Nullable |
| `functional_requirements` | `jsonb` |  |
| `non_functional_requirements` | `jsonb` |  |
| `dependencies` | `jsonb` |  |
| `risks` | `jsonb` |  |
| `assumptions` | `jsonb` |  |

## Table `user_stories`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `organization_id` | `uuid` |  |
| `product_space_id` | `uuid` |  |
| `project_id` | `uuid` |  |
| `feature_id` | `uuid` |  |
| `story_key` | `varchar` |  |
| `title` | `varchar` |  |
| `story_text` | `text` |  Nullable |
| `status` | `varchar` |  |
| `priority` | `varchar` |  |
| `story_points` | `int4` |  Nullable |
| `release_id` | `uuid` |  |
| `sprint_id` | `uuid` |  Nullable |
| `ai_generation_id` | `uuid` |  Nullable |
| `source` | `varchar` |  |
| `archived_at` | `timestamptz` |  Nullable |
| `version` | `int4` |  |
| `created_by` | `text` |  |
| `updated_by` | `text` |  Nullable |
| `created_at` | `timestamptz` |  |
| `updated_at` | `timestamptz` |  |

## Table `acceptance_criteria`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `organization_id` | `uuid` |  |
| `product_space_id` | `uuid` |  |
| `project_id` | `uuid` |  |
| `feature_id` | `uuid` |  Nullable |
| `user_story_id` | `uuid` |  Nullable |
| `given_text` | `text` |  Nullable |
| `when_text` | `text` |  Nullable |
| `then_text` | `text` |  Nullable |
| `criteria_order` | `int4` |  |
| `is_completed` | `bool` |  |
| `created_by` | `text` |  |
| `created_at` | `timestamptz` |  |

## Table `project_sequences`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `project_id` | `uuid` | Primary |
| `next_feature_number` | `int4` |  |
| `next_story_number` | `int4` |  |
| `updated_at` | `timestamptz` |  |

## Table `activity_logs`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `organization_id` | `uuid` |  |
| `product_space_id` | `uuid` |  |
| `project_id` | `uuid` |  |
| `entity_type` | `varchar` |  |
| `entity_id` | `uuid` |  Nullable |
| `action` | `varchar` |  |
| `performed_by` | `text` |  |
| `details` | `jsonb` |  |
| `created_at` | `timestamptz` |  |

## Table `idempotency_keys`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `key` | `text` | Primary |
| `project_id` | `uuid` |  |
| `response` | `jsonb` |  Nullable |
| `created_at` | `timestamptz` |  |

## Table `organization_members`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `organization_id` | `uuid` | Primary |
| `user_id` | `uuid` | Primary |
| `role` | `varchar` |  |
| `created_at` | `timestamptz` |  |

## Table `product_space_members`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `product_space_id` | `uuid` | Primary |
| `user_id` | `uuid` | Primary |
| `role` | `varchar` |  |
| `created_at` | `timestamptz` |  |

## Table `project_members`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `project_id` | `uuid` | Primary |
| `user_id` | `uuid` | Primary |
| `role` | `varchar` |  |
| `created_at` | `timestamptz` |  |

## Table `chat_sessions`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `organization_id` | `uuid` |  |
| `product_space_id` | `uuid` |  |
| `project_id` | `uuid` |  |
| `actor_id` | `text` |  |
| `title` | `text` |  Nullable |
| `status` | `varchar` |  |
| `current_intent` | `varchar` |  Nullable |
| `intent_confidence` | `numeric` |  Nullable |
| `resolved_context` | `jsonb` |  |
| `conversation_summary` | `text` |  Nullable |
| `metadata` | `jsonb` |  |
| `message_count` | `int4` |  |
| `last_message_at` | `timestamptz` |  Nullable |
| `archived_at` | `timestamptz` |  Nullable |
| `created_at` | `timestamptz` |  |
| `updated_at` | `timestamptz` |  |

## Table `chat_messages`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `session_id` | `uuid` |  |
| `sequence_number` | `int4` |  |
| `client_message_id` | `varchar` |  Nullable |
| `role` | `varchar` |  |
| `content` | `text` |  |
| `status` | `varchar` |  |
| `model_name` | `varchar` |  Nullable |
| `prompt_tokens` | `int4` |  Nullable |
| `completion_tokens` | `int4` |  Nullable |
| `total_tokens` | `int4` |  Nullable |
| `latency_ms` | `int4` |  Nullable |
| `error_code` | `varchar` |  Nullable |
| `error_message` | `text` |  Nullable |
| `metadata` | `jsonb` |  |
| `created_at` | `timestamptz` |  |

## Table `chat_message_intents`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `session_id` | `uuid` |  |
| `message_id` | `uuid` |  Unique |
| `primary_intent` | `varchar` |  |
| `confidence` | `numeric` |  |
| `secondary_intents` | `jsonb` |  |
| `extracted_entities` | `jsonb` |  |
| `resolved_entities` | `jsonb` |  |
| `search_plan` | `jsonb` |  |
| `classifier_model` | `varchar` |  Nullable |
| `created_at` | `timestamptz` |  |

## Table `chat_retrieval_events`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `session_id` | `uuid` |  |
| `user_message_id` | `uuid` |  |
| `retrieval_type` | `varchar` |  |
| `original_query` | `text` |  |
| `normalized_query` | `text` |  Nullable |
| `filters` | `jsonb` |  |
| `source_types` | `jsonb` |  |
| `retrieved_results` | `jsonb` |  |
| `result_count` | `int4` |  |
| `latency_ms` | `int4` |  Nullable |
| `created_at` | `timestamptz` |  |

## Table `chat_runs`

### Columns

| Name | Type | Constraints |
|------|------|-------------|
| `id` | `uuid` | Primary |
| `session_id` | `uuid` |  |
| `user_message_id` | `uuid` |  |
| `assistant_message_id` | `uuid` |  Nullable |
| `status` | `varchar` |  |
| `graph_version` | `varchar` |  |
| `last_node` | `varchar` |  Nullable |
| `error_code` | `varchar` |  Nullable |
| `error_message` | `text` |  Nullable |
| `started_at` | `timestamptz` |  |
| `completed_at` | `timestamptz` |  Nullable |
| `latency_ms` | `int4` |  Nullable |
| `metadata` | `jsonb` |  |

## RLS Policies

### `ai_generations`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `generations_member_read` | SELECT | authenticated | PERMISSIVE | `is_project_member(project_id)` | — |

### `user_stories`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `stories_member_access` | ALL | authenticated | PERMISSIVE | `is_project_member(project_id)` | `can_edit_project(project_id)` |

### `organizations`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `organizations_select` | SELECT | authenticated | PERMISSIVE | `is_organization_member(id)` | — |
| `organizations_update` | UPDATE | authenticated | PERMISSIVE | `can_manage_organization(id)` | `can_manage_organization(id)` |

### `product_spaces`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `product_spaces_select` | SELECT | authenticated | PERMISSIVE | `is_product_space_member(id)` | — |
| `product_spaces_write` | ALL | authenticated | PERMISSIVE | `can_manage_product_space(id)` | `can_manage_organization(organization_id)` |

### `features`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `features_member_access` | ALL | authenticated | PERMISSIVE | `is_project_member(project_id)` | `can_edit_project(project_id)` |

### `acceptance_criteria`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `criteria_member_access` | ALL | authenticated | PERMISSIVE | `is_project_member(project_id)` | `can_edit_project(project_id)` |

### `activity_logs`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `activity_member_read` | SELECT | authenticated | PERMISSIVE | `is_project_member(project_id)` | — |

### `organization_members`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `organization_members_manage` | ALL | authenticated | PERMISSIVE | `can_manage_organization(organization_id)` | `can_manage_organization(organization_id)` |
| `organization_members_read` | SELECT | authenticated | PERMISSIVE | `((user_id = auth.uid()) OR can_manage_organization(organization_id))` | — |

### `product_space_members`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `product_space_members_manage` | ALL | authenticated | PERMISSIVE | `can_manage_product_space(product_space_id)` | `can_manage_product_space(product_space_id)` |
| `product_space_members_read` | SELECT | authenticated | PERMISSIVE | `((user_id = auth.uid()) OR can_manage_product_space(product_space_id))` | — |

### `project_members`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `project_members_manage` | ALL | authenticated | PERMISSIVE | `can_edit_project(project_id)` | `can_edit_project(project_id)` |
| `project_members_read` | SELECT | authenticated | PERMISSIVE | `((user_id = auth.uid()) OR can_edit_project(project_id))` | — |

### `projects`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `projects_select` | SELECT | authenticated | PERMISSIVE | `is_project_member(id)` | — |
| `projects_write` | ALL | authenticated | PERMISSIVE | `can_edit_project(id)` | `can_manage_product_space(product_space_id)` |

### `releases`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `releases_member_access` | ALL | authenticated | PERMISSIVE | `is_project_member(project_id)` | `can_edit_project(project_id)` |

### `sprints`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `sprints_member_access` | ALL | authenticated | PERMISSIVE | `is_project_member(project_id)` | `can_edit_project(project_id)` |

### `chat_sessions`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `chat_sessions_delete` | DELETE | authenticated | PERMISSIVE | `((actor_id = (auth.uid())::text) OR can_edit_project(project_id))` | — |
| `chat_sessions_insert` | INSERT | authenticated | PERMISSIVE | — | `(is_project_member(project_id) AND (EXISTS ( SELECT 1    FROM projects p   WHERE ((p.id = chat_sessions.project_id) AND (p.product_space_id = p.product_space_id) AND (p.organization_id = p.organization_id)))))` |
| `chat_sessions_select` | SELECT | authenticated | PERMISSIVE | `is_project_member(project_id)` | — |
| `chat_sessions_update` | UPDATE | authenticated | PERMISSIVE | `((actor_id = (auth.uid())::text) OR can_edit_project(project_id))` | `((actor_id = (auth.uid())::text) OR can_edit_project(project_id))` |

### `chat_messages`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `chat_messages_access` | ALL | authenticated | PERMISSIVE | `(EXISTS ( SELECT 1    FROM chat_sessions s   WHERE ((s.id = chat_messages.session_id) AND is_project_member(s.project_id))))` | `(EXISTS ( SELECT 1    FROM chat_sessions s   WHERE ((s.id = chat_messages.session_id) AND is_project_member(s.project_id))))` |

### `chat_message_intents`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `chat_message_intents_access` | ALL | authenticated | PERMISSIVE | `(EXISTS ( SELECT 1    FROM chat_sessions s   WHERE ((s.id = chat_message_intents.session_id) AND is_project_member(s.project_id))))` | `(EXISTS ( SELECT 1    FROM chat_sessions s   WHERE ((s.id = chat_message_intents.session_id) AND is_project_member(s.project_id))))` |

### `chat_retrieval_events`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `chat_retrieval_events_access` | ALL | authenticated | PERMISSIVE | `(EXISTS ( SELECT 1    FROM chat_sessions s   WHERE ((s.id = chat_retrieval_events.session_id) AND is_project_member(s.project_id))))` | `(EXISTS ( SELECT 1    FROM chat_sessions s   WHERE ((s.id = chat_retrieval_events.session_id) AND is_project_member(s.project_id))))` |

### `chat_runs`

| Policy | Command | Roles | Action | USING | WITH CHECK |
|--------|---------|-------|--------|-------|------------|
| `chat_runs_access` | ALL | authenticated | PERMISSIVE | `(EXISTS ( SELECT 1    FROM chat_sessions s   WHERE ((s.id = chat_runs.session_id) AND is_project_member(s.project_id))))` | `(EXISTS ( SELECT 1    FROM chat_sessions s   WHERE ((s.id = chat_runs.session_id) AND is_project_member(s.project_id))))` |

