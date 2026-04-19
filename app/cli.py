from __future__ import annotations

import argparse
import os

import uvicorn

from app.core.runtime_logging import build_log_config


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _env_str(*names: str, default: str) -> str:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        value = raw.strip()
        if value:
            return value
    return default


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the codex-lb API server.")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "2455")))
    parser.add_argument("--ssl-certfile", default=os.getenv("SSL_CERTFILE"))
    parser.add_argument("--ssl-keyfile", default=os.getenv("SSL_KEYFILE"))
    parser.add_argument(
        "--workers",
        type=_positive_int,
        default=_positive_int(_env_str("CODEX_LB_UVICORN_WORKERS", "UVICORN_WORKERS", default="1")),
    )
    parser.add_argument(
        "--loop",
        choices=("auto", "asyncio", "uvloop"),
        default=_env_str("CODEX_LB_UVICORN_LOOP", "UVICORN_LOOP", default="auto"),
    )
    parser.add_argument(
        "--http",
        choices=("auto", "h11", "httptools"),
        default=_env_str("CODEX_LB_UVICORN_HTTP", "UVICORN_HTTP", default="auto"),
    )

    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if bool(args.ssl_certfile) ^ bool(args.ssl_keyfile):
        raise SystemExit("Both --ssl-certfile and --ssl-keyfile must be provided together.")

    os.environ["PORT"] = str(args.port)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        workers=args.workers,
        loop=args.loop,
        http=args.http,
        ssl_certfile=args.ssl_certfile,
        ssl_keyfile=args.ssl_keyfile,
        log_config=build_log_config(),
    )


if __name__ == "__main__":
    main()
