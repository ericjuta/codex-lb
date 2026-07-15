from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import CursorResult, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import TokenEncryptor
from app.core.utils.time import to_utc_naive, utcnow
from app.db.models import OAuthDeviceFlowSlot, OAuthFlowState

_TERMINAL_OAUTH_STATUSES = {"error", "success"}
DEVICE_FLOW_SLOT_KEY = "dashboard"


def epoch_to_naive_utc(value: float | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)


@dataclass(slots=True)
class OAuthFlowRecord:
    flow_id: str
    method: str
    status: str
    state_token: str | None = None
    error_message: str | None = None
    code_verifier: str | None = None
    device_auth_id: str | None = None
    user_code: str | None = None
    interval_seconds: int | None = None
    expires_at: datetime | None = None
    finished_at: datetime | None = None


class OAuthFlowRepository:
    """Request-scoped access to shared OAuth flow coordination state."""

    def __init__(self, session: AsyncSession, encryptor: TokenEncryptor) -> None:
        self._session = session
        self._encryptor = encryptor

    def _to_record(self, row: OAuthFlowState) -> OAuthFlowRecord:
        verifier = None
        if row.code_verifier_encrypted is not None:
            verifier = self._encryptor.decrypt(row.code_verifier_encrypted)
        return OAuthFlowRecord(
            flow_id=row.flow_id,
            method=row.method,
            status=row.status,
            state_token=row.state_token,
            error_message=row.error_message,
            code_verifier=verifier,
            device_auth_id=row.device_auth_id,
            user_code=row.user_code,
            interval_seconds=row.interval_seconds,
            expires_at=row.expires_at,
            finished_at=row.finished_at,
        )

    @staticmethod
    def _is_expired_pending(row: OAuthFlowState, now: datetime) -> bool:
        return row.status == "pending" and row.expires_at is not None and to_utc_naive(row.expires_at) <= now

    async def create(self, record: OAuthFlowRecord) -> None:
        encrypted = None
        if record.code_verifier is not None:
            encrypted = self._encryptor.encrypt(record.code_verifier)
        self._session.add(
            OAuthFlowState(
                flow_id=record.flow_id,
                state_token=record.state_token,
                method=record.method,
                status=record.status,
                error_message=record.error_message,
                code_verifier_encrypted=encrypted,
                device_auth_id=record.device_auth_id,
                user_code=record.user_code,
                interval_seconds=record.interval_seconds,
                expires_at=record.expires_at,
                created_at=utcnow(),
                finished_at=record.finished_at,
            )
        )
        await self._session.commit()

    async def get_by_flow_id(self, flow_id: str) -> OAuthFlowRecord | None:
        row = await self._session.get(OAuthFlowState, flow_id, populate_existing=True)
        if row is None or self._is_expired_pending(row, utcnow()):
            return None
        return self._to_record(row)

    async def get_by_state_token(self, state_token: str) -> OAuthFlowRecord | None:
        result = await self._session.execute(
            select(OAuthFlowState)
            .where(OAuthFlowState.state_token == state_token)
            .limit(1)
            .execution_options(populate_existing=True)
        )
        row = result.scalar_one_or_none()
        if row is None or self._is_expired_pending(row, utcnow()):
            return None
        return self._to_record(row)

    async def has_pending_browser_flows(self) -> bool:
        now = utcnow()
        result = await self._session.execute(
            select(OAuthFlowState.flow_id)
            .where(
                OAuthFlowState.method == "browser",
                OAuthFlowState.status == "pending",
                or_(OAuthFlowState.expires_at.is_(None), OAuthFlowState.expires_at > now),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def set_status(
        self,
        flow_id: str,
        *,
        status: str,
        error_message: str | None,
    ) -> bool:
        finished_at = utcnow() if status in _TERMINAL_OAUTH_STATUSES else None
        statement = update(OAuthFlowState).where(OAuthFlowState.flow_id == flow_id)
        if status != "success":
            statement = statement.where(OAuthFlowState.status != "success")
        statement = statement.values(
            status=status,
            error_message=error_message,
            finished_at=finished_at,
        ).execution_options(synchronize_session=False)
        result = cast(CursorResult[Any], await self._session.execute(statement))
        await self._session.commit()
        return int(result.rowcount or 0) > 0

    async def purge_expired(self, *, terminal_keep: int) -> None:
        now = utcnow()
        await self._session.execute(
            delete(OAuthFlowState).where(
                OAuthFlowState.status == "pending",
                OAuthFlowState.expires_at.is_not(None),
                OAuthFlowState.expires_at <= now,
            )
        )
        result = await self._session.execute(
            select(OAuthFlowState.flow_id)
            .where(OAuthFlowState.status.in_(tuple(_TERMINAL_OAUTH_STATUSES)))
            .order_by(OAuthFlowState.finished_at.desc())
            .offset(terminal_keep)
        )
        stale_terminal = [row[0] for row in result.all()]
        if stale_terminal:
            await self._session.execute(delete(OAuthFlowState).where(OAuthFlowState.flow_id.in_(stale_terminal)))
        await self._session.commit()

    async def claim_device_slot(self, flow_id: str) -> None:
        now = utcnow()
        dialect = self._session.get_bind().dialect.name
        if dialect == "postgresql":
            insert_stmt = pg_insert(OAuthDeviceFlowSlot)
        elif dialect == "sqlite":
            insert_stmt = sqlite_insert(OAuthDeviceFlowSlot)
        else:  # pragma: no cover - supported backends are SQLite and PostgreSQL
            raise RuntimeError(f"device-flow slot unsupported for dialect={dialect!r}")
        statement = insert_stmt.values(
            slot_key=DEVICE_FLOW_SLOT_KEY,
            flow_id=flow_id,
            generation=1,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[OAuthDeviceFlowSlot.slot_key],
            set_={
                "flow_id": flow_id,
                "generation": OAuthDeviceFlowSlot.generation + 1,
                "updated_at": now,
            },
        )
        await self._session.execute(statement)
        await self._session.commit()

    async def consume_device_slot(self, flow_id: str) -> bool:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                delete(OAuthDeviceFlowSlot).where(
                    OAuthDeviceFlowSlot.slot_key == DEVICE_FLOW_SLOT_KEY,
                    OAuthDeviceFlowSlot.flow_id == flow_id,
                )
            ),
        )
        await self._session.commit()
        return int(result.rowcount or 0) > 0

    async def current_device_slot_flow_id(self) -> str | None:
        result = await self._session.execute(
            select(OAuthDeviceFlowSlot.flow_id).where(OAuthDeviceFlowSlot.slot_key == DEVICE_FLOW_SLOT_KEY)
        )
        return result.scalar_one_or_none()
