"""Lớp lưu trữ SQLite: schema, kết nối, đồng hồ và cài đặt."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    link          TEXT NOT NULL DEFAULT '',
    allowed       INTEGER NOT NULL DEFAULT 0,
    can_post      INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'active',
    api_group_id  TEXT,
    api_verified  INTEGER NOT NULL DEFAULT 0,
    notes         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL,
    body           TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'draft',
    version        INTEGER NOT NULL DEFAULT 1,
    content_hash   TEXT NOT NULL,
    author         TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    approved_by    TEXT,
    approved_at    TEXT,
    approved_hash  TEXT,
    review_note    TEXT
);

-- Lịch sử phiên bản nội dung (bất biến)
CREATE TABLE IF NOT EXISTS post_versions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id       INTEGER NOT NULL REFERENCES posts(id),
    version       INTEGER NOT NULL,
    title         TEXT NOT NULL,
    body          TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    created_by    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    UNIQUE (post_id, version)
);

CREATE TABLE IF NOT EXISTS jobs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id        INTEGER NOT NULL REFERENCES posts(id),
    post_version   INTEGER NOT NULL,
    content_hash   TEXT NOT NULL,
    group_id       INTEGER NOT NULL REFERENCES groups(id),
    channel        TEXT NOT NULL DEFAULT 'manual',
    status         TEXT NOT NULL DEFAULT 'queued',
    scheduled_at   TEXT,
    block_reason   TEXT,
    created_by     TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    handed_off_at  TEXT,
    completed_at   TEXT,
    completed_by   TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_group_hash ON jobs(group_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

-- Nhật ký kiểm toán: chỉ thêm, không sửa/xóa
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    entity     TEXT NOT NULL,
    entity_id  INTEGER,
    reason     TEXT,
    detail     TEXT
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""

DEFAULT_SETTINGS: dict[str, Any] = {
    # Dừng khẩn cấp: khi bật, mọi lệnh đăng đều bị chặn.
    "kill_switch": False,
    # Khoảng cách tối thiểu giữa 2 lần đăng vào cùng một nhóm (phút).
    "min_interval_minutes": 60,
    # Số lần đăng tối đa mỗi ngày (tính trên tất cả các nhóm).
    "daily_limit": 20,
    # Số lần đăng tối đa mỗi ngày vào cùng một nhóm.
    "per_group_daily_limit": 2,
    # Không gửi lại cùng một nội dung vào cùng một nhóm trong N ngày.
    "dedupe_days": 7,
    # Khung giờ yên lặng (giờ địa phương, định dạng HH:MM). Rỗng = tắt.
    "quiet_start": "22:00",
    "quiet_end": "07:00",
    # Bắt buộc người duyệt khác người soạn (nguyên tắc 4 mắt).
    "require_different_approver": False,
    # Kênh Official API: tắt mặc định, chỉ bật khi đã được Zalo xác nhận quyền.
    "official_api_enabled": False,
    # Tự động dừng (bật kill switch) sau N lỗi API liên tiếp.
    "auto_stop_after_failures": 3,
    # Tên người dùng hiện tại (hiển thị trong nhật ký).
    "operator_name": "",
}


Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class Database:
    """Bao bọc kết nối SQLite kèm đồng hồ (có thể thay thế khi kiểm thử)."""

    def __init__(self, path: str | Path = ":memory:", clock: Clock = utc_now):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.clock = clock
        self._migrate()

    # ------------------------------------------------------------------ infra
    def _migrate(self) -> None:
        with self.conn:
            self.conn.executescript(SCHEMA)
            self.conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def now(self) -> datetime:
        return self.clock()

    def now_iso(self) -> str:
        return to_iso(self.clock())

    def close(self) -> None:
        self.conn.close()

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def transaction(self):
        """Dùng: `with db.transaction(): ...` — commit/rollback tự động."""
        return self.conn

    # --------------------------------------------------------------- settings
    def get_setting(self, key: str) -> Any:
        row = self.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        if row is None:
            return DEFAULT_SETTINGS.get(key)
        return json.loads(row["value"])

    def set_setting(self, key: str, value: Any) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )

    def all_settings(self) -> dict[str, Any]:
        result = dict(DEFAULT_SETTINGS)
        for row in self.query("SELECT key, value FROM settings"):
            result[row["key"]] = json.loads(row["value"])
        return result
