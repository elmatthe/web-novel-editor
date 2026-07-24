"""Provider-neutral, chapter-atomic AI editing orchestration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, Iterable

from core.protected_lexicon import (
    ProtectedLexicon,
    mask_protected_terms,
    unmask_placeholders,
)
from rules.em_dash import remove_spaced_em_dashes

from .chunking import CHUNKER_VERSION, estimate_tokens, plan_chunks, safe_input_budget
from .errors import (
    AIProviderError,
    ContextTooLong,
    InvalidResponse,
    ModelUnavailable,
    ProviderUnavailable,
    TransientNetworkError,
)
from .models import (
    AIOutcome,
    CompletionRequest,
    ProtectionStrategy,
    ProviderRunState,
    ProviderStatus,
    RunPolicy,
)
from .prompt import PromptBundle, build_retry_prompt, build_system_prompt
from .provenance import build_provenance
from .provider import AIProvider
from .validation import GATE_VERSION, RejectionReason, validate_candidate


@dataclass(frozen=True)
class EditorOptions:
    model_id: str
    policy: RunPolicy = RunPolicy.SCRIPT_ONLY
    protection_strategy: ProtectionStrategy = ProtectionStrategy.MASK
    temperature: float = 0.0
    seed: int | None = 0
    timeout_seconds: float = 120.0
    request_overhead_tokens: int = 128
    safety_margin_tokens: int = 256


def _lexicon_from_terms(terms: tuple[str, ...]) -> ProtectedLexicon:
    multi = sorted((term for term in terms if " " in term), key=len, reverse=True)
    single = sorted((term for term in terms if " " not in term), key=len, reverse=True)
    ordered = tuple(dict.fromkeys(multi + single))
    return ProtectedLexicon(ordered, frozenset(term.lower() for term in ordered))


class AIEditor:
    """One run-scoped editor.

    Provider construction happens at most once. An exhausted provider outage makes the
    run unavailable: ``prefer_ai`` uses honest fallback for later chapters without
    reconstructing it, while ``ai_required`` raises and never silently degrades.
    Gate rejection is chapter-local and does not poison a healthy provider for the next
    chapter.
    """

    def __init__(
        self,
        provider_factory: Callable[[], AIProvider] | None,
        options: EditorOptions,
    ):
        self._provider_factory = provider_factory
        self.options = options
        self._provider: AIProvider | None = None
        self._capabilities = None
        self._state = ProviderRunState.UNINITIALIZED
        self._unavailable_reason = "Provider unavailable for this run."

    @property
    def run_state(self) -> ProviderRunState:
        return self._state

    def prepare_run(self) -> ProviderRunState:
        """Establish provider availability once before a batch starts.

        Script-only runs deliberately do nothing. AI-required callers use this
        preflight to fail before processing any chapter; prefer-AI callers may
        also use it, but batch integration leaves their first check at the first
        chapter so an unavailable provider becomes an honest chapter fallback.
        """
        if self.options.policy is RunPolicy.SCRIPT_ONLY:
            return self._state
        provider = self._provider_for_run()
        try:
            status = provider.health_check()
            if status is not ProviderStatus.OK:
                raise ProviderUnavailable(
                    f"Provider preflight failed: {status.value}.", retryable=False
                )
            if (
                self._capabilities is not None
                and self.options.model_id not in self._capabilities.model_ids
            ):
                raise ModelUnavailable(
                    f"Model unavailable: {self.options.model_id}", retryable=False
                )
        except (AIProviderError, OSError, TimeoutError) as exc:
            self._mark_unavailable(f"{type(exc).__name__}: {exc}")
            raise
        return self._state

    def _provider_for_run(self) -> AIProvider:
        if self._state is ProviderRunState.UNAVAILABLE:
            raise ProviderUnavailable(self._unavailable_reason, retryable=False)
        if self._provider is not None:
            return self._provider
        if self._provider_factory is None:
            self._mark_unavailable("No provider factory configured.")
            raise ProviderUnavailable(self._unavailable_reason, retryable=False)
        try:
            provider = self._provider_factory()
            capabilities = provider.capabilities()
        except (AIProviderError, OSError, TimeoutError) as exc:
            self._mark_unavailable(f"{type(exc).__name__}: {exc}")
            raise
        self._provider = provider
        self._capabilities = capabilities
        self._state = ProviderRunState.AVAILABLE
        return provider

    def _mark_unavailable(self, reason: str) -> None:
        self._state = ProviderRunState.UNAVAILABLE
        self._unavailable_reason = reason

    def _fallback_or_raise(
        self,
        baseline: str,
        reasons: tuple[str, ...],
        *,
        chunk_count: int = 0,
        retry_count: int = 0,
        records: tuple[dict, ...] = (),
        cause: BaseException | None = None,
    ) -> AIOutcome:
        if self.options.policy is RunPolicy.AI_REQUIRED:
            if isinstance(cause, BaseException):
                raise cause
            raise InvalidResponse(
                "AI-required chapter was not accepted: " + ", ".join(reasons),
                retryable=False,
            )
        return AIOutcome(
            baseline,
            "fallback",
            False,
            True,
            reasons,
            chunk_count,
            retry_count,
            records,
        )

    def edit(self, baseline: str, *, protected_terms: Iterable[str] = ()) -> AIOutcome:
        if self.options.policy is RunPolicy.SCRIPT_ONLY:
            return AIOutcome(baseline, "script_only", False, False)

        terms = tuple(protected_terms)
        lexicon = _lexicon_from_terms(terms)
        prompt = build_system_prompt(lexicon.terms)
        try:
            provider = self._provider_for_run()
            capabilities = self._capabilities
            if capabilities is None:  # defensive: _provider_for_run establishes both
                raise ProviderUnavailable("Provider capabilities unavailable.", retryable=False)
            if "__WE_" in baseline:
                raise InvalidResponse(
                    "Deterministic baseline contains a reserved placeholder prefix.",
                    retryable=False,
                )
            working_baseline = baseline
            protected_map: dict[str, str] = {}
            if self.options.protection_strategy is ProtectionStrategy.MASK:
                working_baseline, protected_map = mask_protected_terms(baseline, lexicon)
            budget = safe_input_budget(
                context_limit=capabilities.context_limit,
                max_output_limit=capabilities.max_output_tokens,
                serialized_prompt_tokens=estimate_tokens(prompt.system_prompt),
                request_overhead_tokens=self.options.request_overhead_tokens,
                safety_margin_tokens=self.options.safety_margin_tokens,
            )
            plan = plan_chunks(working_baseline, max_input_tokens=budget)
        except (AIProviderError, ContextTooLong, OSError, TimeoutError) as exc:
            return self._fallback_or_raise(
                baseline, (type(exc).__name__,), cause=exc
            )

        accepted: list[str] = []
        records: list[dict] = []
        retry_total = 0
        failure_reasons: tuple[str, ...] = ()
        for chunk in plan.chunks:
            chunk_accepted = False
            stricter_retry = False
            provider_outage: BaseException | None = None
            for attempt_index in range(2):
                if attempt_index:
                    retry_total += 1
                attempt_prompt = build_retry_prompt(prompt) if stricter_retry else prompt
                request = CompletionRequest(
                    text=chunk.text,
                    system_prompt=attempt_prompt.system_prompt,
                    prompt_version=attempt_prompt.prompt_version,
                    model_id=self.options.model_id,
                    temperature=self.options.temperature,
                    seed=self.options.seed,
                    timeout_seconds=self.options.timeout_seconds,
                    max_output_tokens=min(capabilities.max_output_tokens, max(1, budget)),
                    request_id=str(uuid.uuid4()),
                )
                try:
                    result = provider.complete(request)
                    validation = validate_candidate(
                        chunk.text,
                        result.text,
                        protected_terms=(
                            terms
                            if self.options.protection_strategy is ProtectionStrategy.VERIFY
                            else ()
                        ),
                        finish_reason=result.finish_reason,
                        truncated=result.truncated,
                    )
                    status = "accepted" if validation.accepted else "rejected"
                    failure_reasons = tuple(reason.value for reason in validation.reasons)
                    records.append(
                        self._attempt_record(
                            chunk.text,
                            validation.candidate,
                            prompt,
                            attempt_prompt,
                            chunk.index,
                            chunk.count,
                            attempt_index,
                            status,
                            failure_reasons,
                            duration_seconds=result.duration_seconds,
                            model_id=result.model_id,
                            outer_fence_unwrapped=validation.outer_fence_unwrapped,
                            input_tokens=result.input_tokens,
                            output_tokens=result.output_tokens,
                        )
                    )
                    if validation.accepted:
                        accepted.append(validation.candidate)
                        chunk_accepted = True
                        break
                    # Every gate rejection, including malformed/truncated output, is
                    # eligible for the single stricter-prompt retry.
                    stricter_retry = True
                except AIProviderError as exc:
                    failure_reasons = (type(exc).__name__,)
                    records.append(
                        self._attempt_record(
                            chunk.text,
                            "",
                            prompt,
                            attempt_prompt,
                            chunk.index,
                            chunk.count,
                            attempt_index,
                            "provider_error",
                            failure_reasons,
                            model_id=self.options.model_id,
                            include_diff=False,
                        )
                    )
                    stricter_retry = isinstance(exc, InvalidResponse)
                    if isinstance(
                        exc,
                        (
                            ProviderUnavailable,
                            ModelUnavailable,
                            TransientNetworkError,
                        ),
                    ):
                        provider_outage = exc
                    if not exc.retryable:
                        break
                except (TimeoutError, OSError) as exc:
                    failure_reasons = (type(exc).__name__,)
                    provider_outage = exc
                    records.append(
                        self._attempt_record(
                            chunk.text,
                            "",
                            prompt,
                            attempt_prompt,
                            chunk.index,
                            chunk.count,
                            attempt_index,
                            "provider_error",
                            failure_reasons,
                            model_id=self.options.model_id,
                            include_diff=False,
                        )
                    )
                    stricter_retry = False
            if not chunk_accepted:
                if provider_outage is not None:
                    self._mark_unavailable(
                        f"{type(provider_outage).__name__}: {provider_outage}"
                    )
                return self._fallback_or_raise(
                    baseline,
                    failure_reasons,
                    chunk_count=len(plan.chunks),
                    retry_count=retry_total,
                    records=tuple(records),
                    cause=provider_outage,
                )

        candidate = plan.reassemble(accepted)
        if self.options.protection_strategy is ProtectionStrategy.MASK:
            candidate = unmask_placeholders(candidate, protected_map, {})
        if "__WE_" in candidate:
            return self._fallback_or_raise(
                baseline,
                (RejectionReason.PLACEHOLDER_DAMAGED.value,),
                chunk_count=len(plan.chunks),
                retry_count=retry_total,
                records=tuple(records),
            )
        candidate = remove_spaced_em_dashes(candidate)
        final = validate_candidate(baseline, candidate, protected_terms=terms)
        if not final.accepted:
            return self._fallback_or_raise(
                baseline,
                tuple(reason.value for reason in final.reasons),
                chunk_count=len(plan.chunks),
                retry_count=retry_total,
                records=tuple(records),
            )
        return AIOutcome(
            final.candidate,
            "accepted",
            True,
            False,
            (),
            len(plan.chunks),
            retry_total,
            tuple(records),
        )

    def _attempt_record(
        self,
        baseline: str,
        candidate: str,
        base_prompt: PromptBundle,
        attempt_prompt: PromptBundle,
        chunk_index: int,
        chunk_count: int,
        attempt_index: int,
        status: str,
        reasons: tuple[str, ...],
        *,
        duration_seconds: float = 0.0,
        model_id: str,
        outer_fence_unwrapped: bool = False,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        include_diff: bool = True,
    ) -> dict:
        provider_name = (
            self._capabilities.provider_name
            if self._capabilities is not None
            else "unknown"
        )
        return build_provenance(
            baseline,
            candidate,
            provider=provider_name,
            model_id=model_id,
            prompt_version=attempt_prompt.prompt_version,
            gate_version=GATE_VERSION,
            lexicon_hash=base_prompt.lexicon_hash,
            lexicon_version=base_prompt.lexicon_version,
            protection_strategy=self.options.protection_strategy.value,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
            chunker_version=CHUNKER_VERSION,
            attempt_number=attempt_index + 1,
            status=status,
            rejection_reasons=reasons,
            retry_count=attempt_index,
            duration_seconds=duration_seconds,
            outer_fence_unwrapped=outer_fence_unwrapped,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            include_diff=include_diff,
        ).to_dict()
