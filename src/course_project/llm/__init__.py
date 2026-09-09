"""Provider-neutral LLM hypothesis generation boundaries."""

from course_project.llm.live_provider import (
    JSONTransport,
    LiveLLMProviderError,
    LiveLLMResponseError,
    LiveLLMTransportError,
    OpenAICompatibleLLMProvider,
    OpenAICompatibleProviderConfig,
    StructuredOutputMode,
    UrllibJSONTransport,
    build_chat_completion_payload,
    parse_chat_completion_response,
)
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
    "JSONTransport",
    "LLMHypothesisProvider",
    "LLMHypothesisRequest",
    "LLMProviderResult",
    "LiveLLMProviderError",
    "LiveLLMResponseError",
    "LiveLLMTransportError",
    "OfflineNoopLLMProvider",
    "OpenAICompatibleLLMProvider",
    "OpenAICompatibleProviderConfig",
    "ProviderMode",
    "StructuredOutputMode",
    "UrllibJSONTransport",
    "build_chat_completion_payload",
    "materialize_hypotheses",
    "parse_chat_completion_response",
]
