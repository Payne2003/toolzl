"""Gom các thành phần lõi thành một đối tượng để giao diện sử dụng."""

from __future__ import annotations

from pathlib import Path

from .approval import ApprovalEngine
from .audit import AuditLog
from .db import Clock, Database, utc_now
from .dispatcher import Dispatcher
from .groups import GroupRepository
from .publishers import OfficialApiPublisher
from .templates import TemplateRepository


class Services:
    def __init__(self, db_path: str | Path = ":memory:", clock: Clock = utc_now,
                 api_publisher: OfficialApiPublisher | None = None):
        self.db = Database(db_path, clock)
        self.audit = AuditLog(self.db)
        self.groups = GroupRepository(self.db, self.audit)
        self.posts = ApprovalEngine(self.db, self.audit)
        self.templates = TemplateRepository(self.db, self.audit)
        self.dispatcher = Dispatcher(self.db, self.audit, self.posts, self.groups, api_publisher)

    def close(self) -> None:
        self.db.close()
