"""Transient account health is scoped to the model the account was serving."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.models import Account
from app.modules.proxy.load_balancer import _MAX_MODEL_HEALTH_ENTRIES, LoadBalancer
from tests.unit.test_load_balancer_concurrency import (
    _make_account,
    _repo_factory,
    _StubAccountsRepository,
    _StubUsageRepository,
    _usage_row,
    _usage_row_with_percent,
)

pytestmark = pytest.mark.unit

THROTTLED_MODEL = "gpt-6.1-terra"
OTHER_MODEL = "gpt-6.2-sol"


def _balancer(*accounts: Account, primary_used_percent: dict[str, float] | None = None) -> LoadBalancer:
    now_epoch = int(datetime.now(tz=timezone.utc).timestamp())
    used = primary_used_percent or {}
    usage_repo = _StubUsageRepository(
        primary={
            account.id: _usage_row_with_percent(
                index * 2 + 1,
                account.id,
                used_percent=used.get(account.id, 10.0),
                reset_at=now_epoch + 300,
            )
            for index, account in enumerate(accounts)
        },
        secondary={
            account.id: _usage_row(index * 2 + 2, account.id, window="secondary", reset_at=now_epoch + 3600)
            for index, account in enumerate(accounts)
        },
    )
    return LoadBalancer(lambda: _repo_factory(_StubAccountsRepository(list(accounts)), usage_repo))


async def _selected_id(balancer: LoadBalancer, model: str) -> str | None:
    selection = await balancer.select_account(routing_strategy="usage_weighted", model=model)
    return None if selection.account is None else selection.account.id


@pytest.mark.asyncio
async def test_three_errors_for_one_model_keep_the_only_account_selectable_for_another() -> None:
    account = _make_account("acc-model-scope")
    balancer = _balancer(account)

    await balancer.record_errors(account, 3, model=THROTTLED_MODEL)

    throttled = await balancer.select_account(routing_strategy="usage_weighted", model=THROTTLED_MODEL)
    assert throttled.account is None
    assert throttled.error_message is not None
    assert "No available accounts" in throttled.error_message
    assert await _selected_id(balancer, OTHER_MODEL) == account.id
    # The slug is compared the way bridge sessions compare models.
    assert await _selected_id(balancer, f" {THROTTLED_MODEL.upper()} ") is None
    assert balancer._runtime[account.id].error_count == 0


@pytest.mark.asyncio
async def test_errors_without_a_model_back_the_account_off_for_every_model() -> None:
    account = _make_account("acc-account-wide")
    balancer = _balancer(account)

    await balancer.record_errors(account, 3)

    assert await _selected_id(balancer, THROTTLED_MODEL) is None
    assert await _selected_id(balancer, OTHER_MODEL) is None


@pytest.mark.asyncio
async def test_success_clears_only_the_model_that_succeeded() -> None:
    account = _make_account("acc-success-scope")
    balancer = _balancer(account)
    await balancer.record_errors(account, 3, model=THROTTLED_MODEL)

    await balancer.record_success(account, model=OTHER_MODEL)
    await balancer.record_success(account)
    assert await _selected_id(balancer, THROTTLED_MODEL) is None

    await balancer.record_success(account, model=THROTTLED_MODEL)
    assert await _selected_id(balancer, THROTTLED_MODEL) == account.id


@pytest.mark.asyncio
async def test_elapsed_model_backoff_returns_with_a_clean_count() -> None:
    account = _make_account("acc-backoff-expiry")
    balancer = _balancer(account)
    await balancer.record_errors(account, 3, model=THROTTLED_MODEL)
    health = balancer._runtime[account.id].model_health[THROTTLED_MODEL]
    assert health.last_error_at is not None
    health.last_error_at -= 31.0

    assert await _selected_id(balancer, THROTTLED_MODEL) == account.id
    assert THROTTLED_MODEL not in balancer._runtime[account.id].model_health

    # One further error starts from zero instead of re-entering the backoff.
    await balancer.record_error(account, model=THROTTLED_MODEL)
    assert await _selected_id(balancer, THROTTLED_MODEL) == account.id


@pytest.mark.asyncio
async def test_temporary_cooldown_for_one_model_leaves_another_model_selectable() -> None:
    account = _make_account("acc-cooldown-scope")
    balancer = _balancer(account)

    await balancer.mark_temporary_cooldown(account, 30.0, model=THROTTLED_MODEL)

    cooling = await balancer.select_account(routing_strategy="usage_weighted", model=THROTTLED_MODEL)
    assert cooling.account is None
    assert cooling.error_message is not None
    assert "Try again in" in cooling.error_message
    assert await _selected_id(balancer, OTHER_MODEL) == account.id
    assert balancer._runtime[account.id].cooldown_until is None

    health = balancer._runtime[account.id].model_health[THROTTLED_MODEL]
    assert health.cooldown_until is not None
    health.cooldown_until -= 31.0
    assert await _selected_id(balancer, THROTTLED_MODEL) == account.id
    assert THROTTLED_MODEL not in balancer._runtime[account.id].model_health


@pytest.mark.asyncio
async def test_model_errors_drain_the_account_for_that_model_only() -> None:
    preferred = _make_account("acc-drain-preferred")
    fallback = _make_account("acc-drain-fallback")
    balancer = _balancer(preferred, fallback, primary_used_percent={preferred.id: 5.0, fallback.id: 60.0})
    assert await _selected_id(balancer, THROTTLED_MODEL) == preferred.id

    await balancer.record_errors(preferred, 2, model=THROTTLED_MODEL)

    assert await _selected_id(balancer, THROTTLED_MODEL) == fallback.id
    assert await _selected_id(balancer, OTHER_MODEL) == preferred.id
    assert balancer._runtime[preferred.id].health_tier == 0


@pytest.mark.asyncio
async def test_model_health_entries_per_account_are_bounded() -> None:
    account = _make_account("acc-model-bound")
    balancer = _balancer(account)

    for index in range(_MAX_MODEL_HEALTH_ENTRIES + 1):
        await balancer.record_error(account, model=f"model-{index}")

    model_health = balancer._runtime[account.id].model_health
    assert len(model_health) == _MAX_MODEL_HEALTH_ENTRIES
    assert "model-0" not in model_health
    assert f"model-{_MAX_MODEL_HEALTH_ENTRIES}" in model_health
