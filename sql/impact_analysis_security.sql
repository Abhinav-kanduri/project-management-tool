begin;

alter table public.repository_snapshots enable row level security;
alter table public.repository_source_files enable row level security;
alter table public.repository_source_symbols enable row level security;
alter table public.repository_source_edges enable row level security;
alter table public.repository_source_chunks enable row level security;
alter table public.impact_analysis_runs enable row level security;
alter table public.impact_requirements enable row level security;
alter table public.impact_evidence enable row level security;
alter table public.impact_findings enable row level security;
alter table public.analysis_score_history enable row level security;
alter table public.generated_changes enable row level security;
alter table public.generated_change_validations enable row level security;

grant select, insert, update, delete on
    public.repository_snapshots,
    public.repository_source_files,
    public.repository_source_symbols,
    public.repository_source_edges,
    public.repository_source_chunks,
    public.impact_analysis_runs,
    public.impact_requirements,
    public.impact_evidence,
    public.impact_findings,
    public.analysis_score_history,
    public.generated_changes,
    public.generated_change_validations
to authenticated;

revoke all on
    public.repository_snapshots,
    public.repository_source_files,
    public.repository_source_symbols,
    public.repository_source_edges,
    public.repository_source_chunks,
    public.impact_analysis_runs,
    public.impact_requirements,
    public.impact_evidence,
    public.impact_findings,
    public.analysis_score_history,
    public.generated_changes,
    public.generated_change_validations
from anon;

drop policy if exists impact_runs_project_access on public.impact_analysis_runs;
create policy impact_runs_project_access on public.impact_analysis_runs for all to authenticated
    using (is_project_member(project_id))
    with check (is_project_member(project_id));

drop policy if exists repository_snapshots_project_access on public.repository_snapshots;
create policy repository_snapshots_project_access on public.repository_snapshots for all to authenticated
    using (is_project_member(project_id))
    with check (is_project_member(project_id));

drop policy if exists score_history_project_access on public.analysis_score_history;
create policy score_history_project_access on public.analysis_score_history for all to authenticated
    using (is_project_member(project_id))
    with check (is_project_member(project_id));

drop policy if exists impact_requirements_run_access on public.impact_requirements;
create policy impact_requirements_run_access on public.impact_requirements for all to authenticated
    using (exists (select 1 from public.impact_analysis_runs r where r.id=impact_requirements.run_id and is_project_member(r.project_id)))
    with check (exists (select 1 from public.impact_analysis_runs r where r.id=impact_requirements.run_id and is_project_member(r.project_id)));

drop policy if exists impact_evidence_run_access on public.impact_evidence;
create policy impact_evidence_run_access on public.impact_evidence for all to authenticated
    using (exists (select 1 from public.impact_analysis_runs r where r.id=impact_evidence.run_id and is_project_member(r.project_id)))
    with check (exists (select 1 from public.impact_analysis_runs r where r.id=impact_evidence.run_id and is_project_member(r.project_id)));

drop policy if exists impact_findings_run_access on public.impact_findings;
create policy impact_findings_run_access on public.impact_findings for all to authenticated
    using (exists (select 1 from public.impact_analysis_runs r where r.id=impact_findings.run_id and is_project_member(r.project_id)))
    with check (exists (select 1 from public.impact_analysis_runs r where r.id=impact_findings.run_id and is_project_member(r.project_id)));

drop policy if exists source_files_snapshot_access on public.repository_source_files;
create policy source_files_snapshot_access on public.repository_source_files for all to authenticated
    using (exists (select 1 from public.repository_snapshots s where s.id=repository_source_files.snapshot_id and is_project_member(s.project_id)))
    with check (exists (select 1 from public.repository_snapshots s where s.id=repository_source_files.snapshot_id and is_project_member(s.project_id)));

drop policy if exists source_symbols_snapshot_access on public.repository_source_symbols;
create policy source_symbols_snapshot_access on public.repository_source_symbols for all to authenticated
    using (exists (select 1 from public.repository_snapshots s where s.id=repository_source_symbols.snapshot_id and is_project_member(s.project_id)))
    with check (exists (select 1 from public.repository_snapshots s where s.id=repository_source_symbols.snapshot_id and is_project_member(s.project_id)));

drop policy if exists source_edges_snapshot_access on public.repository_source_edges;
create policy source_edges_snapshot_access on public.repository_source_edges for all to authenticated
    using (exists (select 1 from public.repository_snapshots s where s.id=repository_source_edges.snapshot_id and is_project_member(s.project_id)))
    with check (exists (select 1 from public.repository_snapshots s where s.id=repository_source_edges.snapshot_id and is_project_member(s.project_id)));

drop policy if exists source_chunks_snapshot_access on public.repository_source_chunks;
create policy source_chunks_snapshot_access on public.repository_source_chunks for all to authenticated
    using (exists (select 1 from public.repository_snapshots s where s.id=repository_source_chunks.snapshot_id and is_project_member(s.project_id)))
    with check (exists (select 1 from public.repository_snapshots s where s.id=repository_source_chunks.snapshot_id and is_project_member(s.project_id)));

drop policy if exists generated_changes_finding_access on public.generated_changes;
create policy generated_changes_finding_access on public.generated_changes for all to authenticated
    using (exists (
        select 1 from public.impact_findings f
        join public.impact_analysis_runs r on r.id=f.run_id
        where f.id=generated_changes.finding_id and is_project_member(r.project_id)
    ))
    with check (exists (
        select 1 from public.impact_findings f
        join public.impact_analysis_runs r on r.id=f.run_id
        where f.id=generated_changes.finding_id and is_project_member(r.project_id)
    ));

drop policy if exists generated_validations_change_access on public.generated_change_validations;
create policy generated_validations_change_access on public.generated_change_validations for all to authenticated
    using (exists (
        select 1 from public.generated_changes c
        join public.impact_findings f on f.id=c.finding_id
        join public.impact_analysis_runs r on r.id=f.run_id
        where c.id=generated_change_validations.generated_change_id and is_project_member(r.project_id)
    ))
    with check (exists (
        select 1 from public.generated_changes c
        join public.impact_findings f on f.id=c.finding_id
        join public.impact_analysis_runs r on r.id=f.run_id
        where c.id=generated_change_validations.generated_change_id and is_project_member(r.project_id)
    ));

commit;
