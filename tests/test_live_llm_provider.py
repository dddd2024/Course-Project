from __future__ import annotations

import json
import urllib.request
from typing import Any

import pytest

from course_project.llm import (
    LLMHypothesisProvider,
    LLMHypothesisRequest,
    LiveLLMProviderError,
    LiveLLMResponseError,
    LiveLLMTransportError,
    OpenAICompatibleLLMProvider,
    OpenAICompatibleProviderConfig,
    UrllibJSONTransport,
    build_chat_completion_payload,
    parse_chat_completion_response,
)


class FakeTransport:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str] | Any,
        payload: dict[str, Any] | Any,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


class DummyHTTPResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> DummyHTTPResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self._body[:limit]


def _config(**overrides: Any) -> OpenAICompatibleProviderConfig:
    values: dict[str, Any] = {
        "endpoint": "https://llm.example.test/v1/chat/completions",
        "model": "example-model",
        "api_key_env": "TEST_LLM_API_KEY",
        "timeout_seconds": 12,
        "structured_output": "json_object",
    }
    values.update(overrides)
    return OpenAICompatibleProviderConfig(**values)


def _request() -> LLMHypothesisRequest:
    return LLMHypothesisRequest(
        request_id="req-1",
        input_id="input-1",
        allowed_evidence_ids=("ev-length", "ev-seq"),
        context={
            "regions": [{"offset": 0, "bytesHex": "0010aabb"}],
            "notes": "candidate semantic regions only",
        },
    )


def _provider_response(
    hypotheses: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if hypotheses is None:
        hypotheses = [
            {
                "offset": 0,
                "size": 2,
                "semanticType": "length",
                "interpretation": "big-endian payload length",
                "parameters": {"endian": "big", "target": "payload"},
                "modelConfidence": 0.82,
                "supportingEvidenceIds": ["ev-length"],
            },
            {
                "offset": 0,
                "size": 2,
                "semanticType": "enum",
                "interpretation": "message type code",
                "parameters": {"endian": "big"},
                "modelConfidence": 0.44,
                "supportingEvidenceIds": ["ev-seq"],
            },
        ]
    return {
        "id": "chatcmpl-test",
        "model": "provider-resolved-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"hypotheses": hypotheses}),
                },
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 80,
            "total_tokens": 200,
            "ignored": "not numeric",
        },
    }


def test_live_provider_satisfies_existing_provider_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_LLM_API_KEY", "secret-test-value")
    provider = OpenAICompatibleLLMProvider(_config(), transport=FakeTransport(_provider_response()))

    assert isinstance(provider, LLMHypothesisProvider)
    assert provider.mode == "live"


def test_live_provider_materializes_project_native_hypotheses_without_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "secret-test-value"
    monkeypatch.setenv("TEST_LLM_API_KEY", secret)
    transport = FakeTransport(_provider_response())
    provider = OpenAICompatibleLLMProvider(
        _config(),
        transport=transport,
        provider_name="compatible-test",
    )

    result = provider.propose(_request())

    assert result.provider == "compatible-test"
    assert result.mode == "live"
    assert len(result.hypotheses) == 2
    first, second = result.hypotheses
    assert first.model_confidence == pytest.approx(0.82)
    assert second.model_confidence == pytest.approx(0.44)
    assert first.competing_hypothesis_ids == (second.hypothesis_id,)
    assert second.competing_hypothesis_ids == (first.hypothesis_id,)
    assert not hasattr(first, "verification_score")
    assert result.metadata["networkAccess"] is True
    assert result.metadata["endpointHost"] == "llm.example.test"
    assert result.metadata["model"] == "example-model"
    assert result.metadata["responseModel"] == "provider-resolved-model"
    assert result.metadata["usage"] == {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
    }
    assert secret not in repr(result.metadata)
    assert "Authorization" not in result.metadata

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["headers"]["Authorization"] == f"Bearer {secret}"
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["timeout_seconds"] == 12.0


def test_payload_is_deterministic_and_contains_only_provider_neutral_request_context() -> None:
    request = _request()
    first = build_chat_completion_payload(_config(), request)
    second = build_chat_completion_payload(_config(), request)

    assert first == second
    assert first["model"] == "example-model"
    assert first["stream"] is False
    assert first["response_format"] == {"type": "json_object"}
    assert [message["role"] for message in first["messages"]] == ["system", "user"]
    user_payload = json.loads(first["messages"][1]["content"])
    assert user_payload == {
        "requestId": "req-1",
        "inputId": "input-1",
        "allowedEvidenceIds": ["ev-length", "ev-seq"],
        "context": request.context,
    }


def test_prompt_only_mode_omits_provider_specific_response_format() -> None:
    payload = build_chat_completion_payload(
        _config(structured_output="prompt_only"),
        _request(),
    )

    assert "response_format" not in payload


def test_missing_secret_fails_before_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_LLM_API_KEY", raising=False)
    transport = FakeTransport(_provider_response())
    provider = OpenAICompatibleLLMProvider(_config(), transport=transport)

    with pytest.raises(LiveLLMProviderError, match="TEST_LLM_API_KEY"):
        provider.propose(_request())

    assert transport.calls == []


def test_request_validation_fails_before_secret_or_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_LLM_API_KEY", "secret-test-value")
    transport = FakeTransport(_provider_response())
    provider = OpenAICompatibleLLMProvider(_config(), transport=transport)
    invalid = LLMHypothesisRequest(
        request_id="req-invalid",
        input_id="input-invalid",
        allowed_evidence_ids=("duplicate", "duplicate"),
    )

    with pytest.raises(ValueError, match="duplicates"):
        provider.propose(invalid)

    assert transport.calls == []


def test_config_requires_https_and_never_embeds_secret() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        _config(endpoint="http://llm.example.test/v1/chat/completions")
    with pytest.raises(ValueError, match="credentials"):
        _config(endpoint="https://user:pass@llm.example.test/v1/chat/completions")
    with pytest.raises(ValueError, match="query or fragment"):
        _config(endpoint="https://llm.example.test/v1/chat/completions?debug=1")
    with pytest.raises(ValueError, match="environment variable name"):
        _config(api_key_env="not-valid-env-name")
    with pytest.raises(ValueError, match="positive and finite"):
        _config(timeout_seconds=0)


def test_environment_config_reads_non_secret_values_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALT_ENDPOINT", "https://llm.example.test/v1/chat/completions")
    monkeypatch.setenv("ALT_MODEL", "env-model")
    monkeypatch.setenv("ALT_API_KEY_ENV", "ACTUAL_SECRET_ENV")
    monkeypatch.setenv("ALT_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("ALT_STRUCTURED_OUTPUT", "prompt_only")
    monkeypatch.setenv("ACTUAL_SECRET_ENV", "super-secret-value")

    config = OpenAICompatibleProviderConfig.from_environment(prefix="ALT_")

    assert config.endpoint == "https://llm.example.test/v1/chat/completions"
    assert config.model == "env-model"
    assert config.api_key_env == "ACTUAL_SECRET_ENV"
    assert config.timeout_seconds == 7.5
    assert config.structured_output == "prompt_only"
    assert "super-secret-value" not in repr(config)


def test_response_parser_rejects_provider_error_and_refusal() -> None:
    with pytest.raises(LiveLLMResponseError, match="error envelope"):
        parse_chat_completion_response({"error": {"message": "bad request"}})

    refusal = _provider_response([])
    refusal["choices"][0]["message"]["refusal"] = "cannot comply"
    with pytest.raises(LiveLLMResponseError, match="refused"):
        parse_chat_completion_response(refusal)


def test_response_parser_rejects_malformed_envelopes() -> None:
    malformed = [
        ({}, "choices"),
        ({"choices": []}, "choices"),
        ({"choices": ["bad"]}, "choice"),
        ({"choices": [{}]}, "message"),
        ({"choices": [{"message": {"content": None}}]}, "content"),
        ({"choices": [{"message": {"content": "not-json"}}]}, "valid JSON"),
        (
            {"choices": [{"message": {"content": json.dumps({"other": []})}}]},
            "exactly",
        ),
    ]

    for response, message in malformed:
        with pytest.raises(LiveLLMResponseError, match=message):
            parse_chat_completion_response(response)


def test_response_parser_rejects_schema_drift() -> None:
    proposal = _provider_response()["choices"][0]["message"]["content"]
    document = json.loads(proposal)
    document["hypotheses"][0]["extra"] = "unexpected"
    response = _provider_response([])
    response["choices"][0]["message"]["content"] = json.dumps(document)

    with pytest.raises(LiveLLMResponseError, match="required schema"):
        parse_chat_completion_response(response)


def test_shared_materialization_rejects_unknown_evidence_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_LLM_API_KEY", "secret-test-value")
    bad = _provider_response(
        [
            {
                "offset": 0,
                "size": 1,
                "semanticType": "enum",
                "interpretation": "message type",
                "parameters": {},
                "modelConfidence": 0.5,
                "supportingEvidenceIds": ["invented-evidence"],
            }
        ]
    )
    provider = OpenAICompatibleLLMProvider(_config(), transport=FakeTransport(bad))

    with pytest.raises(ValueError, match="outside the request"):
        provider.propose(_request())


def test_shared_materialization_rejects_invalid_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_LLM_API_KEY", "secret-test-value")
    bad = _provider_response(
        [
            {
                "offset": 0,
                "size": 1,
                "semanticType": "enum",
                "interpretation": "message type",
                "parameters": {},
                "modelConfidence": 1.5,
                "supportingEvidenceIds": ["ev-length"],
            }
        ]
    )
    provider = OpenAICompatibleLLMProvider(_config(), transport=FakeTransport(bad))

    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        provider.propose(_request())


def test_stdlib_transport_uses_injected_urlopen_without_real_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    response_body = json.dumps({"choices": []}).encode()

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> DummyHTTPResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return DummyHTTPResponse(response_body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    transport = UrllibJSONTransport()
    result = transport.post_json(
        url="https://llm.example.test/v1/chat/completions",
        headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
        payload={"model": "example-model", "messages": []},
        timeout_seconds=3,
    )

    request = captured["request"]
    assert isinstance(request, urllib.request.Request)
    assert request.get_method() == "POST"
    assert request.full_url == "https://llm.example.test/v1/chat/completions"
    assert captured["timeout"] == 3.0
    assert json.loads(request.data.decode()) == {"messages": [], "model": "example-model"}
    assert result == {"choices": []}


def test_stdlib_transport_rejects_non_json_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(
        _request: urllib.request.Request,
        timeout: float,
    ) -> DummyHTTPResponse:
        assert timeout == 3.0
        return DummyHTTPResponse(b"not-json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(LiveLLMTransportError, match="valid JSON"):
        UrllibJSONTransport().post_json(
            url="https://llm.example.test/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            payload={"model": "example-model"},
            timeout_seconds=3,
        )
