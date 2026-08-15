# Per-table database schema

These files convert the table inventory in `../Schema_chat_bot.sql` into executable PostgreSQL DDL. Run them in numeric order so referenced tables exist before foreign keys are created.

`00_prerequisites.sql` enables the UUID and vector extensions. Files `01` through `24` create the original application tables. Files `25` through `37` add immutable repository source indexing, Impact Analysis runs/evidence/findings/scores, re-analysis lineage, and the generated-change audit lifecycle. They retain PostgreSQL as the primary record and do not duplicate Project Management or GitHub catalog entities.

After creating the tables, apply the existing security scripts in this order when using Supabase:

1. `../releaselens_security.sql`
2. `../chat_conversation_schema.sql`
3. `../impact_analysis_security.sql`

Both scripts are idempotent. The second script retains the chat tables with `create table if not exists` and then installs their grants and row-level security policies.

The `documents` and `document_chunks` definitions follow the column names reported by `Schema_chat_bot.sql`, which differ from the older example in `INSTRUCTION.md`.
