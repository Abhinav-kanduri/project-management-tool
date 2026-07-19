# Per-table database schema

These files convert the table inventory in `../Schema_chat_bot.sql` into executable PostgreSQL DDL. Run them in numeric order so referenced tables exist before foreign keys are created.

`00_prerequisites.sql` enables the UUID and vector extensions. Files `01` through `24` create one table each, including known defaults, checks, foreign keys, delete behavior, unique constraints, and indexes from the existing ReleaseLens migrations.

After creating the tables, apply the existing security scripts in this order when using Supabase:

1. `../releaselens_security.sql`
2. `../chat_conversation_schema.sql`

Both scripts are idempotent. The second script retains the chat tables with `create table if not exists` and then installs their grants and row-level security policies.

The `documents` and `document_chunks` definitions follow the column names reported by `Schema_chat_bot.sql`, which differ from the older example in `INSTRUCTION.md`.
