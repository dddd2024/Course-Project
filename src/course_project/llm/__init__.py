"""Structured semantic-hypothesis generation."""


from course_project.llm.generator import (
    HypothesisGenerationError,
    HypothesisGenerator,
    HypothesisProvider,
    MockLLMProvider,
)
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
    LLMFileAnalysis,
    LLMHypothesisProvider,
    LLMHypothesisRequest,
    LLMProviderResult,
    OfflineNoopLLMProvider,
    ProviderMode,
    materialize_hypotheses,
)

__all__ = [
    "DeterministicMockLLMProvider",
    "HypothesisGenerationError",
    "HypothesisGenerator",
    "HypothesisProposal",
    "HypothesisProvider",
    "JSONTransport",
    "LLMFileAnalysis",
    "LLMHypothesisProvider",
    "LLMHypothesisRequest",
    "LLMProviderResult",
    "LiveLLMProviderError",
    "LiveLLMResponseError",
    "LiveLLMTransportError",
    "MockLLMProvider",
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
