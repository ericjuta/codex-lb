"""Regression coverage for Helm PostgreSQL connection budgets."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from app.db.session import _POSTGRES_POOLED_ENGINES_PER_WORKER

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHART_DIR = _REPO_ROOT / "deploy" / "helm" / "codex-lb"
_CHART_README = _CHART_DIR / "README.md"
_POSTGRES_DEFAULT_MAX_CONNECTIONS = 100
_POSTGRES_DEFAULT_SUPERUSER_RESERVED_CONNECTIONS = 3
_MIGRATOR_PEAK_CONNECTIONS = 2
_REQUIRED_RAW_CONNECTION_RESERVE = 20
_SUPPORTED_WORKERS_PER_REPLICA = 1
_DEPENDENCY_BUILD_COMPLETE = False


def _ensure_chart_dependencies() -> None:
    global _DEPENDENCY_BUILD_COMPLETE
    if _DEPENDENCY_BUILD_COMPLETE:
        return

    if shutil.which("helm") is None:
        pytest.skip("helm is required for chart rendering tests")

    subprocess.run(
        ["helm", "dependency", "build", str(_CHART_DIR)],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    _DEPENDENCY_BUILD_COMPLETE = True


def _helm_template(*args: str) -> str:
    _ensure_chart_dependencies()
    completed = subprocess.run(
        ["helm", "template", "codex-lb", str(_CHART_DIR), *args],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _helm_documents(rendered: str) -> list[dict]:
    return [document for document in yaml.safe_load_all(rendered) if document]


def _prod_overlay_args(*args: str) -> tuple[str, ...]:
    return (
        "-f",
        str(_CHART_DIR / "values-prod.yaml"),
        "--set",
        "externalSecrets.secretStoreRef.name=test-store",
        *args,
    )


def _connection_budget(values: dict) -> int:
    config = values["config"]
    autoscaling = values["autoscaling"]
    return (
        (config["databasePoolSize"] + config["databaseMaxOverflow"])
        * _POSTGRES_POOLED_ENGINES_PER_WORKER
        * _SUPPORTED_WORKERS_PER_REPLICA
        * autoscaling["maxReplicas"]
    )


def test_helm_pool_budgets_count_both_postgres_engines() -> None:
    defaults = yaml.safe_load((_CHART_DIR / "values.yaml").read_text())
    production = yaml.safe_load((_CHART_DIR / "values-prod.yaml").read_text())
    merged_production = {
        **defaults,
        **production,
        "config": {**defaults["config"], **production["config"]},
        "autoscaling": {**defaults["autoscaling"], **production["autoscaling"]},
    }

    for values in (defaults, merged_production):
        budget = _connection_budget(values)
        reserve = _POSTGRES_DEFAULT_MAX_CONNECTIONS - budget

        assert budget == 80
        assert reserve >= _REQUIRED_RAW_CONNECTION_RESERVE
        assert reserve >= _POSTGRES_DEFAULT_SUPERUSER_RESERVED_CONNECTIONS + _MIGRATOR_PEAK_CONNECTIONS


def test_helm_pool_budget_values_flow_to_runtime_and_hpa_templates() -> None:
    configmap = (_CHART_DIR / "templates" / "configmap.yaml").read_text()
    deployment = (_CHART_DIR / "templates" / "deployment.yaml").read_text()
    hpa = (_CHART_DIR / "templates" / "hpa.yaml").read_text()

    assert "CODEX_LB_DATABASE_POOL_SIZE: {{ .Values.config.databasePoolSize" in configmap
    assert "CODEX_LB_DATABASE_MAX_OVERFLOW: {{ .Values.config.databaseMaxOverflow" in configmap
    assert re.search(r"command:\s+- python\s+- -m\s+- app\.cli", deployment)
    assert re.search(r'- --workers\s+- "1"', deployment)
    assert "maxReplicas: {{ .Values.autoscaling.maxReplicas }}" in hpa


def test_pool_budget_documentation_names_both_engines_one_worker_and_reserve() -> None:
    readme = _CHART_README.read_text()
    deployment_context = (_REPO_ROOT / "openspec" / "specs" / "deployment-installation" / "context.md").read_text()
    database_context = (_REPO_ROOT / "openspec" / "specs" / "database-backends" / "context.md").read_text()

    assert "× 2 pools × 1 worker × replicas" in readme
    assert "WEB_CONCURRENCY" in readme
    assert "reserving 20" in readme
    assert "../../../openspec/specs/database-backends/" in readme
    assert "../../../openspec/specs/deployment-installation/" in readme
    assert "(pool_size + max_overflow) x 2 x replicas" in deployment_context
    assert "one worker with two independently pooled PostgreSQL engine roles" in database_context


def test_default_profile_renders_budgeted_pool_values_and_hpa_ceiling() -> None:
    configmap_rendered = _helm_template("--show-only", "templates/configmap.yaml")
    hpa_rendered = _helm_template(
        "--set",
        "autoscaling.enabled=true",
        "--show-only",
        "templates/hpa.yaml",
    )
    (configmap,) = _helm_documents(configmap_rendered)
    (hpa,) = _helm_documents(hpa_rendered)

    assert configmap["data"]["CODEX_LB_DATABASE_POOL_SIZE"] == "3"
    assert configmap["data"]["CODEX_LB_DATABASE_MAX_OVERFLOW"] == "1"
    assert hpa["spec"]["maxReplicas"] == 10


def test_prod_overlay_renders_budgeted_pool_values_and_hpa_ceiling() -> None:
    configmap_rendered = _helm_template(
        *_prod_overlay_args("--show-only", "templates/configmap.yaml"),
    )
    deployment_rendered = _helm_template(
        *_prod_overlay_args("--show-only", "templates/deployment.yaml"),
    )
    hpa_rendered = _helm_template(
        *_prod_overlay_args("--show-only", "templates/hpa.yaml"),
    )
    (configmap,) = _helm_documents(configmap_rendered)
    (deployment,) = _helm_documents(deployment_rendered)
    (hpa,) = _helm_documents(hpa_rendered)
    (application_container,) = (
        container
        for container in deployment["spec"]["template"]["spec"]["containers"]
        if container["name"] == "codex-lb"
    )

    assert configmap["data"]["CODEX_LB_DATABASE_POOL_SIZE"] == "1"
    assert configmap["data"]["CODEX_LB_DATABASE_MAX_OVERFLOW"] == "1"
    assert application_container["command"] == [
        "python",
        "-m",
        "app.cli",
        "--host",
        "0.0.0.0",
        "--port",
        "2455",
        "--workers",
        "1",
    ]
    assert hpa["spec"]["maxReplicas"] == 20
