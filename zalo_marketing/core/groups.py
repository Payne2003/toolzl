"""Quản lý nhóm Zalo (danh sách trắng)."""

from __future__ import annotations

import re
from typing import Any

from .audit import AuditLog
from .db import Database
from .errors import NotFound, ValidationError
from .models import Group, GroupStatus

# Link mời nhóm Zalo chính thức có dạng https://zalo.me/g/<mã>
GROUP_LINK_RE = re.compile(r"^https://zalo\.me/g/[A-Za-z0-9_-]+/?$")

_EDITABLE = {"name", "link", "allowed", "can_post", "status", "api_group_id", "api_verified", "notes"}


def validate_link(link: str) -> str:
    link = (link or "").strip()
    if link and not GROUP_LINK_RE.match(link):
        raise ValidationError(
            "Link nhóm không hợp lệ. Dùng link mời chính thức dạng https://zalo.me/g/xxxx "
            "(hoặc để trống — khi đó chỉ chép nội dung, bạn tự mở nhóm)."
        )
    return link


def _row_to_group(r) -> Group:
    return Group(
        id=r["id"],
        name=r["name"],
        link=r["link"],
        allowed=bool(r["allowed"]),
        can_post=bool(r["can_post"]),
        status=GroupStatus(r["status"]),
        api_group_id=r["api_group_id"],
        api_verified=bool(r["api_verified"]),
        notes=r["notes"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


class GroupRepository:
    def __init__(self, db: Database, audit: AuditLog):
        self.db = db
        self.audit = audit

    def get(self, group_id: int) -> Group:
        r = self.db.query_one("SELECT * FROM groups WHERE id = ?", (group_id,))
        if r is None:
            raise NotFound(f"Không tìm thấy nhóm #{group_id}")
        return _row_to_group(r)

    def list(self, include_archived: bool = False) -> list[Group]:
        sql = "SELECT * FROM groups"
        if not include_archived:
            sql += " WHERE status != 'archived'"
        sql += " ORDER BY name COLLATE NOCASE"
        return [_row_to_group(r) for r in self.db.query(sql)]

    def add(
        self,
        name: str,
        actor: str,
        link: str = "",
        allowed: bool = False,
        can_post: bool = False,
        notes: str = "",
    ) -> Group:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Tên nhóm không được để trống.")
        link = validate_link(link)
        if link and self.db.query_one("SELECT 1 FROM groups WHERE link = ? AND status != 'archived'", (link,)):
            raise ValidationError("Nhóm với link này đã tồn tại.")
        now = self.db.now_iso()
        with self.db.transaction():
            cur = self.db.execute(
                "INSERT INTO groups(name, link, allowed, can_post, notes, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, link, int(allowed), int(can_post), notes, now, now),
            )
            gid = int(cur.lastrowid)
            self.audit.record(actor, "group.create", "group", gid, name=name, link=link,
                              allowed=allowed, can_post=can_post)
        return self.get(gid)

    def update(self, group_id: int, actor: str, reason: str | None = None, **fields: Any) -> Group:
        unknown = set(fields) - _EDITABLE
        if unknown:
            raise ValidationError(f"Trường không hợp lệ: {', '.join(sorted(unknown))}")
        current = self.get(group_id)
        if "name" in fields:
            fields["name"] = (fields["name"] or "").strip()
            if not fields["name"]:
                raise ValidationError("Tên nhóm không được để trống.")
        if "link" in fields:
            fields["link"] = validate_link(fields["link"])
        if "status" in fields:
            fields["status"] = GroupStatus(fields["status"]).value
        for b in ("allowed", "can_post", "api_verified"):
            if b in fields:
                fields[b] = int(bool(fields[b]))
        if "api_group_id" in fields:
            fields["api_group_id"] = (fields["api_group_id"] or "").strip() or None

        changes: dict[str, Any] = {}
        for k, v in fields.items():
            old = getattr(current, k)
            old = old.value if isinstance(old, GroupStatus) else (int(old) if isinstance(old, bool) else old)
            if old != v:
                changes[k] = {"from": old, "to": v}
        if not changes:
            return current

        sets = ", ".join(f"{k} = ?" for k in changes)
        with self.db.transaction():
            self.db.execute(
                f"UPDATE groups SET {sets}, updated_at = ? WHERE id = ?",
                (*[fields[k] for k in changes], self.db.now_iso(), group_id),
            )
            self.audit.record(actor, "group.update", "group", group_id, reason=reason, changes=changes)
        return self.get(group_id)

    def archive(self, group_id: int, actor: str, reason: str | None = None) -> Group:
        return self.update(group_id, actor, reason=reason, status=GroupStatus.ARCHIVED.value)
