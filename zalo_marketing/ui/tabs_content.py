"""Tab Soạn nội dung & tab Phê duyệt."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLineEdit, QMessageBox, QPlainTextEdit, QSplitter, QVBoxLayout, QWidget,
)

from ..core.approval import MAX_BODY_CHARS
from ..core.models import PostStatus, content_hash
from ..core.services import Services
from .common import POST_STATUS_VI, fill_table, fmt_ts, guarded, make_table, selected_id
from .theme import button, card, label


class ContentTab(QWidget):
    changed = Signal()

    def __init__(self, svc: Services, operator, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.operator = operator  # callable trả về tên người dùng hiện tại
        self.current_id: int | None = None

        self.table = make_table(["#", "Tiêu đề", "Trạng thái", "Phiên bản", "Cập nhật"], badge_cols=(2,))
        self.table.itemSelectionChanged.connect(self._load_selected)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Nhãn nội bộ, ví dụ: Khuyến mãi tháng 11")
        self.body_edit = QPlainTextEdit()
        self.body_edit.setPlaceholderText("Nội dung sẽ được chép để bạn dán vào nhóm Zalo…")
        self.body_edit.textChanged.connect(self._update_counter)
        self.counter = label("", "Muted")
        self.status_label = label("", "InfoBox", wrap=True)

        self.btn_save = button("Lưu nháp", slot=self.save)
        self.btn_submit = button("Gửi duyệt  →", "primary", self.submit)
        self.btn_archive = button("Lưu trữ", "ghost", self.archive)

        # Danh sách nội dung
        left, ll = card()
        head = QHBoxLayout()
        head.addWidget(label("Nội dung của bạn", "CardTitle"))
        head.addStretch()
        head.addWidget(button("+  Nội dung mới", "primary", self.new_post))
        ll.addLayout(head)
        ll.addWidget(self.table, 1)

        # Trình soạn thảo
        right, rl = card()
        self.editor_title = label("Bản nháp mới", "CardTitle")
        rl.addWidget(self.editor_title)
        rl.addWidget(label("TIÊU ĐỀ", "StatLabel"))
        rl.addWidget(self.title_edit)
        row = QHBoxLayout()
        row.addWidget(label("NỘI DUNG GỬI VÀO NHÓM", "StatLabel"))
        row.addStretch()
        row.addWidget(self.counter)
        rl.addLayout(row)
        rl.addWidget(self.body_edit, 1)
        rl.addWidget(self.status_label)
        btns = QHBoxLayout()
        btns.addWidget(self.btn_archive)
        btns.addStretch()
        btns.addWidget(self.btn_save)
        btns.addWidget(self.btn_submit)
        rl.addLayout(btns)

        split = QSplitter()
        split.setHandleWidth(16)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([520, 560])
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(split)

        self.reload()
        self.new_post()

    def reload(self) -> None:
        posts = self.svc.posts.list()
        fill_table(
            self.table,
            [[p.id, p.title, POST_STATUS_VI[p.status.value], f"v{p.version}", fmt_ts(p.updated_at)] for p in posts],
            [p.id for p in posts],
        )
        if self.current_id is not None:
            self._show(self.current_id)

    def _update_counter(self) -> None:
        n = len(self.body_edit.toPlainText())
        self.counter.setText(f"{n}/{MAX_BODY_CHARS} ký tự")

    @guarded
    def _load_selected(self):
        pid = selected_id(self.table)
        if pid is not None and pid != self.current_id:
            self.current_id = pid
            self._show(pid)

    def _show(self, pid: int) -> None:
        p = self.svc.posts.get(pid)
        self.title_edit.setText(p.title)
        if self.body_edit.toPlainText() != p.body:
            self.body_edit.setPlainText(p.body)
        self.editor_title.setText(f"Chỉnh sửa #{p.id} · v{p.version}")
        info = f"<b>{POST_STATUS_VI[p.status.value]}</b> · v{p.version} · soạn bởi {p.author}"
        if p.status == PostStatus.APPROVED:
            info += (f"<br>🔒 Duyệt bởi <b>{p.approved_by}</b> lúc {fmt_ts(p.approved_at)}. "
                     "Nội dung đã khóa — nếu sửa, phần mềm sẽ tạo phiên bản mới và cần duyệt lại.")
        if p.review_note:
            info += f"<br>Ghi chú duyệt: <i>{p.review_note}</i>"
        self.status_label.setText(info)
        self.btn_submit.setEnabled(p.status in (PostStatus.DRAFT, PostStatus.REJECTED))
        self.btn_archive.setEnabled(p.status != PostStatus.ARCHIVED)

    @guarded
    def new_post(self):
        self.current_id = None
        self.table.clearSelection()
        self.title_edit.clear()
        self.body_edit.clear()
        self.editor_title.setText("Bản nháp mới")
        self.status_label.setText("Bản nháp mới — chưa lưu. Lưu nháp rồi bấm <b>Gửi duyệt</b> để chuyển cho người duyệt.")
        self.btn_submit.setEnabled(False)
        self.btn_archive.setEnabled(False)

    @guarded
    def save(self):
        self._do_save()

    def _do_save(self) -> bool:
        """Lưu nội dung; trả về False nếu người dùng hủy. Ném lỗi nghiệp vụ nếu không hợp lệ."""
        title, body = self.title_edit.text(), self.body_edit.toPlainText()
        if self.current_id is None:
            p = self.svc.posts.create(title, body, self.operator())
        else:
            old = self.svc.posts.get(self.current_id)
            if old.status == PostStatus.APPROVED:
                if content_hash(body) != old.content_hash:
                    ok = QMessageBox.question(
                        self, "Nội dung đã duyệt",
                        "Nội dung này đã được duyệt và đang khóa.\n"
                        "Lưu thay đổi sẽ tạo phiên bản mới, hủy phê duyệt và hủy các lệnh đăng đang chờ.\n\n"
                        "Tiếp tục?")
                    if ok != QMessageBox.Yes:
                        return False
            p = self.svc.posts.edit(self.current_id, title, body, self.operator())
        self.current_id = p.id
        self.reload()
        self.changed.emit()
        return True

    @guarded
    def submit(self):
        if self.current_id is None or not self._do_save():
            return
        self.svc.posts.submit(self.current_id, self.operator())
        self.reload()
        self.changed.emit()

    @guarded
    def archive(self):
        if self.current_id is None:
            return
        if QMessageBox.question(self, "Lưu trữ", "Lưu trữ nội dung này? Các lệnh đang chờ sẽ bị hủy.") \
                != QMessageBox.Yes:
            return
        self.svc.posts.archive(self.current_id, self.operator())
        self.new_post()
        self.reload()
        self.changed.emit()


class ApprovalTab(QWidget):
    changed = Signal()

    def __init__(self, svc: Services, operator, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.operator = operator
        self.viewed_hash: str | None = None

        self.table = make_table(["#", "Tiêu đề", "Trạng thái", "Phiên bản", "Người soạn", "Cập nhật"],
                                badge_cols=(2,))
        self.table.itemSelectionChanged.connect(self._load_selected)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.meta = label("", "InfoBox", wrap=True)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Ghi chú cho người soạn (bắt buộc khi từ chối / thu hồi)")

        self.btn_approve = button("✓  Duyệt && khóa phiên bản", "success", self.approve)
        self.btn_reject = button("Từ chối", "danger", self.reject)
        self.btn_revoke = button("Thu hồi phê duyệt", slot=self.revoke)

        left, ll = card("Chờ duyệt & đã duyệt")
        ll.addWidget(self.table, 1)

        right, rl = card("Xem trước")
        rl.addWidget(self.meta)
        rl.addWidget(label("NỘI DUNG — ĐÚNG BẢN SẼ ĐƯỢC GỬI", "StatLabel"))
        rl.addWidget(self.preview, 1)
        rl.addWidget(label("GHI CHÚ", "StatLabel"))
        rl.addWidget(self.note)
        b = QHBoxLayout()
        b.addWidget(self.btn_revoke)
        b.addStretch()
        b.addWidget(self.btn_reject)
        b.addWidget(self.btn_approve)
        rl.addLayout(b)

        split = QSplitter()
        split.setHandleWidth(16)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([560, 520])
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(split)
        self.reload()

    def reload(self) -> None:
        posts = self.svc.posts.list(PostStatus.PENDING) + self.svc.posts.list(PostStatus.APPROVED)
        fill_table(
            self.table,
            [[p.id, p.title, POST_STATUS_VI[p.status.value], f"v{p.version}", p.author, fmt_ts(p.updated_at)]
             for p in posts],
            [p.id for p in posts],
        )
        self._load_selected()

    @guarded
    def _load_selected(self):
        pid = selected_id(self.table)
        if pid is None:
            self.preview.clear()
            self.meta.setText("Chọn một nội dung ở danh sách bên trái để xem trước.")
            self.viewed_hash = None
            for w in (self.btn_approve, self.btn_reject, self.btn_revoke):
                w.setEnabled(False)
            return
        p = self.svc.posts.get(pid)
        self.preview.setPlainText(p.body)
        self.viewed_hash = p.content_hash
        meta = (f"<b>{p.title}</b> — v{p.version} · {POST_STATUS_VI[p.status.value]} · soạn bởi {p.author}"
                f"<br>Mã phiên bản: <code>{p.content_hash[:12]}</code>")
        if p.approved_by:
            meta += f"<br>Duyệt bởi {p.approved_by} lúc {fmt_ts(p.approved_at)}"
        self.meta.setText(meta)
        self.btn_approve.setEnabled(p.status == PostStatus.PENDING)
        self.btn_reject.setEnabled(p.status == PostStatus.PENDING)
        self.btn_revoke.setEnabled(p.status == PostStatus.APPROVED)

    def _approver(self) -> str | None:
        name, ok = QInputDialog.getText(self, "Người duyệt", "Tên người duyệt:", text=self.operator())
        return name.strip() if ok and name.strip() else None

    @guarded
    def approve(self):
        pid = selected_id(self.table)
        if pid is None:
            return
        name = self._approver()
        if not name:
            return
        self.svc.posts.approve(pid, name, self.note.text(), expected_hash=self.viewed_hash)
        self.note.clear()
        self.reload()
        self.changed.emit()

    @guarded
    def reject(self):
        pid = selected_id(self.table)
        if pid is None:
            return
        name = self._approver()
        if not name:
            return
        self.svc.posts.reject(pid, name, self.note.text())
        self.note.clear()
        self.reload()
        self.changed.emit()

    @guarded
    def revoke(self):
        pid = selected_id(self.table)
        if pid is None:
            return
        self.svc.posts.revoke(pid, self.operator(), self.note.text())
        self.note.clear()
        self.reload()
        self.changed.emit()
