alter table if exists public.impact_analysis_runs
    add column if not exists previous_run_id uuid
        references public.impact_analysis_runs(id) on delete set null;

create index if not exists impact_analysis_runs_previous_idx
    on public.impact_analysis_runs(previous_run_id)
    where previous_run_id is not null;
