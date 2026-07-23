"""Provider-neutral, chapter-atomic AI editing orchestration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, Iterable

from rules.em_dash import remove_spaced_em_dashes

from .chunking import estimate_tokens, plan_chunks, safe_input_budget
from .errors import AIProviderError, ContextTooLong, ProviderUnavailable
from .models import AIOutcome, CompletionRequest, RunPolicy
from .prompt import PromptBundle, build_system_prompt
from .provenance import build_provenance
from .provider import AIProvider
from .validation import GATE_VERSION, validate_candidate


@dataclass(frozen=True)
class EditorOptions:
    model_id: str
    policy: RunPolicy = RunPolicy.SCRIPT_ONLY
    temperature: float = 0.0
    seed: int | None = 0
    timeout_seconds: float = 120.0
    request_overhead_tokens: int = 128
    safety_margin_tokens: int = 256


class AIEditor:
    def __init__(
        self,
        provider_factory: Callable[[], AIProvider] | None,
        options: EditorOptions,
    ):
        self._provider_factory = provider_factory
        self.options = options

    def edit(self, baseline: str, *, protected_terms: Iterable[str] = ()) -> AIOutcome:
        if self.options.policy is RunPolicy.SCRIPT_ONLY:
            return AIOutcome(baseline, "script_only", False, False)
        try:
            if self._provider_factory is None:
                raise ProviderUnavailable("No provider factory configured.", retryable=False)
            provider = self._provider_factory()
            capabilities = provider.capabilities()
            prompt = build_system_prompt(tuple(protected_terms))
            budget = safe_input_budget(
                context_limit=capabilities.context_limit,
                max_output_limit=capabilities.max_output_tokens,
                serialized_prompt_tokens=estimate_tokens(prompt.system_prompt),
                request_overhead_tokens=self.options.request_overhead_tokens,
                safety_margin_tokens=self.options.safety_margin_tokens,
            )
            plan = plan_chunks(baseline, max_input_tokens=budget)
        except (AIProviderError, ContextTooLong) as exc:
            if self.options.policy is RunPolicy.AI_REQUIRED:
                raise
            return AIOutcome(baseline, "fallback", False, True, (type(exc).__name__,))

        accepted: list[str] = []
        records: list[dict] = []
        retry_total = 0
        failure_reasons: tuple[str, ...] = ()
        for chunk in plan.chunks:
            chunk_accepted = False
            for attempt in range(2):
                if attempt:
                    retry_total += 1
                request = CompletionRequest(
                    text=chunk.text,
                    system_prompt=prompt.system_prompt,
                    prompt_version=prompt.prompt_version,
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
                        protected_terms=protected_terms,
                        finish_reason=result.finish_reason,
                        truncated=result.truncated,
                    )
                    status = "accepted" if validation.accepted else "rejected"
                    failure_reasons = tuple(reason.value for reason in validation.reasons)
                    records.append(
                        build_provenance(
                            chunk.text,
                            validation.candidate,
                            provider=capabilities.provider_name,
                            model_id=result.model_id,
                            prompt_version=prompt.prompt_version,
                            gate_version=GATE_VERSION,
                            status=status,
                            rejection_reasons=failure_reasons,
                            retry_count=attempt,
                            duration_seconds=result.duration_seconds,
                            outer_fence_unwrapped=validation.outer_fence_unwrapped,
                            input_tokens=result.input_tokens,
                            output_tokens=result.output_tokens,
                        ).to_dict()
                    )
                    if validation.accepted:
                        accepted.append(validation.candidate)
                        chunk_accepted = True
                        break
                except AIProviderError as exc:
                    failure_reasons = (type(exc).__name__,)
                    if not exc.retryable:
                        break
                except (TimeoutError, OSError) as exc:
                    failure_reasons = (type(exc).__name__,)
                if attempt == 1:
                    break
            if not chunk_accepted:
                return AIOutcome(
                    baseline,
                    "fallback",
                    False,
                    True,
                    failure_reasons,
                    len(plan.chunks),
                    retry_total,
                    tuple(records),
                )

        candidate = plan.reassemble(accepted)
        candidate = remove_spaced_em_dashes(candidate)
        final = validate_candidate(baseline, candidate, protected_terms=protected_terms)
        if not final.accepted:
            return AIOutcome(
                baseline,
                "fallback",
                False,
                True,
                tuple(reason.value for reason in final.reasons),
                len(plan.chunks),
                retry_total,
                tuple(records),
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
