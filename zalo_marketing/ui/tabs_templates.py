"""Trang Sản phẩm & Mẫu bài: hồ sơ sản phẩm quảng cáo (Tool HanaMedia) và thư viện mẫu."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from ..core.services import Services
from ..core.templates import PROFILE_FIELDS, find_placeholders
from .common import guarded
from .theme import button, card, label

MULTILINE = {"tinh_nang"}


class TemplateEditDialog(QDialog):
    def __init__(self, parent=None, name: str = "", body: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Mẫu bài mới")
        self.resize(560, 480)
        self.name = QLineEdit(name)
        self.name.setPlaceholderText("Tên mẫu, ví dụ: Ưu đãi cuối tuần")
        self.body = QPlainTextEdit(body)
        self.body.setPlaceholderText("Nội dung mẫu. Dùng biến như {ten_san_pham}, {uu_dai}, {link}, {lien_he}…")
        keys = ", ".join("{" + k + "}" for k, _, _ in PROFILE_FIELDS)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.addWidget(label("Mẫu bài mới", "CardTitle"))
        lay.addWidget(label(f"Biến lấy từ hồ sơ sản phẩm: {keys}", "Hint", wrap=True))
        lay.addWidget(self.name)
        lay.addWidget(self.body, 1)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("Hủy", slot=self.reject))
        row.addWidget(button("Lưu mẫu", "primary", self.accept))
        lay.addLayout(row)


class TemplatesTab(QWidget):
    changed = Signal()
    use_template = Signal(str, str)  # (tiêu đề, nội dung) → mở ở trang Soạn nội dung

    def __init__(self, svc: Services, operator, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.operator = operator

        # ---- Hồ sơ sản phẩm
        self.fields: dict[str, QLineEdit | QPlainTextEdit] = {}
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)
        for key, title, hint in PROFILE_FIELDS:
            if key in MULTILINE:
                w = QPlainTextEdit()
                w.setPlaceholderText(hint)
                w.setFixedHeight(96)
                w.textChanged.connect(self._update_preview)
            else:
                w = QLineEdit()
                w.setPlaceholderText(hint)
                w.textChanged.connect(self._update_preview)
            self.fields[key] = w
            form.addRow(title, w)

        prof, pl = card("Sản phẩm quảng cáo",
                        "Thông tin này được tự động điền vào mẫu bài. Trường nào để trống thì dòng tương ứng "
                        "trong mẫu sẽ được bỏ qua.")
        inner = QWidget()
        inner.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        pl.addWidget(scroll, 1)
        b = QHBoxLayout()
        b.addStretch()
        b.addWidget(button("Lưu thông tin sản phẩm", "primary", self.save_profile))
        pl.addLayout(b)

        # ---- Thư viện mẫu
        self.tpl_list = QListWidget()
        self.tpl_list.setObjectName("Checklist")
        self.tpl_list.setFixedHeight(190)
        self.tpl_list.currentRowChanged.connect(self._update_preview)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.warn = label("", "InfoBox", wrap=True)

        lib, ll = card("Thư viện mẫu bài", "Chọn mẫu để xem trước với thông tin sản phẩm của bạn.")
        ll.addWidget(self.tpl_list)
        ll.addWidget(label("XEM TRƯỚC", "StatLabel"))
        ll.addWidget(self.preview, 1)
        ll.addWidget(self.warn)
        r = QHBoxLayout()
        self.btn_delete = button("Xóa mẫu", "ghost", self.delete_template)
        r.addWidget(self.btn_delete)
        r.addWidget(button("+  Thêm mẫu", slot=self.add_template))
        r.addStretch()
        r.addWidget(button("Tạo bài từ mẫu  →", "primary", self.create_post))
        ll.addLayout(r)

        split = QSplitter()
        split.setHandleWidth(16)
        split.addWidget(prof)
        split.addWidget(lib)
        split.setSizes([500, 580])
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(split)
        self.reload()

    # ------------------------------------------------------------------ data
    def reload(self, *_):
        p = self.svc.templates.profile()
        for key, w in self.fields.items():
            w.blockSignals(True)
            (w.setPlainText if isinstance(w, QPlainTextEdit) else w.setText)(p.get(key, ""))
            w.blockSignals(False)
        cur = self.tpl_list.currentItem().data(Qt.UserRole) if self.tpl_list.currentItem() else None
        self.tpl_list.blockSignals(True)
        self.tpl_list.clear()
        for t in self.svc.templates.list():
            it = QListWidgetItem(("📌  " if t.builtin else "📝  ") + t.name)
            it.setData(Qt.UserRole, t.id)
            self.tpl_list.addItem(it)
            if t.id == cur:
                self.tpl_list.setCurrentItem(it)
        self.tpl_list.blockSignals(False)
        if self.tpl_list.currentRow() < 0 and self.tpl_list.count():
            self.tpl_list.setCurrentRow(0)
        self._update_preview()

    def _form_profile(self) -> dict[str, str]:
        return {k: (w.toPlainText() if isinstance(w, QPlainTextEdit) else w.text()) for k, w in self.fields.items()}

    def _current_template_id(self) -> int | None:
        it = self.tpl_list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _update_preview(self, *_):
        from ..core.templates import DEFAULT_PROFILE, render
        tid = self._current_template_id()
        self.btn_delete.setEnabled(tid is not None)
        if tid is None:
            self.preview.clear()
            self.warn.setVisible(False)
            return
        t = self.svc.templates.get(tid)
        text = render(t.body, {**DEFAULT_PROFILE, **self._form_profile()})
        self.preview.setPlainText(text)
        missing = find_placeholders(text)
        self.warn.setVisible(bool(missing))
        if missing:
            self.warn.setText("Còn cần tự điền khi soạn: " + ", ".join("{" + m + "}" for m in missing))

    # --------------------------------------------------------------- actions
    @guarded
    def save_profile(self):
        self.svc.templates.save_profile(self.operator(), self._form_profile())
        QMessageBox.information(self, "Sản phẩm", "Đã lưu thông tin sản phẩm.")
        self.changed.emit()

    @guarded
    def create_post(self):
        tid = self._current_template_id()
        if tid is None:
            return
        self.svc.templates.save_profile(self.operator(), self._form_profile())
        title, body = self.svc.templates.apply(tid)
        self.use_template.emit(title, body)

    @guarded
    def add_template(self):
        dlg = TemplateEditDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        self.svc.templates.add(dlg.name.text(), dlg.body.toPlainText(), self.operator())
        self.reload()
        self.tpl_list.setCurrentRow(self.tpl_list.count() - 1)

    @guarded
    def delete_template(self):
        tid = self._current_template_id()
        if tid is None:
            return
        t = self.svc.templates.get(tid)
        if QMessageBox.question(self, "Xóa mẫu", f"Xóa mẫu '{t.name}'?") != QMessageBox.Yes:
            return
        self.svc.templates.delete(tid, self.operator())
        self.reload()
