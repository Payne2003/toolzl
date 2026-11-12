"""Safety Gate — kiểm tra trước MỖI lần đăng.

Kiểm tra: dừng khẩn cấp · phê duyệt & khóa phiên bản · quyền đăng · trạng thái nhóm ·
lịch hẹn · khung giờ yên lặng · chống gửi trùng · giới hạn tần suất · điều kiện kênh API.

Mọi điều kiện không thỏa → chặn (không có đường vòng). Phần mềm tự động dừng
thay vì cố gửi khi không đủ điều kiện.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from .db import Database, from_iso, to_iso
from .models import Channel, GroupStatus, Job, JobStatus, PostStatus


@dataclass
class GateResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    # True nếu lý do duy nhất là chưa đến giờ hẹn → giữ trong hàng đợi, không đánh dấu "bị chặn".
    waiting: bool = False

    @property
    def summary(self) -> str:
        return "OK" if self.ok else "; ".join(self.reasons)


def _parse_hhmm(value: str | None) -> time | None:
    if not value:
        return None
    try:
        h, m = value.strip().split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def in_quiet_hours(local_now: datetime, start: str | None, end: str | None) -> bool:
    s, e = _parse_hhmm(start), _parse_hhmm(end)
    if s is None or e is None or s == e:
        return False
    t = local_now.time().replace(second=0, microsecond=0)
    if s < e:
        return s <= t < e
    return t >= s or t < e  # khung giờ qua nửa đêm, ví dụ 22:00 → 07:00


class SafetyGate:
    def __init__(self, db: Database, api_publisher=None):
        self.db = db
        self.api_publisher = api_publisher

    def kill_switch_on(self) -> bool:
        return bool(self.db.get_setting("kill_switch"))

    def evaluate(self, job: Job) -> GateResult:
        s = self.db.all_settings()
        now = self.db.now()
        reasons: list[str] = []
        not_due = False

        # 1. Dừng khẩn cấp
        if s["kill_switch"]:
            reasons.append("Dừng khẩn cấp đang bật")

        # 2. Trạng thái lệnh
        if job.status not in (JobStatus.QUEUED, JobStatus.BLOCKED):
            reasons.append(f"Lệnh không ở trạng thái chờ (hiện tại: {job.status.value})")

        # 3. Phê duyệt & khóa phiên bản
        post = self.db.query_one("SELECT * FROM posts WHERE id = ?", (job.post_id,))
        if post is None:
            reasons.append("Nội dung không tồn tại")
        else:
            if post["status"] != PostStatus.APPROVED.value:
                reasons.append(f"Nội dung chưa được duyệt (trạng thái: {post['status']})")
            elif post["approved_hash"] != post["content_hash"]:
                reasons.append("Nội dung đã thay đổi sau khi duyệt")
            if post["content_hash"] != job.content_hash or post["version"] != job.post_version:
                reasons.append(
                    f"Phiên bản không khớp (lệnh: v{job.post_version}, hiện tại: v{post['version']})"
                )

        # 4. Nhóm: danh sách trắng · quyền đăng · trạng thái
        group = self.db.query_one("SELECT * FROM groups WHERE id = ?", (job.group_id,))
        if group is None:
            reasons.append("Nhóm không tồn tại")
        else:
            if not group["allowed"]:
                reasons.append("Nhóm không nằm trong danh sách được phép")
            if not group["can_post"]:
                reasons.append("Chưa xác nhận quyền đăng bài trong nhóm")
            if group["status"] != GroupStatus.ACTIVE.value:
                reasons.append(f"Nhóm đang ở trạng thái '{group['status']}'")

        # 5. Lịch hẹn
        sched = from_iso(job.scheduled_at)
        if sched and sched > now:
            not_due = True
            reasons.append(f"Chưa đến giờ hẹn ({sched.astimezone():%d/%m %H:%M})")

        # 6. Khung giờ yên lặng (giờ địa phương)
        if in_quiet_hours(now.astimezone(), s["quiet_start"], s["quiet_end"]):
            reasons.append(f"Trong khung giờ yên lặng {s['quiet_start']}–{s['quiet_end']}")

        delivered = (JobStatus.HANDED_OFF.value, JobStatus.SENT.value)

        # 7. Chống gửi trùng
        dedupe_days = int(s["dedupe_days"] or 0)
        if dedupe_days > 0:
            since = to_iso(now - timedelta(days=dedupe_days))
            dup = self.db.query_one(
                "SELECT id FROM jobs WHERE group_id = ? AND content_hash = ? AND id != ? "
                "AND status IN (?, ?) AND COALESCE(handed_off_at, completed_at) >= ? LIMIT 1",
                (job.group_id, job.content_hash, job.id, *delivered, since),
            )
            if dup:
                reasons.append(f"Nội dung này đã gửi vào nhóm trong {dedupe_days} ngày qua (lệnh #{dup['id']})")

        # 8. Giới hạn tần suất
        min_interval = int(s["min_interval_minutes"] or 0)
        if min_interval > 0:
            last = self.db.query_one(
                "SELECT MAX(COALESCE(handed_off_at, completed_at)) AS t FROM jobs "
                "WHERE group_id = ? AND id != ? AND status IN (?, ?)",
                (job.group_id, job.id, *delivered),
            )
            last_t = from_iso(last["t"]) if last else None
            if last_t and now - last_t < timedelta(minutes=min_interval):
                wait = timedelta(minutes=min_interval) - (now - last_t)
                reasons.append(f"Chưa đủ {min_interval} phút kể từ lần đăng trước vào nhóm "
                               f"(còn ~{math.ceil(wait.total_seconds() / 60)} phút)")

        since_24h = to_iso(now - timedelta(hours=24))
        per_group = int(s["per_group_daily_limit"] or 0)
        if per_group > 0:
            n = self.db.query_one(
                "SELECT COUNT(*) AS n FROM jobs WHERE group_id = ? AND id != ? AND status IN (?, ?) "
                "AND COALESCE(handed_off_at, completed_at) >= ?",
                (job.group_id, job.id, *delivered, since_24h),
            )["n"]
            if n >= per_group:
                reasons.append(f"Nhóm đã đạt giới hạn {per_group} bài / 24 giờ")

        daily = int(s["daily_limit"] or 0)
        if daily > 0:
            n = self.db.query_one(
                "SELECT COUNT(*) AS n FROM jobs WHERE id != ? AND status IN (?, ?) "
                "AND COALESCE(handed_off_at, completed_at) >= ?",
                (job.id, *delivered, since_24h),
            )["n"]
            if n >= daily:
                reasons.append(f"Đã đạt giới hạn {daily} bài / 24 giờ (tất cả các nhóm)")

        # 9. Kênh Official API
        if job.channel == Channel.OFFICIAL_API:
            if not s["official_api_enabled"]:
                reasons.append("Kênh Official API đang tắt")
            if group is not None and not (group["api_verified"] and group["api_group_id"]):
                reasons.append("Nhóm chưa được Zalo xác nhận quyền truy cập qua API")
            if self.api_publisher is None or not self.api_publisher.is_configured():
                reasons.append("Chưa cấu hình adapter Official API")

        waiting = not_due and len(reasons) == 1
        return GateResult(ok=not reasons, reasons=reasons, waiting=waiting)
