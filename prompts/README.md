# Versioned Agent Prompts

Owner: Track C (`@sunny1ce`).

When LLM prompts become part of the implementation, store versioned prompt templates here instead of embedding long mutable prompts throughout application code.

Prompt rules:
- consume structured evidence rather than unbounded raw binary dumps;
- request structured protocol hypotheses, not final unquestioned facts;
- preserve ACCEPTED / REJECTED / UNCERTAIN semantics;
- include evidence IDs so outputs are traceable;
- record prompt version/model version in experiments;
- do not place API keys, private traffic or sensitive restored data here.
