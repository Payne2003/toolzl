"""Tab Quản lý nhóm."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QSplitter, QVBoxLayout, QWidget,
)

from ..core.models import GroupStatus
from ..core.services import Services
from .common import GROUP_STATUS_VI, fill_table, guarded, make_table, selected_id


def _yn(v: bool) -> str:
    return "✔" if v else "✘"


class GroupsTab(QWidget):
    changed = Signal()

    def __init__(self, svc: Services, operator, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.operator = operator
        self.current_id: int | None = None

        self.show_archived = QCheckBox("Hiện nhóm đã lưu trữ")
        self.show_archived.toggled.connect(self.reload)
        self.table = make_table(["#", "Tên nhóm", "Được phép", "Quyền đăng", "Trạng thái", "API", "Link"])
        self.table.itemSelectionChanged.connect(self._load_selected)

        self.name = QLineEdit()
        self.link = QLineEdit()
        self.link.setPlaceholderText("https://zalo.me/g/xxxxxx")
        self.allowed = QCheckBox("Nằm trong danh sách được phép đăng")
        self.can_post = QCheckBox("Tôi đã xác nhận mình có quyền đăng bài trong nhóm này")
        self.status = QComboBox()
        for s in GroupStatus:
            self.status.addItem(GROUP_STATUS_VI[s.value], s.value)
        self.api_group_id = QLineEdit()
        self.api_group_id.setPlaceholderText("Chỉ điền khi Zalo đã cấp quyền truy cập nhóm qua API")
        self.api_verified = QCheckBox("Zalo đã xác nhận quyền truy cập nhóm qua API chính thức")
        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(90)

        form = QFormLayout()
        form.addRow("Tên nhóm:", self.name)
        form.addRow("Link mời:", self.link)
        form.addRow("", self.allowed)
        form.addRow("", self.can_post)
        form.addRow("Trạng thái:", self.status)
        form.addRow("API group ID:", self.api_group_id)
        form.addRow("", self.api_verified)
        form.addRow("Ghi chú:", self.notes)

        btn_new = QPushButton("➕ Nhóm mới")
        btn_new.clicked.connect(self.clear_form)
        btn_save = QPushButton("💾 Lưu nhóm")
        btn_save.clicked.connect(self.save)

        hint = QLabel(
            "Chỉ thêm những nhóm bạn là thành viên và được phép đăng bài quảng bá. "
            "Nhóm mới mặc định <b>không được phép</b> cho tới khi bạn tích xác nhận."
        )
        hint.setWordWrap(True)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(hint)
        rl.addLayout(form)
        b = QHBoxLayout()
        b.addWidget(btn_new)
        b.addWidget(btn_save)
        b.addStretch()
        rl.addLayout(b)
        rl.addStretch()

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(self.show_archived)
        ll.addWidget(self.table)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([560, 460])
        QVBoxLayout(self).addWidget(split)
        self.reload()
        self.clear_form()

    def reload(self, *_):
        groups = self.svc.groups.list(include_archived=self.show_archived.isChecked())
        fill_table(
            self.table,
            [[g.id, g.name, _yn(g.allowed), _yn(g.can_post), GROUP_STATUS_VI[g.status.value],
              "✔ xác nhận" if g.api_verified and g.api_group_id else "—", g.link] for g in groups],
            [g.id for g in groups],
        )

    @guarded
    def _load_selected(self):
        gid = selected_id(self.table)
        if gid is None:
            return
        g = self.svc.groups.get(gid)
        self.current_id = gid
        self.name.setText(g.name)
        self.link.setText(g.link)
        self.allowed.setChecked(g.allowed)
        self.can_post.setChecked(g.can_post)
        self.status.setCurrentIndex(self.status.findData(g.status.value))
        self.api_group_id.setText(g.api_group_id or "")
        self.api_verified.setChecked(g.api_verified)
        self.notes.setPlainText(g.notes)

    @guarded
    def clear_form(self):
        self.current_id = None
        self.table.clearSelection()
        for w in (self.name, self.link, self.api_group_id):
            w.clear()
        self.notes.clear()
        self.allowed.setChecked(False)
        self.can_post.setChecked(False)
        self.api_verified.setChecked(False)
        self.status.setCurrentIndex(0)

    @guarded
    def save(self):
        actor = self.operator()
        if self.current_id is None:
            g = self.svc.groups.add(self.name.text(), actor, link=self.link.text(),
                                    allowed=self.allowed.isChecked(), can_post=self.can_post.isChecked(),
                                    notes=self.notes.toPlainText())
            gid = g.id
            self.svc.groups.update(gid, actor, status=self.status.currentData(),
                                   api_group_id=self.api_group_id.text(),
                                   api_verified=self.api_verified.isChecked())
        else:
            gid = self.current_id
            self.svc.groups.update(
                gid, actor, name=self.name.text(), link=self.link.text(), allowed=self.allowed.isChecked(),
                can_post=self.can_post.isChecked(), status=self.status.currentData(),
                api_group_id=self.api_group_id.text(), api_verified=self.api_verified.isChecked(),
                notes=self.notes.toPlainText(),
            )
        self.current_id = gid
        self.reload()
        self.changed.emit()
