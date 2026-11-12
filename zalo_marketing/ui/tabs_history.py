"""Tab Lịch sử & Nhật ký kiểm toán, tab Cài đặt."""

from __future__ import annotations

import json

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ..core.services import Services
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
}


class HistoryTab(QWidget):
    def __init__(self, svc: Services, parent=None):
        super().__init__(parent)
        self.svc = svc

        self.jobs = make_table(["#", "Nội dung", "Phiên bản", "Nhóm", "Kênh", "Trạng thái", "Bàn giao",
                                "Hoàn tất", "Người xác nhận", "Ghi chú"])
        self.audit = make_table(["#", "Thời gian", "Người thực hiện", "Hành động", "Đối tượng", "Lý do", "Chi tiết"])

        self.action_filter = QComboBox()
        self.action_filter.addItem("Tất cả hành động", None)
        for k, v in ACTION_VI.items():
            self.action_filter.addItem(v, k)
        self.action_filter.currentIndexChanged.connect(self.reload)
        btn_export = QPushButton("⤓ Xuất CSV")
        btn_export.clicked.connect(self.export)
        btn_refresh = QPushButton("⟳ Làm mới")
        btn_refresh.clicked.connect(self.reload)

        audit_page = QWidget()
        al = QVBoxLayout(audit_page)
        row = QHBoxLayout()
        row.addWidget(self.action_filter)
        row.addStretch()
        row.addWidget(btn_refresh)
        row.addWidget(btn_export)
        al.addLayout(row)
        al.addWidget(self.audit)

        tabs = QTabWidget()
        tabs.addTab(self.jobs, "Lịch sử đăng")
        tabs.addTab(audit_page, "Nhật ký kiểm toán")
        QVBoxLayout(self).addWidget(tabs)
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
        self.api_enabled = QCheckBox("Bật kênh Official API (chỉ khi Zalo đã xác nhận quyền truy cập)")
        self.auto_stop = QSpinBox(maximum=100, suffix=" lỗi")

        form = QFormLayout()
        form.addRow("Tên người dùng:", self.operator_name)
        form.addRow("Khoảng cách tối thiểu / nhóm:", self.min_interval)
        form.addRow("Tối đa mỗi nhóm / 24 giờ:", self.per_group)
        form.addRow("Tối đa tất cả nhóm / 24 giờ:", self.daily_limit)
        form.addRow("Không gửi lại cùng nội dung trong:", self.dedupe)
        q = QHBoxLayout()
        q.addWidget(self.quiet_start)
        q.addWidget(QLabel("→"))
        q.addWidget(self.quiet_end)
        q.addStretch()
        form.addRow("Khung giờ yên lặng:", q)
        form.addRow("", self.four_eyes)
        form.addRow("", self.api_enabled)
        form.addRow("Tự dừng khẩn cấp sau:", self.auto_stop)

        api_state = "đã cấu hình" if svc.dispatcher.api_publisher.is_configured() else "chưa cấu hình"
        note = QLabel(f"Adapter Official API: <b>{api_state}</b> ({svc.dispatcher.api_publisher.name}). "
                      "Đặt giá trị 0 để tắt một giới hạn. Khung giờ yên lặng để trống (__:__) = tắt.")
        note.setWordWrap(True)

        btn = QPushButton("💾 Lưu cài đặt")
        btn.clicked.connect(self.save)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(note)
        b = QHBoxLayout()
        b.addWidget(btn)
        b.addStretch()
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
        )
        QMessageBox.information(self, "Cài đặt", "Đã lưu.")
        self.changed.emit()
