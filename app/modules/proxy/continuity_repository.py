from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Insert

from app.core.types import JsonValue
from app.db.models import WebsocketContinuityStateRecord
from app.db.sqlite_retry import retry_sqlite_write

logger = logging.getLogger(__name__)


class WebsocketContinuityStatesRepository:
    """Shared store for per-session WebSocket continuity snapshots.

    Rows are opaque JSON blobs keyed by ``(session_key, api_key_id)`` so
    a downstream reconnect landing on a different worker can rehydrate the
    continuity state its previous worker recorded.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, session_key: str, api_key_id: str) -> dict[str, JsonValue] | None:
        statement = select(WebsocketContinuityStateRecord.state).where(
            WebsocketContinuityStateRecord.session_key == session_key,
            WebsocketContinuityStateRecord.api_key_id == api_key_id,
        )
        result = await self._session.execute(statement)
        raw_state = result.scalar_one_or_none()
        if raw_state is None:
            return None
        try:
            payload = json.loads(raw_state)
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    async def upsert(self, session_key: str, api_key_id: str, state: dict[str, JsonValue]) -> None:
        serialized = json.dumps(state, ensure_ascii=True, separators=(",", ":"))

        async def _upsert_once() -> None:
            statement = self._build_upsert_statement(session_key, api_key_id, serialized)
            await self._session.execute(statement)
            await self._session.commit()

        await retry_sqlite_write(
            self._session,
            _upsert_once,
            operation_name="websocket_continuity_state_upsert",
            logger=logger,
        )

    async def purge_before(self, cutoff: datetime) -> int:
        async def _purge_once() -> int:
            statement = (
                delete(WebsocketContinuityStateRecord)
                .where(WebsocketContinuityStateRecord.updated_at < cutoff)
                .returning(WebsocketContinuityStateRecord.session_key)
            )
            result = await self._session.execute(statement)
            deleted = len(result.scalars().all())
            await self._session.commit()
            return deleted

        return await retry_sqlite_write(
            self._session,
            _purge_once,
            operation_name="websocket_continuity_state_purge_before",
            logger=logger,
        )

    def _build_upsert_statement(self, session_key: str, api_key_id: str, serialized: str) -> Insert:
        dialect = self._session.get_bind().dialect.name
        if dialect == "postgresql":
            insert_fn = pg_insert
        elif dialect == "sqlite":
            insert_fn = sqlite_insert
        else:
            raise RuntimeError(f"WebsocketContinuityState upsert unsupported for dialect={dialect!r}")
        statement = insert_fn(WebsocketContinuityStateRecord).values(
            session_key=session_key,
            api_key_id=api_key_id,
            state=serialized,
        )
        return statement.on_conflict_do_update(
            index_elements=[
                WebsocketContinuityStateRecord.session_key,
                WebsocketContinuityStateRecord.api_key_id,
            ],
            set_={
                "state": serialized,
                "updated_at": func.now(),
            },
        )
