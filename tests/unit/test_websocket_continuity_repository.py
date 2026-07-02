from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.utils.time import utcnow
from app.db.models import WebsocketContinuityStateRecord
from app.db.session import SessionLocal
from app.modules.proxy.continuity_repository import WebsocketContinuityStatesRepository

pytestmark = pytest.mark.unit


def _snapshot(response_id: str) -> dict[str, object]:
    return {
        "last_completed_input_count": 2,
        "last_completed_response_id": response_id,
        "last_completed_input_prefix_fingerprint": "fingerprint",
        "last_pending_function_call_ids": [],
        "folded_response_id_aliases": {"resp_visible": response_id},
    }


@pytest.mark.asyncio
async def test_upsert_inserts_then_updates_row(db_setup) -> None:
    del db_setup
    async with SessionLocal() as session:
        repo = WebsocketContinuityStatesRepository(session)

        await repo.upsert("sess_upsert", "", _snapshot("resp_first"))
        first = await repo.get("sess_upsert", "")
        assert first is not None
        assert first["last_completed_response_id"] == "resp_first"

        backdated = utcnow() - timedelta(hours=1)
        await session.execute(
            update(WebsocketContinuityStateRecord)
            .where(WebsocketContinuityStateRecord.session_key == "sess_upsert")
            .values(updated_at=backdated)
        )
        await session.commit()

        await repo.upsert("sess_upsert", "", _snapshot("resp_second"))
        second = await repo.get("sess_upsert", "")
        assert second is not None
        assert second["last_completed_response_id"] == "resp_second"
        assert second["folded_response_id_aliases"] == {"resp_visible": "resp_second"}

        row = (
            await session.execute(
                select(WebsocketContinuityStateRecord).where(
                    WebsocketContinuityStateRecord.session_key == "sess_upsert"
                )
            )
        ).scalar_one()
        assert row.updated_at > backdated


@pytest.mark.asyncio
async def test_get_scopes_rows_by_api_key_and_misses_cleanly(db_setup) -> None:
    del db_setup
    async with SessionLocal() as session:
        repo = WebsocketContinuityStatesRepository(session)

        await repo.upsert("sess_scoped", "key_a", _snapshot("resp_key_a"))

        scoped = await repo.get("sess_scoped", "key_a")
        assert scoped is not None
        assert scoped["last_completed_response_id"] == "resp_key_a"
        assert await repo.get("sess_scoped", "") is None
        assert await repo.get("sess_missing", "key_a") is None


@pytest.mark.asyncio
async def test_get_returns_none_for_corrupt_state_payload(db_setup) -> None:
    del db_setup
    async with SessionLocal() as session:
        session.add(
            WebsocketContinuityStateRecord(
                session_key="sess_corrupt",
                api_key_id="",
                state="{not-json",
            )
        )
        session.add(
            WebsocketContinuityStateRecord(
                session_key="sess_non_dict",
                api_key_id="",
                state="[1,2,3]",
            )
        )
        await session.commit()

        repo = WebsocketContinuityStatesRepository(session)
        assert await repo.get("sess_corrupt", "") is None
        assert await repo.get("sess_non_dict", "") is None


@pytest.mark.asyncio
async def test_purge_before_removes_only_stale_rows(db_setup) -> None:
    del db_setup
    async with SessionLocal() as session:
        repo = WebsocketContinuityStatesRepository(session)
        await repo.upsert("sess_stale", "", _snapshot("resp_stale"))
        await repo.upsert("sess_fresh", "", _snapshot("resp_fresh"))
        await session.execute(
            update(WebsocketContinuityStateRecord)
            .where(WebsocketContinuityStateRecord.session_key == "sess_stale")
            .values(updated_at=utcnow() - timedelta(hours=49))
        )
        await session.commit()

        deleted = await repo.purge_before(utcnow() - timedelta(hours=48))

        assert deleted == 1
        assert await repo.get("sess_stale", "") is None
        assert await repo.get("sess_fresh", "") is not None
