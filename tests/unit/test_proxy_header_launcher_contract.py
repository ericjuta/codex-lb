from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (_REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_development_compose_disables_server_proxy_projection() -> None:
    compose = yaml.safe_load(_read("docker-compose.yml"))
    command = compose["services"]["server"]["command"]

    assert command[:2] == ["uvicorn", "app.main:app"]
    assert command.count("--no-proxy-headers") == 1


@pytest.mark.parametrize(
    ("relative_path", "contract"),
    [
        ("Dockerfile", 'CMD ["/app/scripts/docker-entrypoint.sh"]'),
        ("scripts/docker-entrypoint.sh", "exec python -m app.cli"),
        ("Dockerfile.distroless", 'CMD ["python", "/app/scripts/distroless-entrypoint.py"]'),
        ("scripts/distroless-entrypoint.py", '[sys.executable, "-m", "app.cli"'),
        ("deploy/helm/codex-lb/templates/deployment.yaml", "            - app.cli\n"),
    ],
)
def test_production_launchers_delegate_to_app_cli(relative_path: str, contract: str) -> None:
    assert contract in _read(relative_path)


def test_production_compose_does_not_override_the_app_cli_launcher() -> None:
    server = yaml.safe_load(_read("docker-compose.prod.yml"))["services"]["server"]

    assert "command" not in server
    assert "entrypoint" not in server
