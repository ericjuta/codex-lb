from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import app.db.recover as recover_module
import app.db.sqlite_utils as sqlite_utils_module
from app.db.backup import create_sqlite_pre_migration_backup
from app.db.sqlite_utils import sqlite_connection


class _TrackedConnection(sqlite3.Connection):
    __slots__ = ("closed",)

    def __init__(self, database: str) -> None:
        super().__init__(database)
        self.closed = False

    def close(self) -> None:
        self.closed = True
        super().close()


def _track_connections(monkeypatch: pytest.MonkeyPatch) -> list[_TrackedConnection]:
    connections: list[_TrackedConnection] = []

    def connect(database: str | Path, *args: object, **kwargs: object) -> sqlite3.Connection:
        del args, kwargs
        connection = _TrackedConnection(str(database))
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite_utils_module.sqlite3, "connect", connect)
    return connections


def _close_connections(connections: list[_TrackedConnection]) -> None:
    for connection in connections:
        try:
            connection.close()
        except sqlite3.Error:
            pass


def _patch_path_mutation(
    monkeypatch: pytest.MonkeyPatch,
    *,
    method_name: str,
    connections: list[_TrackedConnection],
    snapshots: list[tuple[Path, tuple[bool, ...]]],
) -> None:
    original = getattr(Path, method_name)

    def tracked(self: Path, *args: object, **kwargs: object) -> object:
        assert connections, f"expected tracked sqlite connections before Path.{method_name}"
        states = tuple(connection.closed for connection in connections)
        snapshots.append((self, states))
        assert all(states), (
            f"sqlite connection still open at Path.{method_name} for {self}; closed={states}"
        )
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, method_name, tracked)


def test_backup_closes_connections_before_rotating_old_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "store.db"
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        connection.execute("INSERT INTO items (name) VALUES ('alpha')")

    connections = _track_connections(monkeypatch)
    unlink_snapshots: list[tuple[Path, tuple[bool, ...]]] = []
    _patch_path_mutation(
        monkeypatch,
        method_name="unlink",
        connections=connections,
        snapshots=unlink_snapshots,
    )
    base_time = datetime(2026, 7, 29, tzinfo=timezone.utc)
    expected_first_backup = tmp_path / "store.pre-migrate-20260729T000000Z.db"
    expected_second_backup = tmp_path / "store.pre-migrate-20260729T000100Z.db"

    try:
        first_backup = create_sqlite_pre_migration_backup(db_path, max_files=1, now=base_time)
        second_backup = create_sqlite_pre_migration_backup(
            db_path,
            max_files=1,
            now=base_time + timedelta(minutes=1),
        )

        assert first_backup == expected_first_backup
        assert second_backup == expected_second_backup
        assert not first_backup.exists()
        assert second_backup.exists()
        assert connections
        assert [path for path, _states in unlink_snapshots] == [first_backup]
        assert all(connection.closed for connection in connections)
        assert all(all(states) for _path, states in unlink_snapshots)
    finally:
        _close_connections(connections)


def test_recover_cli_closes_connections_before_replacing_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "store.db"
    output_path = tmp_path / "recovered.db"
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        connection.execute("INSERT INTO items (name) VALUES ('alpha')")

    connections = _track_connections(monkeypatch)
    replace_snapshots: list[tuple[Path, tuple[bool, ...]]] = []
    _patch_path_mutation(
        monkeypatch,
        method_name="replace",
        connections=connections,
        snapshots=replace_snapshots,
    )
    corrupt_path = tmp_path / "store.db.corrupt-20260729-000000"
    monkeypatch.setattr(recover_module, "_timestamp", lambda: "20260729-000000")

    try:
        exit_code = recover_module.main(
            [
                "--db",
                str(db_path),
                "--output",
                str(output_path),
                "--replace",
            ]
        )

        assert exit_code == 0
        assert corrupt_path.exists()
        assert db_path.exists()
        assert not output_path.exists()
        assert connections
        assert [path for path, _states in replace_snapshots] == [db_path, output_path]
        assert all(connection.closed for connection in connections)
        assert all(all(states) for _path, states in replace_snapshots)

        with closing(sqlite3.connect(db_path)) as connection:
            assert connection.execute("SELECT name FROM items").fetchall() == [("alpha",)]
    finally:
        _close_connections(connections)


def test_sqlite_connection_closes_and_rolls_back_on_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "store.db"
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")

    connections = _track_connections(monkeypatch)

    try:
        with pytest.raises(RuntimeError, match="boom"):
            with sqlite_connection(db_path) as connection:
                connection.execute("INSERT INTO items (name) VALUES ('beta')")
                assert connection.execute("SELECT name FROM items").fetchall() == [("beta",)]
                raise RuntimeError("boom")

        assert connections
        assert len(connections) == 1
        assert connections[0].closed is True

        with closing(sqlite3.connect(db_path)) as connection:
            assert connection.execute("SELECT name FROM items").fetchall() == []
    finally:
        _close_connections(connections)
