"""Tab Lịch sử & Nhật ký kiểm toán, tab Cài đặt."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLineEdit, QMessageBox,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ..core.services import Services
from .theme import button, card, label
from .common import CHANNEL_VI, JOB_STATUS_VI, fill_table, fmt_ts, guarded, make_table

ACTION_VI = {
    "post.create": "Tạo nội dung", "post.edit": "Sửa nội dung (phiên bản mới)", "post.rename": "Đổi tiêu đề",
    "post.submit": "Gửi duyệt", "post.approve": "Duyệt", "post.reject": "Từ chối", "post.revoke": "Thu hồi duyệt",
    "post.archive": "Lưu trữ nội dung", "group.create": "Thêm nhóm", "group.update": "Sửa nhóm",
    "job.enqueue": "Xếp lệnh", "job.enqueue_rejected": "Từ chối xếp lệnh", "job.cancel": "Hủy lệnh",
    "job.handoff": "Bàn giao thủ công", "job.confirm_sent": "Xác nhận đã gửi", "job.skip": "Bỏ qua",
    "job.return_to_queue": "Trả lại hàng đợi", "job.api_sent": "Gửi API thành công", "job.api_failed": "Gửi API lỗi",
    "gate.block": "Safety Gate chặn", "gate.unblock": "Safety Gate mở chặn",
    "gate.deny_handoff": "Từ chối bàn giao", "gate.deny_api": "Từ chối gửi API",
    "kill_switch.on": "BẬT dừng khẩn cấp", "kill_switch.off": "TẮT dừng khẩn cấp",
    "settings.update": "Đổi cài đặt",
    "profile.update": "Sửa thông tin sản phẩm", "template.create": "Thêm mẫu", "template.delete": "Xóa mẫu",
}


class HistoryTab(QWidget):
    def __init__(self, svc: Services, parent=None):
        super().__init__(parent)
        self.svc = svc

        self.jobs = make_table(["#", "Nội dung", "Phiên bản", "Nhóm", "Kênh", "Trạng thái", "Bàn giao",
                                "Hoàn tất", "Người xác nhận", "Ghi chú"], badge_cols=(4, 5))
        self.audit = make_table(["#", "Thời gian", "Người thực hiện", "Hành động", "Đối tượng", "Lý do", "Chi tiết"])

        self.action_filter = QComboBox()
        self.action_filter.setMinimumWidth(240)
        self.action_filter.addItem("Tất cả hành động", None)
        for k, v in ACTION_VI.items():
            self.action_filter.addItem(v, k)
        self.action_filter.currentIndexChanged.connect(self.reload)
        jobs_card, jl = card()
        jl.addWidget(self.jobs)

        audit_card, al = card()
        row = QHBoxLayout()
        row.addWidget(self.action_filter)
        row.addStretch()
        row.addWidget(button("⟳  Làm mới", "ghost", self.reload))
        row.addWidget(button("Xuất CSV", "primary", self.export))
        al.addLayout(row)
        al.addWidget(self.audit)

        tabs = QTabWidget()
        tabs.addTab(jobs_card, "Lịch sử đăng")
        tabs.addTab(audit_card, "Nhật ký kiểm toán")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(tabs)
        self.reload()

    def reload(self, *_):
        rows = self.svc.dispatcher.history()
        fill_table(self.jobs, [[j["id"], j["post_title"], f"v{j['post_version']}", j["group_name"],
                                CHANNEL_VI[j["channel"]], JOB_STATUS_VI[j["status"]], fmt_ts(j["handed_off_at"]),
                                fmt_ts(j["completed_at"]), j["completed_by"] or "", j["block_reason"] or ""]
                               for j in rows], [j["id"] for j in rows])
        entries = self.svc.audit.list(limit=1000, action=self.action_filter.currentData())
        fill_table(self.audit, [[e.id, fmt_ts(e.ts), e.actor, ACTION_VI.get(e.action, e.action),
                                 f"{e.entity} #{e.entity_id}" if e.entity_id is not None else e.entity,
                                 e.reason or "", _short(e.detail)] for e in entries], [e.id for e in entries])

    @guarded
    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Xuất nhật ký", "audit_log.csv", "CSV (*.csv)")
        if path:
            n = self.svc.audit.export_csv(path)
            QMessageBox.information(self, "Xuất nhật ký", f"Đã xuất {n} dòng.")


def _short(detail: str | None) -> str:
    if not detail:
        return ""
    try:
        d = json.loads(detail)
    except ValueError:
        return detail
    return ", ".join(f"{k}={v}" for k, v in d.items())[:200]


class SettingsTab(QWidget):
    changed = Signal()

    def __init__(self, svc: Services, operator, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.operator = operator

        self.operator_name = QLineEdit()
        self.min_interval = QSpinBox(maximum=24 * 60, suffix=" phút")
        self.daily_limit = QSpinBox(maximum=1000, suffix=" bài")
        self.per_group = QSpinBox(maximum=100, suffix=" bài")
        self.dedupe = QSpinBox(maximum=365, suffix=" ngày")
        self.quiet_start = QLineEdit()
        self.quiet_start.setInputMask("99:99;_")
        self.quiet_end = QLineEdit()
        self.quiet_end.setInputMask("99:99;_")
        self.four_eyes = QCheckBox("Người duyệt phải khác người soạn (nguyên tắc 4 mắt)")
        self.api_enabled = QCheckBox("Bật kênh Official API")
        self.auto_stop = QSpinBox(maximum=100, suffix=" lỗi")
        self.auto_update = QCheckBox("Tự kiểm tra bản cập nhật khi mở phần mềm")

        def section(title, subtitle, rows):
            frame, lay = card(title, subtitle)
            form = QFormLayout()
            form.setVerticalSpacing(10)
            form.setHorizontalSpacing(16)
            for text, w in rows:
                form.addRow(text, w)
            lay.addLayout(form)
            return frame

        q = QWidget()
        ql = QHBoxLayout(q)
        ql.setContentsMargins(0, 0, 0, 0)
        ql.addWidget(self.quiet_start)
        ql.addWidget(label("đến"))
        ql.addWidget(self.quiet_end)
        ql.addStretch()
        for w in (self.quiet_start, self.quiet_end):
            w.setFixedWidth(80)
        for w in (self.min_interval, self.daily_limit, self.per_group, self.dedupe, self.auto_stop):
            w.setFixedWidth(140)
            w.setButtonSymbols(QSpinBox.NoButtons)
            w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        api_state = "đã cấu hình" if svc.dispatcher.api_publisher.is_configured() else "chưa cấu hình"
        general = section("Chung", None, [("Tên người dùng", self.operator_name), ("", self.four_eyes),
                                          ("", self.auto_update)])
        limits = section("Giới hạn an toàn", "Đặt 0 để tắt một giới hạn. Khung giờ yên lặng để trống = tắt.", [
            ("Khoảng cách tối thiểu / nhóm", self.min_interval),
            ("Tối đa mỗi nhóm / 24 giờ", self.per_group),
            ("Tối đa tất cả nhóm / 24 giờ", self.daily_limit),
            ("Không gửi lại cùng nội dung trong", self.dedupe),
            ("Khung giờ yên lặng", q),
        ])
        api = section("Official API",
                      f"Adapter: <b>{api_state}</b> ({svc.dispatcher.api_publisher.name}). "
                      "Chỉ bật khi Zalo đã xác nhận quyền truy cập nhóm.",
                      [("", self.api_enabled), ("Tự dừng khẩn cấp sau", self.auto_stop)])

        grid = QGridLayout()
        grid.setSpacing(16)
        grid.addWidget(general, 0, 0)
        grid.addWidget(api, 1, 0)
        grid.addWidget(limits, 0, 1, 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(grid)
        b = QHBoxLayout()
        b.addStretch()
        b.addWidget(button("Lưu cài đặt", "primary", self.save))
        lay.addLayout(b)
        lay.addStretch()
        self.reload()

    def reload(self, *_):
        s = self.svc.db.all_settings()
        self.operator_name.setText(s["operator_name"])
        self.min_interval.setValue(int(s["min_interval_minutes"]))
        self.daily_limit.setValue(int(s["daily_limit"]))
        self.per_group.setValue(int(s["per_group_daily_limit"]))
        self.dedupe.setValue(int(s["dedupe_days"]))
        self.quiet_start.setText(s["quiet_start"] or "")
        self.quiet_end.setText(s["quiet_end"] or "")
        self.four_eyes.setChecked(bool(s["require_different_approver"]))
        self.api_enabled.setChecked(bool(s["official_api_enabled"]))
        self.auto_stop.setValue(int(s["auto_stop_after_failures"]))
        self.auto_update.setChecked(bool(s["auto_check_updates"]))

    @guarded
    def save(self):
        def hhmm(w: QLineEdit) -> str:
            t = w.text().strip()
            return "" if t in ("", ":") else t
        from ..core.safety import _parse_hhmm
        for w in (self.quiet_start, self.quiet_end):
            if hhmm(w) and _parse_hhmm(hhmm(w)) is None:
                QMessageBox.warning(self, "Cài đặt", f"Giờ không hợp lệ: {w.text()} (định dạng HH:MM).")
                return
        name = self.operator_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Cài đặt", "Tên người dùng không được để trống.")
            return
        self.svc.dispatcher.update_settings(
            name,
            operator_name=name,
            min_interval_minutes=self.min_interval.value(),
            daily_limit=self.daily_limit.value(),
            per_group_daily_limit=self.per_group.value(),
            dedupe_days=self.dedupe.value(),
            quiet_start=hhmm(self.quiet_start),
            quiet_end=hhmm(self.quiet_end),
            require_different_approver=self.four_eyes.isChecked(),
            official_api_enabled=self.api_enabled.isChecked(),
            auto_stop_after_failures=self.auto_stop.value(),
            auto_check_updates=self.auto_update.isChecked(),
        )
        QMessageBox.information(self, "Cài đặt", "Đã lưu.")
        self.changed.emit()
