"""Cửa sổ chính — PySide6 Marketing Dashboard (sidebar + trang nội dung)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..core.models import JobStatus, PostStatus
from ..core.services import Services
from .common import guarded
from .tabs_content import ApprovalTab, ContentTab
from .tabs_groups import GroupsTab
from .tabs_history import HistoryTab, SettingsTab
from .tabs_queue import QueueTab
from .tabs_templates import TemplatesTab
from .updater_ui import UpdateController
from .theme import label, repolish

REFRESH_MS = 60_000

PAGES = [
    # (icon, tên, tiêu đề, mô tả)
    ("🏷️", "Sản phẩm & Mẫu", "Sản phẩm & Mẫu bài",
     "Thông tin sản phẩm quảng cáo (Tool HanaMedia) và thư viện mẫu bài viết."),
    ("✏️", "Soạn nội dung", "Soạn nội dung", "Viết bài marketing và gửi duyệt. Nội dung đã duyệt sẽ được khóa phiên bản."),
    ("✅", "Phê duyệt", "Phê duyệt", "Xem đúng bản sẽ được gửi, duyệt hoặc từ chối kèm lý do."),
    ("👥", "Quản lý nhóm", "Quản lý nhóm", "Danh sách trắng các nhóm Zalo bạn được phép đăng bài."),
    ("📤", "Hàng đợi", "Hàng đợi đăng bài", "Xếp lệnh, kiểm tra Safety Gate và bàn giao để bạn tự gửi trên Zalo."),
    ("📜", "Lịch sử", "Lịch sử & Nhật ký", "Lịch sử đăng bài và nhật ký kiểm toán (chỉ thêm, không sửa/xóa)."),
    ("⚙️", "Cài đặt", "Cài đặt", "Giới hạn tần suất, khung giờ yên lặng và kênh Official API."),
]


class StatCard(QFrame):
    def __init__(self, title: str, accent: str):
        super().__init__()
        self.setObjectName("Stat")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 16, 12)
        lay.setSpacing(12)
        bar = QFrame()
        bar.setFixedSize(4, 36)
        bar.setStyleSheet(f"background:{accent}; border-radius:2px;")
        col = QVBoxLayout()
        col.setSpacing(0)
        self.value = label("0", "StatValue")
        col.addWidget(self.value)
        col.addWidget(label(title.upper(), "StatLabel"))
        lay.addWidget(bar)
        lay.addLayout(col)
        lay.addStretch()

    def set(self, n: int) -> None:
        self.value.setText(str(n))


class MainWindow(QMainWindow):
    def __init__(self, svc: Services):
        super().__init__()
        self.svc = svc
        self.setWindowTitle(f"Zalo Marketing — Group Posting v{__version__}")
        self.resize(1280, 820)
        self.setMinimumSize(1080, 680)

        op = self.operator
        self.templates_tab = TemplatesTab(svc, op)
        self.content_tab = ContentTab(svc, op)
        self.approval_tab = ApprovalTab(svc, op)
        self.groups_tab = GroupsTab(svc, op)
        self.queue_tab = QueueTab(svc, op)
        self.history_tab = HistoryTab(svc)
        self.settings_tab = SettingsTab(svc, op)
        self.pages = [self.templates_tab, self.content_tab, self.approval_tab, self.groups_tab, self.queue_tab,
                      self.history_tab, self.settings_tab]
        for t in self.pages:
            if hasattr(t, "changed"):
                t.changed.connect(self.refresh_all)
        self.templates_tab.use_template.connect(self._open_template)

        root = QWidget()
        rl = QHBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self._build_sidebar())
        rl.addWidget(self._build_main(), 1)
        self.setCentralWidget(root)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(REFRESH_MS)

        self.updater = UpdateController(svc, self)
        self.updater.available.connect(self._on_update_available)
        self.updater.checking.connect(self._on_checking)
        if svc.db.get_setting("auto_check_updates"):
            QTimer.singleShot(3000, lambda: self.updater.check(silent=True))

        self.nav.setCurrentRow(0)
        self.refresh_header()

    def _on_update_available(self, info) -> None:
        self.update_btn.setText(f"⬆  Cập nhật lên v{info.version}")
        self.update_btn.setVisible(True)

    def _on_checking(self, busy: bool) -> None:
        self.check_btn.setEnabled(not busy)
        self.check_btn.setText("Đang kiểm tra…" if busy else f"⟳  Kiểm tra cập nhật · v{__version__}")

    # ----------------------------------------------------------------- layout
    def _build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(236)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 22, 0, 18)
        lay.setSpacing(4)

        brand = QHBoxLayout()
        brand.setContentsMargins(20, 0, 20, 0)
        logo = QLabel("Z")
        logo.setFixedSize(36, 36)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("background:#0068FF;color:white;border-radius:10px;font-size:18px;font-weight:800;")
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("Zalo Marketing", "Brand"))
        names.addWidget(label(f"Group Posting · v{__version__}", "BrandSub"))
        brand.addWidget(logo)
        brand.addSpacing(8)
        brand.addLayout(names)
        brand.addStretch()
        lay.addLayout(brand)
        lay.addSpacing(22)

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFocusPolicy(Qt.NoFocus)
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setCursor(Qt.PointingHandCursor)
        for icon, name, *_ in PAGES:
            QListWidgetItem(f"{icon}   {name}", self.nav)
        self.nav.currentRowChanged.connect(self._on_nav)
        lay.addWidget(self.nav, 1)

        foot = QVBoxLayout()
        foot.setContentsMargins(16, 0, 16, 0)
        foot.setSpacing(10)
        self.operator_label = label("", "Operator")
        foot.addWidget(self.operator_label)
        self.update_btn = QPushButton()
        self.update_btn.setObjectName("UpdateButton")
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.setVisible(False)
        self.update_btn.clicked.connect(lambda: self.updater.prompt())
        foot.addWidget(self.update_btn)
        self.check_btn = QPushButton(f"⟳  Kiểm tra cập nhật · v{__version__}")
        self.check_btn.setObjectName("CheckUpdate")
        self.check_btn.setCursor(Qt.PointingHandCursor)
        self.check_btn.clicked.connect(lambda: self.updater.check(silent=False))
        foot.addWidget(self.check_btn)
        self.kill_btn = QPushButton()
        self.kill_btn.setObjectName("KillSwitch")
        self.kill_btn.setCursor(Qt.PointingHandCursor)
        self.kill_btn.clicked.connect(self.toggle_kill_switch)
        foot.addWidget(self.kill_btn)
        lay.addLayout(foot)
        return side

    def _build_main(self) -> QWidget:
        main = QWidget()
        main.setObjectName("Page")
        lay = QVBoxLayout(main)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(16)

        self.title = label("", "PageTitle")
        self.subtitle = label("", "PageSubtitle")
        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(self.title)
        head.addWidget(self.subtitle)
        lay.addLayout(head)

        self.banner = QFrame()
        self.banner.setObjectName("Banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(14, 10, 14, 10)
        self.banner_text = label("", "BannerText", wrap=True)
        bl.addWidget(self.banner_text, 1)
        lay.addWidget(self.banner)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.stat_pending = StatCard("Chờ duyệt", "#F5A524")
        self.stat_queued = StatCard("Đang chờ đăng", "#0068FF")
        self.stat_blocked = StatCard("Bị chặn", "#E5484D")
        self.stat_handed = StatCard("Chờ xác nhận", "#7C4DFF")
        self.stat_sent = StatCard("Đã gửi 24 giờ", "#1F9D55")
        for c in (self.stat_pending, self.stat_queued, self.stat_blocked, self.stat_handed, self.stat_sent):
            stats.addWidget(c, 1)
        lay.addLayout(stats)

        self.stack = QStackedWidget()
        for p in self.pages:
            self.stack.addWidget(p)
        lay.addWidget(self.stack, 1)
        return main

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
        self.refresh_header()

    def refresh_header(self) -> None:
        on = bool(self.svc.db.get_setting("kill_switch"))
        self.kill_btn.setText("▶  Tiếp tục hoạt động" if on else "■  Dừng khẩn cấp")
        self.kill_btn.setProperty("active", on)
        repolish(self.kill_btn)
        self.banner.setVisible(on)
        if on:
            last = self.svc.audit.list(limit=1, action="kill_switch.on")
            why = f" — {last[0].reason} ({last[0].actor})" if last else ""
            self.banner_text.setText(f"⛔  Đang dừng khẩn cấp: mọi lệnh đăng đều bị chặn{why}")
        self.operator_label.setText(f"👤  {self.operator()}")

        q = self.svc.db.query_one
        count = lambda status: q("SELECT COUNT(*) n FROM jobs WHERE status = ?", (status,))["n"]  # noqa: E731
        self.stat_pending.set(q("SELECT COUNT(*) n FROM posts WHERE status = ?", (PostStatus.PENDING.value,))["n"])
        self.stat_queued.set(count(JobStatus.QUEUED.value))
        self.stat_blocked.set(count(JobStatus.BLOCKED.value))
        self.stat_handed.set(count(JobStatus.HANDED_OFF.value))
        from datetime import timedelta
        from ..core.db import to_iso
        since = to_iso(self.svc.db.now() - timedelta(hours=24))
        self.stat_sent.set(q("SELECT COUNT(*) n FROM jobs WHERE status = 'sent' AND completed_at >= ?", (since,))["n"])

    def refresh_all(self) -> None:
        for t in self.pages:
            t.reload()
        self.refresh_header()

    def _on_nav(self, idx: int) -> None:
        if idx < 0:
            return
        _, _, title, sub = PAGES[idx]
        self.title.setText(title)
        self.subtitle.setText(sub)
        self.stack.setCurrentIndex(idx)
        w = self.pages[idx]
        if hasattr(w, "reload"):
            w.reload()
        self.refresh_header()

    def _open_template(self, title: str, body: str) -> None:
        self.show_page(self.content_tab)
        self.content_tab.load_draft(title, body)

    def show_page(self, widget: QWidget) -> None:
        self.nav.setCurrentRow(self.pages.index(widget))

    def _tick(self) -> None:
        if self.stack.currentWidget() is self.queue_tab:
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
                "Bạn có thể xác nhận sau trong trang Hàng đợi. Vẫn thoát?")
            if ans != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()
