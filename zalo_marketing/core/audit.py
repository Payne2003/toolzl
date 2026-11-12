"""SQLite Audit Log — lưu trạng thái, người thực hiện, thời gian, lý do dừng."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .db import Database
from .models import AuditEntry


class AuditLog:
    def __init__(self, db: Database):
        self.db = db

    def record(
        self,
        actor: str,
        action: str,
        entity: str,
        entity_id: int | None = None,
        reason: str | None = None,
        **detail: Any,
    ) -> int:
        """Ghi một dòng nhật ký. Không commit — gọi trong transaction của nghiệp vụ."""
        cur = self.db.execute(
            "INSERT INTO audit_log(ts, actor, action, entity, entity_id, reason, detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.db.now_iso(),
                actor or "unknown",
                action,
                entity,
                entity_id,
                reason,
                json.dumps(detail, ensure_ascii=False) if detail else None,
            ),
        )
        return int(cur.lastrowid)

    def list(
        self,
        limit: int = 500,
        entity: str | None = None,
        entity_id: int | None = None,
        action: str | None = None,
    ) -> list[AuditEntry]:
        sql = "SELECT * FROM audit_log WHERE 1=1"
        params: list[Any] = []
        if entity:
            sql += " AND entity = ?"
            params.append(entity)
        if entity_id is not None:
            sql += " AND entity_id = ?"
            params.append(entity_id)
        if action:
            sql += " AND action = ?"
            params.append(action)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [AuditEntry(**dict(r)) for r in self.db.query(sql, tuple(params))]

    def export_csv(self, path: str | Path) -> int:
        rows = self.db.query("SELECT * FROM audit_log ORDER BY id")
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(["id", "ts", "actor", "action", "entity", "entity_id", "reason", "detail"])
            for r in rows:
                writer.writerow([r[k] for k in ("id", "ts", "actor", "action", "entity", "entity_id", "reason", "detail")])
        return len(rows)
