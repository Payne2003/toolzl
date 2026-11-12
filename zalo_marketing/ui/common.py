"""Tiện ích giao diện dùng chung."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QTableWidget, QTableWidgetItem, QWidget, QHeaderView, QAbstractItemView

from ..core.db import from_iso
from ..core.errors import BotError, GateBlocked

POST_STATUS_VI = {
    "draft": "Nháp",
    "pending": "Chờ duyệt",
    "approved": "Đã duyệt 🔒",
    "rejected": "Bị từ chối",
    "archived": "Lưu trữ",
}

JOB_STATUS_VI = {
    "queued": "Đang chờ",
    "blocked": "Bị chặn",
    "handed_off": "Đã bàn giao",
    "sent": "Đã gửi",
    "skipped": "Bỏ qua",
    "failed": "Lỗi",
    "cancelled": "Đã hủy",
}

GROUP_STATUS_VI = {"active": "Hoạt động", "paused": "Tạm dừng", "archived": "Lưu trữ"}
CHANNEL_VI = {"manual": "Thủ công", "api": "Official API"}


def fmt_ts(value: str | None) -> str:
    dt = from_iso(value)
    return dt.astimezone().strftime("%d/%m/%Y %H:%M") if dt else ""


def local_now() -> datetime:
    return datetime.now().astimezone()


def make_table(headers: list[str], parent: QWidget | None = None) -> QTableWidget:
    t = QTableWidget(0, len(headers), parent)
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def fill_table(table: QTableWidget, rows: list[list], ids: list[int] | None = None) -> None:
    selected = selected_id(table)
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            text = "" if value is None else str(value)
            item = QTableWidgetItem(text)
            if len(text) > 40:
                item.setToolTip(text)
            if c == 0 and ids is not None:
                item.setData(Qt.UserRole, ids[r])
            table.setItem(r, c, item)
    table.resizeColumnsToContents()
    if selected is not None:
        select_id(table, selected)


def selected_id(table: QTableWidget) -> int | None:
    row = table.currentRow()
    if row < 0:
        return None
    item = table.item(row, 0)
    if item is None:
        return None
    value = item.data(Qt.UserRole)
    return int(value) if value is not None else None


def select_id(table: QTableWidget, target: int) -> None:
    for r in range(table.rowCount()):
        item = table.item(r, 0)
        if item is not None and item.data(Qt.UserRole) == target:
            table.selectRow(r)
            return


def show_error(parent: QWidget, exc: Exception) -> None:
    if isinstance(exc, GateBlocked):
        QMessageBox.warning(parent, "Safety Gate đã chặn",
                            "Không đủ điều kiện đăng:\n\n• " + "\n• ".join(exc.reasons))
    elif isinstance(exc, BotError):
        QMessageBox.warning(parent, "Không thực hiện được", str(exc))
    else:
        QMessageBox.critical(parent, "Lỗi", f"{type(exc).__name__}: {exc}")


def guarded(fn):
    """Decorator cho slot không tham số: bắt lỗi nghiệp vụ và hiển thị thông báo.
    Bỏ qua tham số do signal truyền vào (ví dụ `checked` của QPushButton.clicked)."""
    def wrapper(self, *_args, **_kwargs):
        try:
            return fn(self)
        except Exception as e:  # noqa: BLE001
            show_error(self, e)
            return None
    wrapper.__name__ = fn.__name__
    return wrapper
