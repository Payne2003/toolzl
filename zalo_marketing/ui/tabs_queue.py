"""Tab Hàng đợi: xếp lệnh, kiểm tra Safety Gate, bàn giao thủ công / gửi qua Official API."""

from __future__ import annotations

from PySide6.QtCore import QDateTime, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout,
    QWidget,
)

from ..core.errors import GateBlocked
from ..core.models import Channel, JobStatus, PostStatus
from ..core.publishers import HandoffPackage
from ..core.services import Services
from .common import CHANNEL_VI, JOB_STATUS_VI, fill_table, fmt_ts, guarded, make_table, selected_id, show_error

ACTIVE = (JobStatus.QUEUED.value, JobStatus.BLOCKED.value, JobStatus.HANDED_OFF.value)


class HandoffDialog(QDialog):
    """Hiển thị sau khi đã chép nội dung & mở Zalo. Người dùng tự gửi rồi xác nhận kết quả."""

    SENT, RETURN, SKIP = 1, 2, 3

    def __init__(self, pkg: HandoffPackage, parent=None):
        super().__init__(parent)
        self.pkg = pkg
        self.choice = self.RETURN
        self.setWindowTitle(f"Bàn giao thủ công — {pkg.group_name}")
        self.resize(560, 460)

        steps = QLabel(
            "<b>Nội dung đã được chép vào clipboard.</b><br>"
            + ("Zalo đã được mở tới nhóm. " if pkg.group_link else "Nhóm chưa có link — hãy tự mở nhóm trong Zalo. ")
            + "<ol><li>Kiểm tra đúng nhóm <b>{}</b>.</li>"
              "<li>Dán (Ctrl+V), đọc lại nội dung.</li>"
              "<li>Tự bấm <b>Gửi</b> trong Zalo.</li>"
              "<li>Quay lại đây và xác nhận kết quả.</li></ol>".format(pkg.group_name)
        )
        steps.setWordWrap(True)
        text = QPlainTextEdit(pkg.text)
        text.setReadOnly(True)

        btn_copy = QPushButton("📋 Chép lại")
        btn_copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(pkg.text))
        btn_open = QPushButton("🔗 Mở lại nhóm")
        btn_open.setEnabled(bool(pkg.group_link))
        btn_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(pkg.group_link)))

        box = QDialogButtonBox()
        b_sent = box.addButton("✅ Tôi đã gửi", QDialogButtonBox.AcceptRole)
        b_ret = box.addButton("↩ Chưa gửi — trả lại hàng đợi", QDialogButtonBox.RejectRole)
        b_skip = box.addButton("⏭ Bỏ qua lệnh này", QDialogButtonBox.DestructiveRole)
        b_sent.clicked.connect(lambda: self._done(self.SENT))
        b_ret.clicked.connect(lambda: self._done(self.RETURN))
        b_skip.clicked.connect(lambda: self._done(self.SKIP))

        lay = QVBoxLayout(self)
        lay.addWidget(steps)
        lay.addWidget(text, 1)
        row = QHBoxLayout()
        row.addWidget(btn_copy)
        row.addWidget(btn_open)
        row.addStretch()
        lay.addLayout(row)
        lay.addWidget(box)

    def _done(self, choice: int) -> None:
        self.choice = choice
        self.accept()

    def reject(self) -> None:  # Esc / đóng cửa sổ = chưa gửi
        self.choice = self.RETURN
        super().reject()


class QueueTab(QWidget):
    changed = Signal()

    def __init__(self, svc: Services, operator, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.operator = operator

        # --- Khu xếp lệnh
        self.post_combo = QComboBox()
        self.group_list = QListWidget()
        self.group_list.setMaximumHeight(160)
        self.channel = QComboBox()
        self.channel.addItem(CHANNEL_VI["manual"], Channel.MANUAL.value)
        self.channel.addItem(CHANNEL_VI["api"], Channel.OFFICIAL_API.value)
        self.use_schedule = QCheckBox("Hẹn giờ:")
        self.schedule = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.schedule.setCalendarPopup(True)
        self.schedule.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.schedule.setEnabled(False)
        self.use_schedule.toggled.connect(self.schedule.setEnabled)
        btn_enqueue = QPushButton("➕ Xếp lệnh")
        btn_enqueue.clicked.connect(self.enqueue)

        enq = QGroupBox("Xếp lệnh đăng (chỉ nội dung đã duyệt · chỉ nhóm được phép)")
        el = QVBoxLayout(enq)
        el.addWidget(QLabel("Nội dung:"))
        el.addWidget(self.post_combo)
        el.addWidget(QLabel("Nhóm:"))
        el.addWidget(self.group_list)
        r = QHBoxLayout()
        r.addWidget(QLabel("Kênh:"))
        r.addWidget(self.channel)
        r.addWidget(self.use_schedule)
        r.addWidget(self.schedule)
        r.addStretch()
        r.addWidget(btn_enqueue)
        el.addLayout(r)

        # --- Bảng lệnh
        self.table = make_table(["#", "Nội dung", "Nhóm", "Kênh", "Trạng thái", "Hẹn giờ", "Lý do / ghi chú"])
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.doubleClicked.connect(self.check_selected)

        self.btn_next = QPushButton("▶ Bàn giao lệnh tiếp theo")
        self.btn_next.setStyleSheet("font-weight: bold; padding: 6px 12px;")
        self.btn_next.clicked.connect(self.handoff_next)
        self.btn_handoff = QPushButton("📋 Bàn giao lệnh đã chọn")
        self.btn_handoff.clicked.connect(self.handoff_selected)
        self.btn_resume = QPushButton("⏯ Xác nhận lệnh đã bàn giao")
        self.btn_resume.clicked.connect(self.resume_handed_off)
        self.btn_api = QPushButton("⚡ Gửi qua Official API")
        self.btn_api.clicked.connect(self.send_api)
        self.btn_check = QPushButton("🔍 Kiểm tra Safety Gate")
        self.btn_check.clicked.connect(self.check_selected)
        self.btn_cancel = QPushButton("🗑 Hủy lệnh")
        self.btn_cancel.clicked.connect(self.cancel)
        btn_refresh = QPushButton("⟳ Đánh giá lại")
        btn_refresh.clicked.connect(self.reload)

        actions = QHBoxLayout()
        for b in (self.btn_next, self.btn_handoff, self.btn_resume, self.btn_api, self.btn_check,
                  self.btn_cancel, btn_refresh):
            actions.addWidget(b)
        actions.addStretch()

        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addLayout(actions)
        bl.addWidget(self.table)

        split = QSplitter(Qt.Vertical)
        split.addWidget(enq)
        split.addWidget(bottom)
        split.setSizes([260, 440])
        QVBoxLayout(self).addWidget(split)
        self.reload()

    # ----------------------------------------------------------------- data
    def reload(self, *_):
        cur_post = self.post_combo.currentData()
        self.post_combo.clear()
        for p in self.svc.posts.list(PostStatus.APPROVED):
            self.post_combo.addItem(f"#{p.id} · {p.title} (v{p.version})", p.id)
        if cur_post is not None:
            idx = self.post_combo.findData(cur_post)
            if idx >= 0:
                self.post_combo.setCurrentIndex(idx)

        checked = {self.group_list.item(i).data(Qt.UserRole) for i in range(self.group_list.count())
                   if self.group_list.item(i).checkState() == Qt.Checked}
        self.group_list.clear()
        for g in self.svc.groups.list():
            usable = g.allowed and g.can_post and g.status.value == "active"
            label = g.name + ("" if usable else "  (chưa đủ điều kiện)")
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, g.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if g.id in checked else Qt.Unchecked)
            if not g.allowed:
                it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
            self.group_list.addItem(it)

        try:
            self.svc.dispatcher.refresh(self.operator() or "system")
        except Exception as e:  # noqa: BLE001
            show_error(self, e)
        jobs = self.svc.dispatcher.list(ACTIVE)
        fill_table(
            self.table,
            [[j["id"], j["post_title"], j["group_name"], CHANNEL_VI[j["channel"]], JOB_STATUS_VI[j["status"]],
              fmt_ts(j["scheduled_at"]), j["block_reason"] or ""] for j in jobs],
            [j["id"] for j in jobs],
        )
        self._update_buttons()

    def _selected_job(self):
        jid = selected_id(self.table)
        return self.svc.dispatcher.get(jid) if jid is not None else None

    def _update_buttons(self):
        job = self._selected_job()
        st = job.status if job else None
        manual = job is not None and job.channel == Channel.MANUAL
        self.btn_handoff.setEnabled(manual and st in (JobStatus.QUEUED, JobStatus.BLOCKED))
        self.btn_resume.setEnabled(st == JobStatus.HANDED_OFF)
        self.btn_api.setEnabled(job is not None and job.channel == Channel.OFFICIAL_API
                                and st in (JobStatus.QUEUED, JobStatus.BLOCKED))
        self.btn_check.setEnabled(job is not None and st in (JobStatus.QUEUED, JobStatus.BLOCKED))
        self.btn_cancel.setEnabled(st in (JobStatus.QUEUED, JobStatus.BLOCKED))

    # -------------------------------------------------------------- actions
    @guarded
    def enqueue(self):
        pid = self.post_combo.currentData()
        if pid is None:
            QMessageBox.information(self, "Xếp lệnh", "Chưa có nội dung nào đã được duyệt.")
            return
        gids = [self.group_list.item(i).data(Qt.UserRole) for i in range(self.group_list.count())
                if self.group_list.item(i).checkState() == Qt.Checked]
        sched = self.schedule.dateTime().toPython().astimezone() if self.use_schedule.isChecked() else None
        res = self.svc.dispatcher.enqueue(pid, gids, self.operator(), Channel(self.channel.currentData()), sched)
        msg = f"Đã tạo {len(res.created)} lệnh."
        if res.skipped:
            msg += "\n\nKhông tạo lệnh cho:\n• " + "\n• ".join(why for _, why in res.skipped)
        QMessageBox.information(self, "Xếp lệnh", msg)
        self.reload()
        self.changed.emit()

    @guarded
    def handoff_next(self):
        job = self.svc.dispatcher.next_ready(Channel.MANUAL)
        if job is None:
            self.reload()
            QMessageBox.information(self, "Hàng đợi",
                                    "Không có lệnh thủ công nào đủ điều kiện lúc này.\n"
                                    "Xem cột 'Lý do' để biết lệnh nào đang bị chặn và vì sao.")
            return
        self._handoff(job.id)

    @guarded
    def handoff_selected(self):
        job = self._selected_job()
        if job:
            self._handoff(job.id)

    def _handoff(self, job_id: int) -> None:
        actor = self.operator()
        try:
            pkg = self.svc.dispatcher.handoff(job_id, actor)
        except GateBlocked as e:
            self.reload()
            show_error(self, e)
            return
        QGuiApplication.clipboard().setText(pkg.text)
        if pkg.group_link:
            QDesktopServices.openUrl(QUrl(pkg.group_link))
        self._confirm(pkg)

    def _confirm(self, pkg: HandoffPackage) -> None:
        actor = self.operator()
        dlg = HandoffDialog(pkg, self)
        dlg.exec()
        if dlg.choice == HandoffDialog.SENT:
            self.svc.dispatcher.confirm_sent(pkg.job_id, actor)
        elif dlg.choice == HandoffDialog.SKIP:
            reason, ok = QInputDialog.getText(self, "Bỏ qua lệnh", "Lý do bỏ qua:")
            if ok and reason.strip():
                self.svc.dispatcher.skip(pkg.job_id, actor, reason)
            else:
                self.svc.dispatcher.return_to_queue(pkg.job_id, actor)
        else:
            self.svc.dispatcher.return_to_queue(pkg.job_id, actor)
        self.reload()
        self.changed.emit()

    @guarded
    def resume_handed_off(self):
        """Mở lại hộp xác nhận cho lệnh đã bàn giao (ví dụ sau khi lỡ đóng phần mềm)."""
        job = self._selected_job()
        if job is None or job.status != JobStatus.HANDED_OFF:
            return
        post = self.svc.posts.get(job.post_id)
        group = self.svc.groups.get(job.group_id)
        body = post.body
        if post.content_hash != job.content_hash:
            v = next((v for v in self.svc.posts.versions(post.id) if v["content_hash"] == job.content_hash), None)
            body = v["body"] if v else body
        self._confirm(HandoffPackage(job.id, group.name, group.link, body))

    @guarded
    def send_api(self):
        job = self._selected_job()
        if job is None:
            return
        if QMessageBox.question(self, "Official API", "Gửi lệnh này qua Official API?") != QMessageBox.Yes:
            return
        try:
            res = self.svc.dispatcher.send_via_api(job.id, self.operator())
        finally:
            self.reload()
            self.changed.emit()
        if res.status == JobStatus.SENT:
            QMessageBox.information(self, "Official API", "Đã gửi thành công.")
        else:
            QMessageBox.warning(self, "Official API", f"Gửi thất bại: {res.block_reason}")

    @guarded
    def check_selected(self):
        job = self._selected_job()
        if job is None:
            return
        res = self.svc.dispatcher.check(job.id)
        if res.ok:
            QMessageBox.information(self, "Safety Gate", f"Lệnh #{job.id} đủ điều kiện đăng.")
        else:
            QMessageBox.warning(self, "Safety Gate", f"Lệnh #{job.id} chưa đủ điều kiện:\n\n• "
                                + "\n• ".join(res.reasons))

    @guarded
    def cancel(self):
        job = self._selected_job()
        if job is None:
            return
        reason, ok = QInputDialog.getText(self, "Hủy lệnh", "Lý do hủy:", text="Người dùng hủy")
        if not ok:
            return
        self.svc.dispatcher.cancel(job.id, self.operator(), reason.strip() or "Người dùng hủy")
        self.reload()
        self.changed.emit()
