# Live LLM Provider

The project has three provider modes:

- `mock` — deterministic, network-free CI/test responses;
- `offline` — explicit no-op with no network access;
- `live` — opt-in OpenAI-compatible HTTPS provider.

V1, CI, packaging, and the deterministic analysis path do **not** require live LLM access.

## Why the core does not depend on an LLM SDK

The official OpenAI Python SDK and LiteLLM are both valid open-source integration options. The OpenAI SDK provides the full OpenAI API surface and structured outputs; LiteLLM is appropriate when the project needs a unified gateway across many providers. The repository currently has no runtime dependencies, however, and already owns a provider-neutral `LLMHypothesisProvider` plus strict project-native materialization.

For that reason the blocking runtime contains only a small Python-standard-library adapter for an OpenAI-compatible `chat/completions` endpoint. This preserves the existing Windows packaging surface. A future LiteLLM gateway or provider SDK may sit behind the same boundary without changing `ProtocolHypothesis`, verification, fusion, or experiment contracts.

## Configuration

Create `OpenAICompatibleProviderConfig` directly or load non-secret configuration with `OpenAICompatibleProviderConfig.from_environment()`.

Default environment variables:

| Variable | Meaning |
| --- | --- |
| `COURSE_PROJECT_LLM_ENDPOINT` | Exact HTTPS chat-completions endpoint, for example a provider's `/v1/chat/completions` URL |
| `COURSE_PROJECT_LLM_MODEL` | Provider model identifier |
| `COURSE_PROJECT_LLM_API_KEY_ENV` | Optional name of the environment variable that holds the secret; defaults to `COURSE_PROJECT_LLM_API_KEY` |
| `COURSE_PROJECT_LLM_API_KEY` | Default secret environment variable; read only when a live request executes |
| `COURSE_PROJECT_LLM_TIMEOUT_SECONDS` | Positive finite request timeout, default `30` |
| `COURSE_PROJECT_LLM_STRUCTURED_OUTPUT` | `json_object` (default) or `prompt_only` |

The API key value is not stored on the config object, returned in provider metadata, or written to experiment records. It is resolved from the configured secret environment variable at call time.

## Security and fail-closed behavior

The live adapter:

- requires HTTPS;
- rejects endpoints with embedded username/password, query strings, or fragments;
- validates the project-native request before any network access;
- sends credentials only as a Bearer `Authorization` header;
- accepts only a JSON object response;
- accepts only an OpenAI-compatible response with a non-empty `choices` list and message content;
- fails closed on provider error envelopes, refusals, malformed or non-JSON content;
- requires the message body to contain exactly `{ "hypotheses": [...] }`;
- requires every proposal to have the exact structured fields expected by `HypothesisProposal`;
- routes every proposal back through shared `materialize_hypotheses()` validation, including evidence-reference and confidence/range checks;
- never converts `modelConfidence` into executable verification or `ACCEPTED` status;
- caps provider response size before decoding.

Provider metadata is intentionally sanitized to endpoint hostname, configured/resolved model information, structured-output mode, network-access flag, and numeric usage counters. Credentials and raw request headers are excluded.

## Provider compatibility

`json_object` adds the OpenAI-compatible `response_format={"type":"json_object"}` request field. Providers that expose a compatible endpoint but do not support that field can use `prompt_only`; the same strict local JSON/schema validation still applies.

The current adapter intentionally does not implement provider-specific retry, rate-limit, billing, model discovery, or multi-provider routing. If those become requirements, prefer an external SDK/gateway such as LiteLLM behind this boundary rather than duplicating them in project code.

## Testing

CI never calls a real provider. Tests inject a deterministic JSON transport and separately monkeypatch the stdlib `urlopen` call to validate the production HTTPS transport without external network access or credentials.
