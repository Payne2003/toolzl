"""Hàng đợi & điều phối: xếp lệnh, kiểm tra qua Safety Gate, bàn giao thủ công hoặc gửi API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .audit import AuditLog
from .db import Database, to_iso
from .errors import ApprovalError, BotError, GateBlocked, NotFound, ValidationError
from .models import (
    ACTIVE_JOB_STATUSES,
    Channel,
    GroupStatus,
    Job,
    JobStatus,
)
from .publishers import HandoffPackage, OfficialApiPublisher, UnconfiguredPublisher
from .safety import GateResult, SafetyGate
from .approval import ApprovalEngine
from .groups import GroupRepository


def _row_to_job(r) -> Job:
    return Job(
        id=r["id"],
        post_id=r["post_id"],
        post_version=r["post_version"],
        content_hash=r["content_hash"],
        group_id=r["group_id"],
        channel=Channel(r["channel"]),
        status=JobStatus(r["status"]),
        scheduled_at=r["scheduled_at"],
        block_reason=r["block_reason"],
        created_by=r["created_by"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        handed_off_at=r["handed_off_at"],
        completed_at=r["completed_at"],
        completed_by=r["completed_by"],
    )


@dataclass
class EnqueueResult:
    created: list[int]
    skipped: list[tuple[int, str]]  # (group_id, lý do)


class Dispatcher:
    def __init__(
        self,
        db: Database,
        audit: AuditLog,
        posts: ApprovalEngine,
        groups: GroupRepository,
        api_publisher: OfficialApiPublisher | None = None,
    ):
        self.db = db
        self.audit = audit
        self.posts = posts
        self.groups = groups
        self.api_publisher = api_publisher or UnconfiguredPublisher()
        self.gate = SafetyGate(db, self.api_publisher)

    # ---------------------------------------------------------------- query
    def get(self, job_id: int) -> Job:
        r = self.db.query_one("SELECT * FROM jobs WHERE id = ?", (job_id,))
        if r is None:
            raise NotFound(f"Không tìm thấy lệnh #{job_id}")
        return _row_to_job(r)

    def list(self, statuses: tuple[str, ...] | None = None, limit: int = 1000) -> list[dict]:
        """Danh sách lệnh kèm tên nhóm & tiêu đề nội dung (cho giao diện)."""
        sql = (
            "SELECT j.*, g.name AS group_name, g.link AS group_link, p.title AS post_title "
            "FROM jobs j JOIN groups g ON g.id = j.group_id JOIN posts p ON p.id = j.post_id"
        )
        params: list = []
        if statuses:
            sql += f" WHERE j.status IN ({','.join('?' * len(statuses))})"
            params.extend(statuses)
        sql += " ORDER BY COALESCE(j.scheduled_at, j.created_at), j.id LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.db.query(sql, tuple(params))]

    def history(self, limit: int = 1000) -> list[dict]:
        sql = (
            "SELECT j.*, g.name AS group_name, p.title AS post_title "
            "FROM jobs j JOIN groups g ON g.id = j.group_id JOIN posts p ON p.id = j.post_id "
            "WHERE j.status NOT IN (?, ?) ORDER BY j.updated_at DESC, j.id DESC LIMIT ?"
        )
        return [dict(r) for r in self.db.query(sql, (JobStatus.QUEUED.value, JobStatus.BLOCKED.value, limit))]

    # -------------------------------------------------------------- enqueue
    def enqueue(
        self,
        post_id: int,
        group_ids: list[int],
        actor: str,
        channel: Channel = Channel.MANUAL,
        scheduled_at: datetime | None = None,
    ) -> EnqueueResult:
        """Approval Engine: chỉ cho xếp lệnh khi nội dung đã duyệt và nhóm được phép."""
        if not group_ids:
            raise ValidationError("Chưa chọn nhóm nào.")
        post = self.posts.get(post_id)
        if not post.approval_valid:
            raise ApprovalError("Chỉ xếp lệnh cho nội dung đã được duyệt (và chưa bị sửa sau khi duyệt).")
        channel = Channel(channel)
        sched = to_iso(scheduled_at) if scheduled_at else None
        created: list[int] = []
        skipped: list[tuple[int, str]] = []
        now = self.db.now_iso()

        with self.db.transaction():
            for gid in dict.fromkeys(group_ids):  # bỏ trùng, giữ thứ tự
                try:
                    g = self.groups.get(gid)
                except NotFound as e:
                    skipped.append((gid, str(e)))
                    continue
                if not g.allowed:
                    skipped.append((gid, f"'{g.name}' không nằm trong danh sách được phép"))
                    continue
                if g.status != GroupStatus.ACTIVE:
                    skipped.append((gid, f"'{g.name}' đang {g.status.value}"))
                    continue
                if channel == Channel.OFFICIAL_API and not (g.api_verified and g.api_group_id):
                    skipped.append((gid, f"'{g.name}' chưa được xác nhận quyền truy cập API"))
                    continue
                dup = self.db.query_one(
                    f"SELECT id FROM jobs WHERE group_id = ? AND content_hash = ? "
                    f"AND status IN ({','.join('?' * len(ACTIVE_JOB_STATUSES))})",
                    (gid, post.content_hash, *ACTIVE_JOB_STATUSES),
                )
                if dup:
                    skipped.append((gid, f"'{g.name}' đã có lệnh #{dup['id']} cho nội dung này"))
                    continue
                cur = self.db.execute(
                    "INSERT INTO jobs(post_id, post_version, content_hash, group_id, channel, status, "
                    "scheduled_at, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)",
                    (post.id, post.version, post.content_hash, gid, channel.value, sched, actor, now, now),
                )
                jid = int(cur.lastrowid)
                created.append(jid)
                self.audit.record(actor, "job.enqueue", "job", jid, post_id=post.id, version=post.version,
                                  group_id=gid, group=g.name, channel=channel.value, scheduled_at=sched)
            for gid, why in skipped:
                self.audit.record(actor, "job.enqueue_rejected", "group", gid, reason=why, post_id=post.id)
        return EnqueueResult(created, skipped)

    def cancel(self, job_id: int, actor: str, reason: str = "Người dùng hủy") -> Job:
        job = self.get(job_id)
        if job.status not in (JobStatus.QUEUED, JobStatus.BLOCKED):
            raise BotError("Chỉ hủy được lệnh đang chờ hoặc bị chặn.")
        self._set_status(job, JobStatus.CANCELLED, actor, "job.cancel", reason=reason, block_reason=reason)
        return self.get(job_id)

    # ----------------------------------------------------------- safety gate
    def check(self, job_id: int) -> GateResult:
        return self.gate.evaluate(self.get(job_id))

    def refresh(self, actor: str = "system") -> dict[int, GateResult]:
        """Đánh giá lại toàn bộ lệnh đang chờ; cập nhật trạng thái blocked/queued."""
        results: dict[int, GateResult] = {}
        rows = self.db.query("SELECT * FROM jobs WHERE status IN (?, ?)",
                             (JobStatus.QUEUED.value, JobStatus.BLOCKED.value))
        with self.db.transaction():
            for r in rows:
                job = _row_to_job(r)
                res = self.gate.evaluate(job)
                results[job.id] = res
                if res.ok or res.waiting:
                    new_status, new_reason = JobStatus.QUEUED, (res.summary if res.waiting else None)
                else:
                    new_status, new_reason = JobStatus.BLOCKED, res.summary
                if new_status != job.status or new_reason != job.block_reason:
                    self.db.execute("UPDATE jobs SET status = ?, block_reason = ?, updated_at = ? WHERE id = ?",
                                    (new_status.value, new_reason, self.db.now_iso(), job.id))
                    if new_status != job.status:
                        action = "gate.block" if new_status == JobStatus.BLOCKED else "gate.unblock"
                        self.audit.record(actor, action, "job", job.id, reason=new_reason)
        return results

    def next_ready(self, channel: Channel | None = None) -> Job | None:
        results = self.refresh()
        for row in self.list((JobStatus.QUEUED.value,)):
            res = results.get(row["id"])
            if res and res.ok and (channel is None or row["channel"] == Channel(channel).value):
                return self.get(row["id"])
        return None

    # ------------------------------------------------------ manual handoff
    def handoff(self, job_id: int, actor: str) -> HandoffPackage:
        """Bàn giao thủ công: kiểm tra Safety Gate lần cuối, trả về nội dung & link nhóm.
        Giao diện sẽ chép nội dung và mở Zalo; người dùng tự kiểm tra và bấm gửi."""
        job = self.get(job_id)
        if job.channel != Channel.MANUAL:
            raise BotError("Lệnh này dùng kênh Official API, không bàn giao thủ công.")
        res = self.gate.evaluate(job)
        if not res.ok:
            with self.db.transaction():
                if not res.waiting and job.status != JobStatus.BLOCKED:
                    self.db.execute("UPDATE jobs SET status = 'blocked', block_reason = ?, updated_at = ? WHERE id = ?",
                                    (res.summary, self.db.now_iso(), job.id))
                self.audit.record(actor, "gate.deny_handoff", "job", job.id, reason=res.summary)
            raise GateBlocked(res.reasons)
        post = self.posts.get(job.post_id)
        group = self.groups.get(job.group_id)
        now = self.db.now_iso()
        with self.db.transaction():
            self.db.execute(
                "UPDATE jobs SET status = 'handed_off', handed_off_at = ?, block_reason = NULL, updated_at = ? "
                "WHERE id = ?",
                (now, now, job.id),
            )
            self.audit.record(actor, "job.handoff", "job", job.id, group=group.name,
                              version=job.post_version, hash=job.content_hash[:12])
        return HandoffPackage(job_id=job.id, group_name=group.name, group_link=group.link, text=post.body)

    def confirm_sent(self, job_id: int, actor: str, note: str | None = None) -> Job:
        job = self.get(job_id)
        if job.status != JobStatus.HANDED_OFF:
            raise BotError("Chỉ xác nhận được lệnh đã bàn giao.")
        self._set_status(job, JobStatus.SENT, actor, "job.confirm_sent", reason=note, complete=True)
        return self.get(job_id)

    def skip(self, job_id: int, actor: str, reason: str) -> Job:
        job = self.get(job_id)
        if job.status not in (JobStatus.HANDED_OFF, JobStatus.QUEUED, JobStatus.BLOCKED):
            raise BotError("Không thể bỏ qua lệnh ở trạng thái này.")
        if not (reason or "").strip():
            raise ValidationError("Cần ghi lý do bỏ qua.")
        self._set_status(job, JobStatus.SKIPPED, actor, "job.skip", reason=reason.strip(),
                         block_reason=reason.strip(), complete=True)
        return self.get(job_id)

    def return_to_queue(self, job_id: int, actor: str, reason: str = "Chưa gửi, trả lại hàng đợi") -> Job:
        job = self.get(job_id)
        if job.status != JobStatus.HANDED_OFF:
            raise BotError("Chỉ trả lại được lệnh đã bàn giao.")
        with self.db.transaction():
            self.db.execute("UPDATE jobs SET status = 'queued', handed_off_at = NULL, updated_at = ? WHERE id = ?",
                            (self.db.now_iso(), job.id))
            self.audit.record(actor, "job.return_to_queue", "job", job.id, reason=reason)
        return self.get(job_id)

    # --------------------------------------------------------- official api
    def send_via_api(self, job_id: int, actor: str) -> Job:
        job = self.get(job_id)
        if job.channel != Channel.OFFICIAL_API:
            raise BotError("Lệnh này dùng kênh thủ công.")
        res = self.gate.evaluate(job)
        if not res.ok:
            with self.db.transaction():
                self.audit.record(actor, "gate.deny_api", "job", job.id, reason=res.summary)
            raise GateBlocked(res.reasons)
        post = self.posts.get(job.post_id)
        group = self.groups.get(job.group_id)
        try:
            result = self.api_publisher.publish(group.api_group_id or "", post.body)
        except Exception as e:  # noqa: BLE001 — mọi lỗi adapter đều phải ghi nhận
            result = None
            message = f"{type(e).__name__}: {e}"
        else:
            message = result.message

        now = self.db.now_iso()
        with self.db.transaction():
            if result is not None and result.ok:
                self.db.execute(
                    "UPDATE jobs SET status = 'sent', handed_off_at = ?, completed_at = ?, completed_by = ?, "
                    "block_reason = NULL, updated_at = ? WHERE id = ?",
                    (now, now, actor, now, job.id))
                self.audit.record(actor, "job.api_sent", "job", job.id, external_id=result.external_id,
                                  message=message)
            else:
                self.db.execute(
                    "UPDATE jobs SET status = 'failed', block_reason = ?, completed_at = ?, updated_at = ? "
                    "WHERE id = ?", (message, now, now, job.id))
                self.audit.record(actor, "job.api_failed", "job", job.id, reason=message)
                self._maybe_auto_stop()
        return self.get(job_id)

    def _maybe_auto_stop(self) -> None:
        limit = int(self.db.get_setting("auto_stop_after_failures") or 0)
        if limit <= 0 or self.db.get_setting("kill_switch"):
            return
        rows = self.db.query(
            "SELECT status FROM jobs WHERE channel = 'api' AND status IN ('sent', 'failed') "
            "ORDER BY completed_at DESC, id DESC LIMIT ?", (limit,))
        if len(rows) == limit and all(r["status"] == "failed" for r in rows):
            reason = f"Tự động dừng sau {limit} lỗi API liên tiếp"
            self.db.set_setting("kill_switch", True)
            self.audit.record("system", "kill_switch.on", "system", None, reason=reason)

    # ---------------------------------------------------------- kill switch
    def set_kill_switch(self, on: bool, actor: str, reason: str) -> None:
        if not (reason or "").strip():
            raise ValidationError("Cần ghi lý do bật/tắt dừng khẩn cấp.")
        with self.db.transaction():
            self.db.set_setting("kill_switch", bool(on))
            self.audit.record(actor, "kill_switch.on" if on else "kill_switch.off", "system", None,
                              reason=reason.strip())

    def update_settings(self, actor: str, **values) -> None:
        current = self.db.all_settings()
        changes = {k: {"from": current.get(k), "to": v} for k, v in values.items()
                   if k != "kill_switch" and current.get(k) != v}
        if not changes:
            return
        with self.db.transaction():
            for k in changes:
                self.db.set_setting(k, values[k])
            self.audit.record(actor, "settings.update", "system", None, changes=changes)

    # -------------------------------------------------------------- helpers
    def _set_status(self, job: Job, status: JobStatus, actor: str, action: str, reason: str | None = None,
                    block_reason: str | None = None, complete: bool = False) -> None:
        now = self.db.now_iso()
        with self.db.transaction():
            if complete:
                self.db.execute(
                    "UPDATE jobs SET status = ?, block_reason = ?, completed_at = ?, completed_by = ?, updated_at = ? "
                    "WHERE id = ?", (status.value, block_reason, now, actor, now, job.id))
            else:
                self.db.execute("UPDATE jobs SET status = ?, block_reason = ?, updated_at = ? WHERE id = ?",
                                (status.value, block_reason, now, job.id))
            self.audit.record(actor, action, "job", job.id, reason=reason, prev_status=job.status.value)
