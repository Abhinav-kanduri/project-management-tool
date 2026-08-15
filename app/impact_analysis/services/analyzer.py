from __future__ import annotations

import logging
from collections import Counter
from typing import Any
from uuid import UUID

from app.impact_analysis.comparison import ComparisonResult, DeterministicComparator
from app.impact_analysis.context import ContextBuilder
from app.impact_analysis.domain import RequirementPackage
from app.impact_analysis.enums import AnalysisStage, FindingStatus, RunStatus
from app.impact_analysis.graph.actual_sync import ActualGraphSynchronizer
from app.impact_analysis.graph.expected_builder import ExpectedGraphBuilder
from app.impact_analysis.graph.expected_sync import ExpectedGraphSynchronizer
from app.impact_analysis.repositories.analysis import AnalysisRepository
from app.impact_analysis.repositories.results import AnalysisResultRepository
from app.impact_analysis.retrieval.hybrid import HybridRetriever
from app.impact_analysis.retrieval.keyword import KeywordRetriever
from app.impact_analysis.retrieval.structured import StructuredRetriever
from app.impact_analysis.retrieval.vector import VectorRetriever
from app.impact_analysis.schemas import AtomicRequirement, StartAnalysisRequest
from app.impact_analysis.scoring import COMPLETION, calculate_score
from app.impact_analysis.services.design_context import DesignContextService
from app.impact_analysis.services.evidence import EvidenceMaterializer
from app.impact_analysis.services.requirement_decomposer import RequirementDecomposer
from app.impact_analysis.services.scope_resolver import ScopeResolver
from app.impact_analysis.services.snapshot_service import SnapshotService


logger = logging.getLogger(__name__)


class ImpactAnalysisService:
    def __init__(
        self,
        *,
        scope_resolver: ScopeResolver | None = None,
        analysis_repository: AnalysisRepository | None = None,
        result_repository: AnalysisResultRepository | None = None,
        design_service: DesignContextService | None = None,
        decomposer: RequirementDecomposer | None = None,
        snapshot_service: SnapshotService | None = None,
        expected_sync: ExpectedGraphSynchronizer | None = None,
        actual_sync: ActualGraphSynchronizer | None = None,
        structured_retriever: StructuredRetriever | None = None,
        keyword_retriever: KeywordRetriever | None = None,
        vector_retriever: VectorRetriever | None = None,
        comparator: DeterministicComparator | None = None,
    ) -> None:
        self.scope_resolver = scope_resolver or ScopeResolver()
        self.analysis_repository = analysis_repository or AnalysisRepository()
        self.result_repository = result_repository or AnalysisResultRepository()
        self.design_service = design_service or DesignContextService()
        self.decomposer = decomposer or RequirementDecomposer()
        self.snapshot_service = snapshot_service or SnapshotService()
        self.expected_sync = expected_sync
        self.actual_sync = actual_sync
        self.structured_retriever = structured_retriever or StructuredRetriever()
        self.keyword_retriever = keyword_retriever or KeywordRetriever()
        self.vector_retriever = vector_retriever or VectorRetriever()
        self.comparator = comparator or DeterministicComparator()
        self.hybrid = HybridRetriever()
        self.context_builder = ContextBuilder()
        self.evidence_materializer = EvidenceMaterializer()

    def start(
        self, *, request: StartAnalysisRequest, actor: str
    ) -> tuple[dict[str, Any], RequirementPackage | None]:
        package = self.scope_resolver.resolve(
            actor=actor,
            product_space_id=request.product_space_id,
            project_id=request.project_id,
            release_id=request.release_id,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            project_repository_id=request.project_repository_id,
        )
        row, created = self.analysis_repository.create_or_get(
            package=package, request=request, actor=actor
        )
        return row, package if created else None

    async def process(
        self,
        *,
        run_id: UUID,
        request: StartAnalysisRequest,
        package: RequirementPackage,
    ) -> None:
        try:
            self._stage(run_id, AnalysisStage.DESIGN_CONTEXT, 8, "Loading approved design context")
            design = self.design_service.load(package)
            self._stage(
                run_id,
                AnalysisStage.REQUIREMENT_DECOMPOSITION,
                15,
                "Creating atomic requirements",
            )
            requirements = self.decomposer.decompose(package, design)
            requirements = self.analysis_repository.replace_requirements(run_id, requirements)

            self._stage(run_id, AnalysisStage.EXPECTED_GRAPH, 24, "Synchronizing expected graph")
            expected = ExpectedGraphBuilder().build(
                run_id=run_id, package=package, requirements=requirements
            )
            try:
                (self.expected_sync or ExpectedGraphSynchronizer()).sync(run_id, expected)
            except Exception as graph_error:
                logger.warning(
                    "Expected graph sync unavailable for run %s: %s",
                    run_id,
                    graph_error,
                )

            self._stage(run_id, AnalysisStage.GITHUB_SNAPSHOT, 34, "Pinning GitHub commit")
            snapshot = await self.snapshot_service.create(
                package=package,
                requested_ref=request.ref,
                force_refresh=request.force_repository_refresh,
                progress_callback=lambda stage, progress, message: self._stage(
                    run_id, stage, progress, message
                ),
            )
            snapshot_id = UUID(str(snapshot["id"]))
            self._stage(
                run_id,
                AnalysisStage.ACTUAL_GRAPH,
                52,
                "Synchronizing actual implementation graph",
                snapshot_id=snapshot_id,
            )
            try:
                (self.actual_sync or ActualGraphSynchronizer()).sync(
                    run_id=run_id,
                    snapshot_id=snapshot_id,
                    repository_name=package.repository.full_name,
                    project_id=package.project.project_id,
                )
            except Exception as graph_error:
                logger.warning(
                    "Actual graph sync unavailable for run %s: %s",
                    run_id,
                    graph_error,
                )

            comparisons: list[tuple[AtomicRequirement, ComparisonResult]] = []
            total = max(1, len(requirements))
            for index, requirement in enumerate(requirements, start=1):
                progress = 55 + int(index / total * 25)
                self._stage(
                    run_id,
                    AnalysisStage.EVIDENCE_RETRIEVAL,
                    progress,
                    f"Retrieving evidence for {requirement.requirement_key}",
                )
                candidates = self._retrieve(
                    run_id=run_id,
                    snapshot_id=snapshot_id,
                    query=requirement.text,
                )
                evidence = self.evidence_materializer.materialize(
                    run_id=run_id,
                    requirement_id=requirement.requirement_id,
                    repository=package.repository.full_name,
                    commit_sha=snapshot["commit_sha"],
                    candidates=candidates,
                )
                context = self.context_builder.build(
                    requirement=requirement,
                    package=package,
                    design=design,
                    candidates=candidates,
                    snapshot=snapshot,
                )
                comparisons.append(
                    (requirement, self.comparator.compare(context=context, evidence=evidence))
                )

            self._stage(run_id, AnalysisStage.SCORING, 86, "Calculating deterministic score")
            score = calculate_score(
                [
                    (result.candidate.candidate_status, requirement.weight)
                    for requirement, result in comparisons
                ]
            )
            self._stage(run_id, AnalysisStage.PERSISTING, 92, "Persisting findings")
            for index, (requirement, result) in enumerate(comparisons):
                status = result.candidate.candidate_status
                completion = None if status == FindingStatus.UNKNOWN else COMPLETION[status]
                self.analysis_repository.replace_result(
                    run_id=run_id,
                    snapshot_id=snapshot_id,
                    requirement=requirement,
                    evidence=list(result.evidence),
                    finding=result.candidate,
                    predicate_results=list(result.predicate_results),
                    completion=completion,
                    contribution=score.contributions[index],
                )
            counts = Counter(result.candidate.candidate_status for _, result in comparisons)
            self.result_repository.complete(
                run_id=run_id,
                score=score.score,
                applicable_weight=score.applicable_weight,
                excluded_weight=score.excluded_weight,
                counts=dict(counts),
            )
        except Exception as error:
            logger.exception("Impact analysis run failed", extra={"run_id": str(run_id)})
            self.analysis_repository.fail(
                run_id,
                code=type(error).__name__.upper()[:100],
                message=str(error),
            )

    def _retrieve(self, *, run_id: UUID, snapshot_id: UUID, query: str):
        structured = self.structured_retriever.search(
            snapshot_id=snapshot_id, query=query, limit=30
        )
        keyword = self.keyword_retriever.search(
            snapshot_id=snapshot_id, query=query, limit=30
        )
        vector = self.vector_retriever.search(
            snapshot_id=snapshot_id, query=query, limit=30
        )
        return self.hybrid.fuse([structured, keyword, vector], limit=20)

    def _stage(
        self,
        run_id: UUID,
        stage: AnalysisStage,
        progress: int,
        message: str,
        *,
        snapshot_id: UUID | None = None,
    ) -> None:
        self.analysis_repository.update_stage(
            run_id,
            status=RunStatus.RUNNING,
            stage=stage,
            progress=progress,
            message=message,
            snapshot_id=snapshot_id,
        )
