"""Harmonize terms with the agentic Bedrock provider."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from threading import local

from agent_experiment import (
    GPT_5_6_LUNA,
    GPT_5_6_SOL,
    NO_MATCH,
    ConverseClient,
    IndexBundle,
    Model,
    Provider,
    PvsIndex,
    ReasoningEffort,
    build_all_indexes,
    build_pvs_index,
    harmonize_term,
    make_provider_client,
)

from src.domain.harmonization import MatchFidelity
from src.integrations.harmonize import (
    TermHarmonizationRequest,
    TermHarmonizationResponse,
)

logger = logging.getLogger(__name__)

_TermIndexes = tuple[PvsIndex, IndexBundle]


def _elapsed_ms(started_at: float) -> int:
    return max(round((time.perf_counter() - started_at) * 1000), 0)


@dataclass(frozen=True)
class AgenticHarmonizeConfig:
    region: str
    explorer_model: Model = GPT_5_6_LUNA
    shortlister_model: Model = GPT_5_6_LUNA
    selector_model: Model = GPT_5_6_SOL
    reasoning_effort: ReasoningEffort = ReasoningEffort.HIGH
    exploration_turns: int = 10
    max_workers: int = 100

    def __post_init__(self) -> None:
        if not self.region.strip():
            raise ValueError("Agentic harmonization requires an AWS region")
        if self.exploration_turns < 1:
            raise ValueError("Agentic exploration turns must be positive")
        if self.max_workers < 1:
            raise ValueError("Agentic worker count must be positive")
        if self.max_workers > 100:
            raise ValueError("Agentic worker count must not exceed 100")


class _WorkerState(local):
    client: ConverseClient | None = None


class _BatchExecutionError(Exception):
    def __init__(self, error: Exception, time_to_first_error_ms: int) -> None:
        super().__init__(str(error))
        self.error = error
        self.time_to_first_error_ms = time_to_first_error_ms


class AgenticTermHarmonizer:
    """Run one bounded Bedrock request for each unique source term."""

    def __init__(self, config: AgenticHarmonizeConfig) -> None:
        self._config = config
        self._worker_state = _WorkerState()

    def harmonize(
        self,
        requests: tuple[TermHarmonizationRequest, ...],
    ) -> tuple[TermHarmonizationResponse, ...]:
        if not requests:
            return ()
        indexes = _build_indexes(requests)
        responses: list[TermHarmonizationResponse | None] = [None] * len(requests)
        worker_count = min(self._config.max_workers, len(requests))
        started_at = time.perf_counter()
        logger.info(
            "Agentic harmonization batch started",
            extra={
                "event_name": "harmonization.agentic_batch.started",
                "term_count": len(requests),
                "worker_count": worker_count,
                "configured_worker_limit": self._config.max_workers,
                "exploration_turns": self._config.exploration_turns,
                "explorer_model": self._config.explorer_model.name,
                "shortlister_model": self._config.shortlister_model.name,
                "selector_model": self._config.selector_model.name,
            },
        )
        try:
            self._run_requests(requests, indexes, responses, worker_count, started_at)
        except _BatchExecutionError as failure:
            logger.warning(
                "Agentic harmonization batch failed",
                extra={
                    "event_name": "harmonization.agentic_batch.failed",
                    "term_count": len(requests),
                    "worker_count": worker_count,
                    "configured_worker_limit": self._config.max_workers,
                    "duration_ms": _elapsed_ms(started_at),
                    "time_to_first_error_ms": failure.time_to_first_error_ms,
                    "error_type": type(failure.error).__name__,
                },
            )
            raise failure.error from failure
        if any(response is None for response in responses):
            raise RuntimeError("Agentic harmonization returned an incomplete result")
        logger.info(
            "Agentic harmonization batch completed",
            extra={
                "event_name": "harmonization.agentic_batch.completed",
                "term_count": len(requests),
                "worker_count": worker_count,
                "configured_worker_limit": self._config.max_workers,
                "duration_ms": _elapsed_ms(started_at),
            },
        )
        return tuple(response for response in responses if response is not None)

    def _run_requests(
        self,
        requests: tuple[TermHarmonizationRequest, ...],
        indexes: dict[tuple[str, ...], _TermIndexes],
        responses: list[TermHarmonizationResponse | None],
        worker_count: int,
        started_at: float | None = None,
    ) -> None:
        started_at = time.perf_counter() if started_at is None else started_at
        work = iter(enumerate(requests))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures: dict[Future[TermHarmonizationResponse], int] = {}
            for _ in range(worker_count):
                index, request = next(work)
                futures[self._submit_request(executor, request, indexes)] = index
            try:
                self._complete_requests(executor, work, indexes, futures, responses)
            except Exception as exc:
                time_to_first_error_ms = _elapsed_ms(started_at)
                for future in futures:
                    future.cancel()
                raise _BatchExecutionError(exc, time_to_first_error_ms) from exc

    def _submit_request(
        self,
        executor: ThreadPoolExecutor,
        request: TermHarmonizationRequest,
        indexes: dict[tuple[str, ...], _TermIndexes],
    ) -> Future[TermHarmonizationResponse]:
        return executor.submit(self._harmonize_term, request, indexes[request.permissible_values])

    def _complete_requests(
        self,
        executor: ThreadPoolExecutor,
        work: Iterator[tuple[int, TermHarmonizationRequest]],
        indexes: dict[tuple[str, ...], _TermIndexes],
        futures: dict[Future[TermHarmonizationResponse], int],
        responses: list[TermHarmonizationResponse | None],
    ) -> None:
        while futures:
            completed, _pending = wait(futures, return_when=FIRST_COMPLETED)
            for future in completed:
                responses[futures.pop(future)] = future.result()
                item = next(work, None)
                if item is not None:
                    index, request = item
                    futures[self._submit_request(executor, request, indexes)] = index

    def _harmonize_term(
        self,
        request: TermHarmonizationRequest,
        indexes: tuple[PvsIndex, IndexBundle],
    ) -> TermHarmonizationResponse:
        result = harmonize_term(
            self._provider_client(),
            indexes[0],
            request.input_term,
            indexes=indexes[1],
            explorer_model=self._config.explorer_model,
            shortlister_model=self._config.shortlister_model,
            selector_model=self._config.selector_model,
            exploration_turns=self._config.exploration_turns,
            context=request.context,
        )
        predicted = result.prediction.predicted_match
        fidelity = MatchFidelity.NONE if predicted == NO_MATCH else MatchFidelity(result.prediction.match_fidelity)
        return TermHarmonizationResponse(
            matched_value=None if predicted == NO_MATCH else predicted,
            match_fidelity=fidelity,
        )

    def _provider_client(self) -> ConverseClient:
        client = self._worker_state.client
        if client is None:
            client = make_provider_client(
                self._config.region,
                provider=Provider.BEDROCK,
                reasoning_effort=self._config.reasoning_effort,
            )
            self._worker_state.client = client
        return client


def _build_indexes(
    requests: tuple[TermHarmonizationRequest, ...],
) -> dict[tuple[str, ...], _TermIndexes]:
    indexes: dict[tuple[str, ...], _TermIndexes] = {}
    for request in requests:
        if request.permissible_values in indexes:
            continue
        pvs_index = build_pvs_index(list(request.permissible_values))
        indexes[request.permissible_values] = (pvs_index, build_all_indexes(pvs_index))
    return indexes


__all__ = [
    "AgenticHarmonizeConfig",
    "AgenticTermHarmonizer",
]
