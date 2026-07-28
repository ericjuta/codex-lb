## ADDED Requirements

### Requirement: Runtime serving profile is operator-configurable

The application launcher MUST expose worker count, event-loop implementation, and HTTP parser as explicit CLI and environment settings. It MUST validate worker counts as positive integers and MUST reject unsupported loop or parser values before serving traffic.

#### Scenario: Operator selects the optimized runtime stack

- **WHEN** an operator configures `CODEX_LB_UVICORN_WORKERS`, `CODEX_LB_UVICORN_LOOP=uvloop`, and `CODEX_LB_UVICORN_HTTP=httptools`
- **THEN** the launcher passes the requested worker count, loop, and HTTP parser to the serving runtime

#### Scenario: Invalid worker count fails before startup

- **WHEN** the configured Uvicorn worker count is zero, negative, or not an integer
- **THEN** the launcher exits with an operator-facing configuration error
