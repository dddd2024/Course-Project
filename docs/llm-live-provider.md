# Live LLM Provider

The project has three provider modes:

- `mock` — deterministic, network-free CI/test responses;
- `offline` — explicit no-op with no network access;
- `live` — opt-in OpenAI-compatible HTTPS provider.

V1, CI, packaging, and the deterministic analysis path do **not** require live LLM access.

## Why the core does not depend on an LLM SDK

The official OpenAI Python SDK and LiteLLM are both valid open-source integration options. The OpenAI SDK provides the full OpenAI API surface and structured outputs; LiteLLM is appropriate when the project needs a unified gateway across many providers. The repository currently has no runtime dependencies, however, and already owns a provider-neutral `LLMHypothesisProvider` plus strict project-native materialization.

For that reason the blocking runtime contains only a small Python-standard-library adapter for an OpenAI-compatible `chat/completions` endpoint. This preserves the existing Windows packaging surface. A future LiteLLM gateway or provider SDK may sit behind the same boundary without changing `ProtocolHypothesis`, verification, fusion, or experiment contracts.

## Production EvidenceGraph-PRE integration

`llmEnabled=true` makes the production Track C semantic backend invoke the configured `LLMHypothesisProvider`. The provider is resolved lazily: when LLM use is disabled, the backend delegates to the deterministic path without loading LLM configuration, reading an API-key environment variable, or performing network work.

The desktop application keeps its frozen request offline-safe, but the CLI/packaged Sidecar now supports an explicit process-level opt-in through `COURSE_PROJECT_LLM_ENABLED=1`. When that variable is enabled, the Sidecar upgrades the effective semantic configuration to `llmEnabled=true`; when it is absent or false, the existing deterministic behavior is unchanged. Invalid enable values fail closed instead of silently enabling network access.

The integration is deliberately narrower than a general agent or provider gateway:

1. Track D first emits a project-native `FieldCandidate` and candidate evidence.
2. The semantic backend builds a bounded structural summary for that exact candidate region.
3. The provider may propose only `length` or `sequence` hypotheses for the exact candidate offset/size currently supported by executable verification.
4. A scoped provider hypothesis is recorded as `track-c-llm-provider` evidence whose parent is the original candidate evidence and whose `independence_group` is the same field region. Therefore an LLM interpretation of an existing candidate is derived evidence, not an independent vote.
5. Every eligible provider hypothesis runs the same deterministic verifier as a non-LLM hypothesis.
6. A verifier rejection vetoes the hypothesis regardless of `modelConfidence`. Only executable verification followed by provenance-aware fusion and global field selection can produce an accepted finding or exportable verified field.

Provider initialization failures, request failures, unsupported/out-of-region hypotheses, and hypotheses that cannot be translated into a safe executable check remain explicit limitations. The deterministic path continues, but the result is not allowed to fabricate successful LLM execution.

### Structural-context privacy boundary

Whole binary payloads are **not** sent to the provider by default. Each request contains only project-native structural information for one candidate:

- candidate ID, family, offset, size, candidate types, declared endian and a narrow match hint;
- total message length for at most 16 samples;
- at most 8 candidate-field bytes per included sample as hex;
- unsigned big-/little-endian interpretations when the bounded field value fits;
- an explicit statement that whole payload bytes are absent;
- the exact region/type constraints that provider output must obey.

This is a data-minimization boundary, not a claim that provider use is anonymous. A live request still sends these structural summaries to the configured external endpoint, so live LLM use remains opt-in.

## Configuration

Create `OpenAICompatibleProviderConfig` directly or load non-secret configuration with `OpenAICompatibleProviderConfig.from_environment()`.

Default environment variables:

| Variable | Meaning |
| --- | --- |
| `COURSE_PROJECT_LLM_ENABLED` | Desktop/Sidecar live-LLM opt-in. Accepts `1/0`, `true/false`, `yes/no`, or `on/off`; defaults off. |
| `COURSE_PROJECT_LLM_ENDPOINT` | Exact HTTPS chat-completions endpoint, for example a provider's `/v1/chat/completions` URL |
| `COURSE_PROJECT_LLM_MODEL` | Provider model identifier |
| `COURSE_PROJECT_LLM_API_KEY_ENV` | Optional name of the environment variable that holds the secret; defaults to `COURSE_PROJECT_LLM_API_KEY` |
| `COURSE_PROJECT_LLM_API_KEY` | Default secret environment variable; read only when a live request executes |
| `COURSE_PROJECT_LLM_TIMEOUT_SECONDS` | Positive finite request timeout, default `30` |
| `COURSE_PROJECT_LLM_STRUCTURED_OUTPUT` | `json_object` (default) or `prompt_only` |

The API key value is not stored on the provider config object, returned in provider metadata, or written to experiment records. It is resolved from the configured secret environment variable at call time.

For PowerShell development, set the variables in the same shell before starting Tauri:

```powershell
$env:COURSE_PROJECT_LLM_ENABLED="1"
$env:COURSE_PROJECT_LLM_ENDPOINT="https://provider.example/v1/chat/completions"
$env:COURSE_PROJECT_LLM_MODEL="provider-model-id"
$env:COURSE_PROJECT_LLM_API_KEY="replace-with-local-secret"
$env:COURSE_PROJECT_LLM_STRUCTURED_OUTPUT="json_object"
cd apps\desktop
npm run tauri dev
```

The repository `.env.example` is a configuration reference; the application does not silently load secrets from that file. For an installed application launched outside the configuring PowerShell process, provide the variables through the normal user/process environment before launch. Never commit a populated `.env` or API key.

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

The production semantic layer additionally scopes returned hypotheses to the requested field region/type and sanitizes provider metadata again before exposing it in semantic metrics. Only endpoint/model/output-mode/network flags and finite non-negative numeric usage counters are retained; arbitrary provider metadata is not trusted as secret-safe.

## Provider compatibility

`json_object` adds the OpenAI-compatible `response_format={"type":"json_object"}` request field. Providers that expose a compatible endpoint but do not support that field can use `prompt_only`; the same strict local JSON/schema validation still applies.

The current adapter intentionally does not implement provider-specific retry, rate-limit, billing, model discovery, or multi-provider routing. If those become requirements, prefer an external SDK/gateway such as LiteLLM behind this boundary rather than duplicating them in project code.

## Claim boundary

A working live-provider path is **mechanism infrastructure**, not an LLM benchmark result. Synthetic fixtures may demonstrate provider→verification→fusion behavior, but they are not teacher-data accuracy evidence. LLM-only, LLM+verification and full EvidenceGraph-PRE experiment records remain separate research gates, and teacher-data metrics remain unavailable until authoritative evaluation data/ground truth is supplied.

## Testing

CI never calls a real provider. Provider unit tests inject deterministic JSON transports. Production semantic-path tests inject deterministic provider implementations and separately verify that missing live configuration fails closed. The blocking deterministic/desktop path continues to require no external network access or credentials.


### Desktop session configuration

The Tauri desktop UI exposes an OpenAI-compatible model settings drawer. The user supplies a Base URL, model identifier, API key, and structured-output mode for the current application session.

The WebView normalizes a Base URL to the chat-completions endpoint and sends the settings through a typed Tauri command. Rust validates the HTTPS endpoint and holds the secret only in process memory. When it starts the Python Sidecar, it injects the existing `COURSE_PROJECT_LLM_*` environment variables into that child process. The API key is never added to the Sidecar JSON Lines request, analysis config, task result, provider metadata, or logs.

Changing or clearing model settings restarts the Sidecar. Because input handles belong to one Sidecar process, the UI clears the current input and asks the user to select it again. The offline deterministic path remains the default and works without credentials or network access.
