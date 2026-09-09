from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import urlparse

from course_project.llm.provider import (
    HypothesisProposal,
    LLMHypothesisProvider,
    LLMHypothesisRequest,
    LLMProviderResult,
    ProviderMode,
    materialize_hypotheses,
)

StructuredOutputMode = Literal["json_object", "prompt_only"]

_DEFAULT_SECRET_ENV = "COURSE_PROJECT_LLM_API_KEY"
_MAX_RESPONSE_BYTES = 2_000_000
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REQUIRED_PROPOSAL_KEYS = frozenset(
    {
        "offset",
        "size",
        "semanticType",
        "interpretation",
        "parameters",
        "modelConfidence",
        "supportingEvidenceIds",
    }
)

_SYSTEM_PROMPT = """You infer candidate semantic fields in an unknown binary protocol.
Return JSON only. Do not claim a hypothesis is verified: modelConfidence is model confidence only.
Use only evidence IDs listed in allowedEvidenceIds. Do not invent evidence IDs.
The response must be exactly one JSON object with this shape:
{
  "hypotheses": [
    {
      "offset": 0,
      "size": 1,
      "semanticType": "length|sequence|enum|timestamp|constant|checksum|other",
      "interpretation": "short human-readable interpretation",
      "parameters": {},
      "modelConfidence": 0.0,
      "supportingEvidenceIds": []
    }
  ]
}
Every offset must be a non-negative integer; size is a positive integer or null; confidence is in [0,1].
If there is insufficient evidence, return {"hypotheses": []}.
"""


class LiveLLMProviderError(RuntimeError):
    """Base class for fail-closed live-provider failures."""


class LiveLLMTransportError(LiveLLMProviderError):
    """Raised when the HTTPS transport cannot obtain a valid JSON response."""


class LiveLLMResponseError(LiveLLMProviderError):
    """Raised when a provider response violates the expected structured contract."""


class JSONTransport(Protocol):
    """Injectable transport used by the live provider and deterministic tests."""

    def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """POST one JSON object and return one JSON object."""


@dataclass(frozen=True, slots=True)
class OpenAICompatibleProviderConfig:
    """Non-secret configuration for one OpenAI-compatible chat-completions endpoint."""

    endpoint: str
    model: str
    api_key_env: str = _DEFAULT_SECRET_ENV
    timeout_seconds: float = 30.0
    structured_output: StructuredOutputMode = "json_object"

    def __post_init__(self) -> None:
        endpoint = _https_endpoint(self.endpoint)
        model = _text(self.model, "model")
        api_key_env = _environment_name(self.api_key_env)
        timeout_seconds = _positive_finite(self.timeout_seconds, "timeout_seconds")
        if self.structured_output not in {"json_object", "prompt_only"}:
            raise ValueError(
                "structured_output must be 'json_object' or 'prompt_only'"
            )
        object.__setattr__(self, "endpoint", endpoint)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "api_key_env", api_key_env)
        object.__setattr__(self, "timeout_seconds", timeout_seconds)

    @classmethod
    def from_environment(
        cls,
        *,
        prefix: str = "COURSE_PROJECT_LLM_",
    ) -> OpenAICompatibleProviderConfig:
        """Load non-secret live-provider configuration from environment variables.

        The API key value itself is deliberately not read here or stored on the config.
        It is resolved from ``api_key_env`` only when a live request is executed.
        """

        prefix = _text(prefix, "environment prefix")
        endpoint_name = f"{prefix}ENDPOINT"
        model_name = f"{prefix}MODEL"
        secret_env_name = f"{prefix}API_KEY_ENV"
        timeout_name = f"{prefix}TIMEOUT_SECONDS"
        output_name = f"{prefix}STRUCTURED_OUTPUT"

        endpoint = _required_environment_value(endpoint_name)
        model = _required_environment_value(model_name)
        api_key_env = os.environ.get(secret_env_name, _DEFAULT_SECRET_ENV)
        timeout_text = os.environ.get(timeout_name, "30")
        structured_output = os.environ.get(output_name, "json_object")
        try:
            timeout_seconds = float(timeout_text)
        except ValueError as exc:
            raise ValueError(f"{timeout_name} must be numeric") from exc

        return cls(
            endpoint=endpoint,
            model=model,
            api_key_env=api_key_env,
            timeout_seconds=timeout_seconds,
            structured_output=structured_output,  # type: ignore[arg-type]
        )


class UrllibJSONTransport:
    """Small stdlib HTTPS JSON transport for OpenAI-compatible providers."""

    def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        endpoint = _https_endpoint(url)
        timeout = _positive_finite(timeout_seconds, "timeout_seconds")
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=encoded,
            headers=dict(headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(_MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise LiveLLMTransportError(
                f"provider returned HTTP status {exc.code}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LiveLLMTransportError("provider HTTPS request failed") from exc

        if len(body) > _MAX_RESPONSE_BYTES:
            raise LiveLLMTransportError("provider response exceeds size limit")
        try:
            decoded = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LiveLLMTransportError("provider response is not UTF-8") from exc
        try:
            parsed = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise LiveLLMTransportError("provider response is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise LiveLLMTransportError("provider response JSON must be an object")
        return parsed


class OpenAICompatibleLLMProvider:
    """Live provider for an OpenAI-compatible chat-completions endpoint."""

    mode: ProviderMode = "live"

    def __init__(
        self,
        config: OpenAICompatibleProviderConfig,
        *,
        transport: JSONTransport | None = None,
        provider_name: str = "openai-compatible",
    ) -> None:
        if not isinstance(config, OpenAICompatibleProviderConfig):
            raise TypeError("config must be OpenAICompatibleProviderConfig")
        self.config = config
        self.provider_name = _text(provider_name, "provider_name")
        self._transport = transport if transport is not None else UrllibJSONTransport()

    def propose(self, request: LLMHypothesisRequest) -> LLMProviderResult:
        # Reuse the existing project-native validator before any network operation.
        materialize_hypotheses(
            provider_name=self.provider_name,
            request=request,
            proposals=(),
        )
        api_key = _required_environment_value(self.config.api_key_env)
        payload = build_chat_completion_payload(self.config, request)
        response = self._transport.post_json(
            url=self.config.endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            payload=payload,
            timeout_seconds=self.config.timeout_seconds,
        )
        proposals = parse_chat_completion_response(response)
        hypotheses = materialize_hypotheses(
            provider_name=self.provider_name,
            request=request,
            proposals=proposals,
        )
        return LLMProviderResult(
            provider=self.provider_name,
            mode=self.mode,
            hypotheses=hypotheses,
            metadata=_result_metadata(self.config, response),
        )


def build_chat_completion_payload(
    config: OpenAICompatibleProviderConfig,
    request: LLMHypothesisRequest,
) -> dict[str, Any]:
    """Build the deterministic provider request body without resolving credentials."""

    if not isinstance(config, OpenAICompatibleProviderConfig):
        raise TypeError("config must be OpenAICompatibleProviderConfig")
    materialize_hypotheses(
        provider_name="payload-validator",
        request=request,
        proposals=(),
    )
    request_context = {
        "requestId": request.request_id,
        "inputId": request.input_id,
        "allowedEvidenceIds": list(request.allowed_evidence_ids),
        "context": request.context,
    }
    user_content = json.dumps(
        request_context,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
    }
    if config.structured_output == "json_object":
        payload["response_format"] = {"type": "json_object"}
    return payload


def parse_chat_completion_response(
    response: Mapping[str, Any],
) -> tuple[HypothesisProposal, ...]:
    """Parse an OpenAI-compatible response envelope into strict structured proposals."""

    if not isinstance(response, Mapping):
        raise TypeError("provider response must be a mapping")
    if response.get("error") is not None:
        raise LiveLLMResponseError("provider returned an error envelope")

    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LiveLLMResponseError("provider response requires a non-empty choices list")
    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        raise LiveLLMResponseError("provider choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        raise LiveLLMResponseError("provider choice requires a message object")
    refusal = message.get("refusal")
    if refusal not in (None, ""):
        raise LiveLLMResponseError("provider refused the structured hypothesis request")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise LiveLLMResponseError("provider message content must be a non-empty JSON string")

    try:
        document = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LiveLLMResponseError("provider message content is not valid JSON") from exc
    if not isinstance(document, dict):
        raise LiveLLMResponseError("provider message JSON must be an object")
    if set(document) != {"hypotheses"}:
        raise LiveLLMResponseError(
            "provider message JSON must contain exactly the 'hypotheses' property"
        )
    raw_hypotheses = document["hypotheses"]
    if not isinstance(raw_hypotheses, list):
        raise LiveLLMResponseError("provider hypotheses must be a list")

    proposals: list[HypothesisProposal] = []
    for index, raw in enumerate(raw_hypotheses):
        if not isinstance(raw, dict):
            raise LiveLLMResponseError(f"provider hypothesis {index} must be an object")
        if set(raw) != _REQUIRED_PROPOSAL_KEYS:
            raise LiveLLMResponseError(
                f"provider hypothesis {index} does not match the required schema"
            )
        supporting = raw["supportingEvidenceIds"]
        if not isinstance(supporting, list) or any(
            not isinstance(item, str) for item in supporting
        ):
            raise LiveLLMResponseError(
                f"provider hypothesis {index} supportingEvidenceIds must be a string list"
            )
        parameters = raw["parameters"]
        if not isinstance(parameters, dict):
            raise LiveLLMResponseError(
                f"provider hypothesis {index} parameters must be an object"
            )
        proposals.append(
            HypothesisProposal(
                offset=raw["offset"],
                size=raw["size"],
                semantic_type=raw["semanticType"],
                interpretation=raw["interpretation"],
                parameters=parameters,
                model_confidence=raw["modelConfidence"],
                supporting_evidence_ids=tuple(supporting),
            )
        )
    return tuple(proposals)


def _result_metadata(
    config: OpenAICompatibleProviderConfig,
    response: Mapping[str, Any],
) -> dict[str, Any]:
    parsed_endpoint = urlparse(config.endpoint)
    metadata: dict[str, Any] = {
        "networkAccess": True,
        "endpointHost": parsed_endpoint.hostname,
        "model": config.model,
        "structuredOutput": config.structured_output,
    }
    response_model = response.get("model")
    if isinstance(response_model, str) and response_model.strip():
        metadata["responseModel"] = response_model.strip()
    usage = response.get("usage")
    if isinstance(usage, Mapping):
        sanitized_usage: dict[str, int | float] = {}
        for key, value in usage.items():
            if not isinstance(key, str):
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if math.isfinite(float(value)) and value >= 0:
                sanitized_usage[key] = value
        if sanitized_usage:
            metadata["usage"] = sanitized_usage
    return metadata


def _https_endpoint(value: str) -> str:
    endpoint = _text(value, "endpoint")
    parsed = urlparse(endpoint)
    if parsed.scheme.lower() != "https":
        raise ValueError("live LLM endpoint must use HTTPS")
    if parsed.hostname is None:
        raise ValueError("live LLM endpoint must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("live LLM endpoint must not embed credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("live LLM endpoint must not contain query or fragment components")
    return endpoint


def _environment_name(value: str) -> str:
    name = _text(value, "api_key_env")
    if _ENV_NAME.fullmatch(name) is None:
        raise ValueError("api_key_env must be a valid environment variable name")
    return name


def _required_environment_value(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise LiveLLMProviderError(f"required environment variable {name!r} is not configured")
    return value.strip()


def _positive_finite(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError(f"{label} must be positive and finite")
    return normalized


def _text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


assert isinstance(
    OpenAICompatibleLLMProvider(
        OpenAICompatibleProviderConfig(
            endpoint="https://example.invalid/v1/chat/completions",
            model="contract-check",
        ),
        transport=UrllibJSONTransport(),
    ),
    LLMHypothesisProvider,
)
