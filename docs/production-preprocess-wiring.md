# Production preprocessing wiring

The production Track D backend now consumes the container-aware preprocessing layer introduced by PR #115.

Runtime path:

```text
Sidecar analyze
  -> TrackDBaselineBackend
  -> load .dat/.bin/PCAP/PCAPNG bytes
  -> io.preprocess.preprocess
     -> content-based PCAP/PCAPNG detection
     -> transport payload extraction
     -> known-protocol classification (currently DTLS)
  -> exact transport-payload packet boundaries when available
  -> known protocol: gate generic unknown-protocol field inference and semantic promotion
  -> unknown raw protocol: continue the existing boundary/family/field inference path
```

Fail-closed behavior:

- a PCAP/PCAPNG parsing failure never falls back to blind scanning the capture container;
- `optionalDependencyPolicy=degrade` returns a partial result with the preprocessing error recorded;
- `optionalDependencyPolicy=fail` fails the analysis request;
- a structurally identified DTLS flow is not presented as recoverable plaintext and is not sent through generic unknown-protocol field inference.

The backend also updates the in-memory registered `InputMetadata.kind` to the detected PCAP/PCAPNG container during analysis, so subsequent inspection reflects the content-derived format even when a capture uses a `.dat` suffix.
