"""Small durable SessionStore adapter for the owned lesson 35 workspace."""

import asyncio
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from claude_agent_sdk import (
    SessionKey,
    SessionListSubkeysKey,
    SessionStoreEntry,
    SessionStoreListEntry,
    SessionSummaryEntry,
    fold_session_summary,
)


class SQLiteSessionStore:
    """Transactional SQLite mirror scoped by project, session and optional subpath."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    subpath TEXT NOT NULL,
                    uuid TEXT,
                    payload TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS entries_uuid
                    ON entries(project_key, session_id, subpath, uuid)
                    WHERE uuid IS NOT NULL;
                CREATE INDEX IF NOT EXISTS entries_key
                    ON entries(project_key, session_id, subpath, id);
                CREATE TABLE IF NOT EXISTS sessions (
                    project_key TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    subpath TEXT NOT NULL,
                    mtime INTEGER NOT NULL,
                    PRIMARY KEY(project_key, session_id, subpath)
                );
                CREATE TABLE IF NOT EXISTS summaries (
                    project_key TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY(project_key, session_id)
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @staticmethod
    def _parts(key: SessionKey) -> tuple[str, str, str]:
        return key["project_key"], key["session_id"], key.get("subpath", "")

    def _append(self, key: SessionKey, entries: list[SessionStoreEntry]) -> None:
        if not entries:
            return
        project, session, subpath = self._parts(key)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            before = db.total_changes
            inserted: list[SessionStoreEntry] = []
            for entry in entries:
                cursor = db.execute(
                    "INSERT OR IGNORE INTO entries(project_key,session_id,subpath,uuid,payload) VALUES(?,?,?,?,?)",
                    (project, session, subpath, entry.get("uuid"), json.dumps(entry, ensure_ascii=False, separators=(",", ":"))),
                )
                if cursor.rowcount:
                    inserted.append(entry)
            if db.total_changes > before:
                old = db.execute("SELECT mtime FROM sessions WHERE project_key=? AND session_id=? AND subpath=?",
                                 (project, session, subpath)).fetchone()
                now = max(int(time.time() * 1000), old[0] + 1 if old else 0)
                db.execute("INSERT INTO sessions VALUES(?,?,?,?) ON CONFLICT(project_key,session_id,subpath) DO UPDATE SET mtime=excluded.mtime",
                           (project, session, subpath, now))
                if not subpath:
                    previous = db.execute("SELECT payload FROM summaries WHERE project_key=? AND session_id=?",
                                          (project, session)).fetchone()
                    summary = fold_session_summary(json.loads(previous[0]) if previous else None, key, inserted)
                    summary["mtime"] = now
                    db.execute("INSERT INTO summaries VALUES(?,?,?) ON CONFLICT(project_key,session_id) DO UPDATE SET payload=excluded.payload",
                               (project, session, json.dumps(summary, ensure_ascii=False)))

    async def append(self, key: SessionKey, entries: list[SessionStoreEntry]) -> None:
        await asyncio.to_thread(self._append, key, entries)

    def _load(self, key: SessionKey) -> list[SessionStoreEntry] | None:
        project, session, subpath = self._parts(key)
        with closing(self._connect()) as db, db:
            exists = db.execute("SELECT 1 FROM sessions WHERE project_key=? AND session_id=? AND subpath=?",
                                (project, session, subpath)).fetchone()
            if not exists:
                return None
            rows = db.execute("SELECT payload FROM entries WHERE project_key=? AND session_id=? AND subpath=? ORDER BY id",
                              (project, session, subpath)).fetchall()
        return [json.loads(row[0]) for row in rows]

    async def load(self, key: SessionKey) -> list[SessionStoreEntry] | None:
        return await asyncio.to_thread(self._load, key)

    def _list_sessions(self, project_key: str) -> list[SessionStoreListEntry]:
        with closing(self._connect()) as db, db:
            rows = db.execute("SELECT session_id,mtime FROM sessions WHERE project_key=? AND subpath='' ORDER BY mtime DESC",
                              (project_key,)).fetchall()
        return [{"session_id": session_id, "mtime": mtime} for session_id, mtime in rows]

    async def list_sessions(self, project_key: str) -> list[SessionStoreListEntry]:
        return await asyncio.to_thread(self._list_sessions, project_key)

    def _list_session_summaries(self, project_key: str) -> list[SessionSummaryEntry]:
        with closing(self._connect()) as db, db:
            rows = db.execute("SELECT payload FROM summaries WHERE project_key=?",
                              (project_key,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    async def list_session_summaries(self, project_key: str) -> list[SessionSummaryEntry]:
        return await asyncio.to_thread(self._list_session_summaries, project_key)

    def _list_subkeys(self, key: SessionListSubkeysKey) -> list[str]:
        with closing(self._connect()) as db, db:
            rows = db.execute("SELECT subpath FROM sessions WHERE project_key=? AND session_id=? AND subpath<>'' ORDER BY subpath",
                              (key["project_key"], key["session_id"])).fetchall()
        return [row[0] for row in rows]

    async def list_subkeys(self, key: SessionListSubkeysKey) -> list[str]:
        return await asyncio.to_thread(self._list_subkeys, key)

    def _delete(self, key: SessionKey) -> None:
        project, session, subpath = self._parts(key)
        clause = "project_key=? AND session_id=? AND subpath=?" if subpath else "project_key=? AND session_id=?"
        args = (project, session, subpath) if subpath else (project, session)
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM entries WHERE " + clause, args)
            db.execute("DELETE FROM sessions WHERE " + clause, args)
            if not subpath:
                db.execute("DELETE FROM summaries WHERE project_key=? AND session_id=?", (project, session))

    async def delete(self, key: SessionKey) -> None:
        await asyncio.to_thread(self._delete, key)
