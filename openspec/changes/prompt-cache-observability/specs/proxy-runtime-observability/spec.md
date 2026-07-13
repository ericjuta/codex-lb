## ADDED Requirements

### Requirement: Streaming time-to-first-byte is attributable per transport

The system MUST record, for each proxied streaming response, Prometheus histogram observations for (a) the elapsed time from upstream stream initiation to the first upstream SSE event and (b) the elapsed time from upstream stream initiation to the first text-delta event, labeled by upstream transport and model, so operators can attribute time-to-first-token latency between upstream acceptance and generation start.

#### Scenario: First upstream event latency is observed

- **WHEN** a proxied streaming request receives its first SSE event from upstream
- **THEN** the `codex_lb_stream_first_event_seconds` histogram records the elapsed seconds since the stream attempt started with `transport` and `model` labels

#### Scenario: First text-delta latency is observed

- **WHEN** a proxied streaming request receives its first text-delta event from upstream
- **THEN** the `codex_lb_stream_first_token_seconds` histogram records the elapsed seconds since the stream attempt started with `transport` and `model` labels

#### Scenario: Streams that fail before any event record nothing

- **WHEN** a stream attempt errors before the first upstream event arrives
- **THEN** neither histogram records an observation for that attempt

### Requirement: Prompt-cache ratio canary alerts on collapse

The system MUST run a periodic, leader-elected background sampler that computes the rolling prompt-cache hit ratio (cached input tokens divided by input tokens) per model from successful `normal` request logs over a configurable window, publishes the ratio as a Prometheus gauge labeled by model, and emits a WARNING log for any model whose windowed input-token volume meets a configurable minimum while its ratio is below a configurable threshold. The sampler MUST be enabled by default and MUST be disableable via settings.

#### Scenario: Healthy model publishes gauge without warning

- **WHEN** the canary samples a model whose windowed cache ratio is at or above the threshold
- **THEN** the `codex_lb_prompt_cache_ratio` gauge for that model is updated
- **AND** no WARNING log is emitted for that model

#### Scenario: Collapsed cache ratio emits a warning

- **WHEN** the canary samples a model whose windowed input tokens meet the minimum volume and whose cache ratio is below the threshold
- **THEN** a WARNING log is emitted naming the model, ratio, input-token volume, and threshold

#### Scenario: Low-volume model does not warn

- **WHEN** the canary samples a model whose windowed input tokens are below the minimum volume
- **THEN** no WARNING log is emitted for that model regardless of its ratio

#### Scenario: Canary disabled via settings

- **WHEN** the canary is disabled via settings
- **THEN** the sampler does not run and no gauge updates or warnings occur
