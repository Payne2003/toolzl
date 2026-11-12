"""Cửa sổ chính — PySide6 Marketing Dashboard."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..core.models import JobStatus, PostStatus
from ..core.services import Services
from .common import guarded
from .tabs_content import ApprovalTab, ContentTab
from .tabs_groups import GroupsTab
from .tabs_history import HistoryTab, SettingsTab
from .tabs_queue import QueueTab

REFRESH_MS = 60_000


class MainWindow(QMainWindow):
    def __init__(self, svc: Services):
        super().__init__()
        self.svc = svc
        self.setWindowTitle(f"Zalo Marketing — Group Posting v{__version__}")
        self.resize(1180, 760)

        # --- Thanh trên: dừng khẩn cấp + trạng thái
        self.kill_btn = QPushButton()
        self.kill_btn.setMinimumHeight(36)
        self.kill_btn.clicked.connect(self.toggle_kill_switch)
        self.status_info = QLabel()
        top = QHBoxLayout()
        top.addWidget(self.kill_btn)
        top.addSpacing(16)
        top.addWidget(self.status_info, 1)

        op = self.operator
        self.content_tab = ContentTab(svc, op)
        self.approval_tab = ApprovalTab(svc, op)
        self.groups_tab = GroupsTab(svc, op)
        self.queue_tab = QueueTab(svc, op)
        self.history_tab = HistoryTab(svc)
        self.settings_tab = SettingsTab(svc, op)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.content_tab, "✏️ Soạn nội dung")
        self.tabs.addTab(self.approval_tab, "✅ Phê duyệt")
        self.tabs.addTab(self.groups_tab, "👥 Quản lý nhóm")
        self.tabs.addTab(self.queue_tab, "📤 Hàng đợi")
        self.tabs.addTab(self.history_tab, "📜 Lịch sử")
        self.tabs.addTab(self.settings_tab, "⚙️ Cài đặt")
        self.tabs.currentChanged.connect(self._on_tab)

        for t in (self.content_tab, self.approval_tab, self.groups_tab, self.queue_tab, self.settings_tab):
            t.changed.connect(self.refresh_all)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(top)
        lay.addWidget(self.tabs)
        self.setCentralWidget(central)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(REFRESH_MS)

        self.refresh_header()

    # ---------------------------------------------------------------- helpers
    def operator(self) -> str:
        return self.svc.db.get_setting("operator_name") or "unknown"

    def ensure_operator(self) -> None:
        if self.svc.db.get_setting("operator_name"):
            return
        name, ok = QInputDialog.getText(self, "Chào mừng", "Nhập tên của bạn (dùng cho nhật ký kiểm toán):")
        name = name.strip() if ok else ""
        self.svc.dispatcher.update_settings(name or "operator", operator_name=name or "operator")
        self.settings_tab.reload()

    def refresh_header(self) -> None:
        on = bool(self.svc.db.get_setting("kill_switch"))
        if on:
            self.kill_btn.setText("⛔ ĐANG DỪNG KHẨN CẤP — bấm để tiếp tục")
            self.kill_btn.setStyleSheet("background:#b71c1c;color:white;font-weight:bold;padding:4px 14px;")
        else:
            self.kill_btn.setText("🛑 DỪNG KHẨN CẤP")
            self.kill_btn.setStyleSheet("background:#e53935;color:white;font-weight:bold;padding:4px 14px;")
        q = self.svc.db.query_one
        pending = q("SELECT COUNT(*) n FROM posts WHERE status = ?", (PostStatus.PENDING.value,))["n"]
        queued = q("SELECT COUNT(*) n FROM jobs WHERE status = ?", (JobStatus.QUEUED.value,))["n"]
        blocked = q("SELECT COUNT(*) n FROM jobs WHERE status = ?", (JobStatus.BLOCKED.value,))["n"]
        handed = q("SELECT COUNT(*) n FROM jobs WHERE status = ?", (JobStatus.HANDED_OFF.value,))["n"]
        self.status_info.setText(
            f"👤 {self.operator()}   ·   Chờ duyệt: <b>{pending}</b>   ·   Đang chờ: <b>{queued}</b>   ·   "
            f"Bị chặn: <b>{blocked}</b>   ·   Chờ xác nhận: <b>{handed}</b>"
        )

    def refresh_all(self) -> None:
        for t in (self.content_tab, self.approval_tab, self.groups_tab, self.queue_tab, self.history_tab):
            t.reload()
        self.refresh_header()

    def _on_tab(self, idx: int) -> None:
        w = self.tabs.widget(idx)
        if hasattr(w, "reload"):
            w.reload()
        self.refresh_header()

    def _tick(self) -> None:
        if self.tabs.currentWidget() is self.queue_tab:
            self.queue_tab.reload()
        self.refresh_header()

    @guarded
    def toggle_kill_switch(self):
        on = bool(self.svc.db.get_setting("kill_switch"))
        if on:
            reason, ok = QInputDialog.getText(self, "Tiếp tục hoạt động", "Lý do tắt dừng khẩn cấp:")
        else:
            reason, ok = QInputDialog.getText(self, "Dừng khẩn cấp",
                                              "Mọi lệnh đăng sẽ bị chặn ngay lập tức.\nLý do dừng:",
                                              text="Dừng khẩn cấp thủ công")
        if not ok:
            return
        if not reason.strip():
            QMessageBox.warning(self, "Dừng khẩn cấp", "Cần ghi lý do.")
            return
        self.svc.dispatcher.set_kill_switch(not on, self.operator(), reason)
        self.refresh_all()

    def closeEvent(self, event):  # noqa: N802
        handed = self.svc.db.query_one("SELECT COUNT(*) n FROM jobs WHERE status = 'handed_off'")["n"]
        if handed:
            ans = QMessageBox.question(
                self, "Còn lệnh chờ xác nhận",
                f"Có {handed} lệnh đã bàn giao nhưng chưa xác nhận kết quả.\n"
                "Bạn có thể xác nhận sau trong tab Hàng đợi. Vẫn thoát?")
            if ans != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()
