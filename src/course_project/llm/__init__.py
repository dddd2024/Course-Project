"""Provider-neutral LLM hypothesis generation boundaries."""

from course_project.llm.provider import (
    DeterministicMockLLMProvider,
    HypothesisProposal,
    LLMHypothesisProvider,
    LLMHypothesisRequest,
    LLMProviderResult,
    OfflineNoopLLMProvider,
    ProviderMode,
    materialize_hypotheses,
)

__all__ = [
    "DeterministicMockLLMProvider",
    "HypothesisProposal",
    "LLMHypothesisProvider",
    "LLMHypothesisRequest",
    "LLMProviderResult",
    "OfflineNoopLLMProvider",
    "ProviderMode",
    "materialize_hypotheses",
]
