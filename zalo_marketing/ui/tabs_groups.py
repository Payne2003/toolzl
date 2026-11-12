"""Tab Quản lý nhóm."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLineEdit, QPlainTextEdit, QSplitter, QVBoxLayout,
    QWidget,
)

from ..core.models import GroupStatus
from ..core.services import Services
from .common import GROUP_STATUS_VI, fill_table, guarded, make_table, selected_id
from .theme import button, card, label


def _yn(v: bool) -> str:
    return "Có" if v else "Không"


class GroupsTab(QWidget):
    changed = Signal()

    def __init__(self, svc: Services, operator, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.operator = operator
        self.current_id: int | None = None

        self.show_archived = QCheckBox("Hiện nhóm đã lưu trữ")
        self.show_archived.toggled.connect(self.reload)
        self.table = make_table(["#", "Tên nhóm", "Được phép", "Quyền đăng", "Trạng thái", "API", "Link"],
                                badge_cols=(2, 3, 4, 5))
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
        self.notes.setMaximumHeight(80)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow("Tên nhóm", self.name)
        form.addRow("Link mời", self.link)
        form.addRow("Trạng thái", self.status)

        perm, pl = card(margins=12)
        perm.setGraphicsEffect(None)
        pl.addWidget(label("QUYỀN ĐĂNG", "StatLabel"))
        pl.addWidget(self.allowed)
        pl.addWidget(self.can_post)

        api, al = card(margins=12)
        api.setGraphicsEffect(None)
        al.addWidget(label("OFFICIAL API (TÙY CHỌN)", "StatLabel"))
        al.addWidget(self.api_group_id)
        al.addWidget(self.api_verified)

        self.form_title = label("Thêm nhóm mới", "CardTitle")
        hint = label(
            "Chỉ thêm những nhóm bạn là thành viên và được phép đăng bài quảng bá. "
            "Nhóm mới mặc định <b>không được phép</b> cho tới khi bạn tích xác nhận.", "InfoBox", wrap=True)

        right, rl = card()
        rl.addWidget(self.form_title)
        rl.addWidget(hint)
        rl.addLayout(form)
        rl.addWidget(perm)
        rl.addWidget(api)
        rl.addWidget(label("GHI CHÚ", "StatLabel"))
        rl.addWidget(self.notes)
        rl.addStretch()
        b = QHBoxLayout()
        b.addStretch()
        b.addWidget(button("Làm mới form", slot=self.clear_form))
        b.addWidget(button("Lưu nhóm", "primary", self.save))
        rl.addLayout(b)

        left, ll = card()
        head = QHBoxLayout()
        head.addWidget(label("Danh sách nhóm", "CardTitle"))
        head.addStretch()
        head.addWidget(self.show_archived)
        head.addWidget(button("+  Nhóm mới", "primary", self.clear_form))
        ll.addLayout(head)
        ll.addWidget(self.table, 1)

        split = QSplitter()
        split.setHandleWidth(16)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([640, 440])
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(split)
        self.reload()
        self.clear_form()

    def reload(self, *_):
        groups = self.svc.groups.list(include_archived=self.show_archived.isChecked())
        fill_table(
            self.table,
            [[g.id, g.name, _yn(g.allowed), _yn(g.can_post), GROUP_STATUS_VI[g.status.value],
              "Đã xác nhận" if g.api_verified and g.api_group_id else "—", g.link] for g in groups],
            [g.id for g in groups],
        )

    @guarded
    def _load_selected(self):
        gid = selected_id(self.table)
        if gid is None:
            return
        g = self.svc.groups.get(gid)
        self.current_id = gid
        self.form_title.setText(f"Sửa nhóm #{g.id}")
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
        self.form_title.setText("Thêm nhóm mới")
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
