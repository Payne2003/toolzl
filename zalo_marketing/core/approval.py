"""Approval Engine — quản lý nội dung, phê duyệt và khóa phiên bản.

Quy trình:  draft ──submit──> pending ──approve──> approved (khóa)
                 ^                 └──reject──> rejected ──edit──> draft
                 └──────── edit (tạo phiên bản mới, hủy duyệt) ───────┘
"""

from __future__ import annotations

from .audit import AuditLog
from .db import Database
from .errors import ApprovalError, NotFound, ValidationError
from .models import PENDING_JOB_STATUSES, JobStatus, Post, PostStatus, content_hash, normalize_body

MAX_BODY_CHARS = 4000


def _row_to_post(r) -> Post:
    return Post(
        id=r["id"],
        title=r["title"],
        body=r["body"],
        status=PostStatus(r["status"]),
        version=r["version"],
        content_hash=r["content_hash"],
        author=r["author"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        approved_by=r["approved_by"],
        approved_at=r["approved_at"],
        approved_hash=r["approved_hash"],
        review_note=r["review_note"],
    )


def _validate(title: str, body: str) -> tuple[str, str]:
    title = (title or "").strip()
    body = normalize_body(body or "")
    if not title:
        raise ValidationError("Tiêu đề (nhãn nội bộ) không được để trống.")
    if not body:
        raise ValidationError("Nội dung không được để trống.")
    if len(body) > MAX_BODY_CHARS:
        raise ValidationError(f"Nội dung quá dài ({len(body)}/{MAX_BODY_CHARS} ký tự).")
    return title, body


class ApprovalEngine:
    def __init__(self, db: Database, audit: AuditLog):
        self.db = db
        self.audit = audit

    # ----------------------------------------------------------------- read
    def get(self, post_id: int) -> Post:
        r = self.db.query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
        if r is None:
            raise NotFound(f"Không tìm thấy nội dung #{post_id}")
        return _row_to_post(r)

    def list(self, status: PostStatus | None = None, include_archived: bool = False) -> list[Post]:
        sql, params = "SELECT * FROM posts WHERE 1=1", []
        if status is not None:
            sql += " AND status = ?"
            params.append(PostStatus(status).value)
        elif not include_archived:
            sql += " AND status != 'archived'"
        sql += " ORDER BY updated_at DESC, id DESC"
        return [_row_to_post(r) for r in self.db.query(sql, tuple(params))]

    def versions(self, post_id: int) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM post_versions WHERE post_id = ? ORDER BY version DESC", (post_id,))]

    # ---------------------------------------------------------------- write
    def create(self, title: str, body: str, author: str) -> Post:
        title, body = _validate(title, body)
        h = content_hash(body)
        now = self.db.now_iso()
        with self.db.transaction():
            cur = self.db.execute(
                "INSERT INTO posts(title, body, status, version, content_hash, author, created_at, updated_at) "
                "VALUES (?, ?, 'draft', 1, ?, ?, ?, ?)",
                (title, body, h, author, now, now),
            )
            pid = int(cur.lastrowid)
            self._snapshot(pid, 1, title, body, h, author, now)
            self.audit.record(author, "post.create", "post", pid, version=1, hash=h[:12])
        return self.get(pid)

    def edit(self, post_id: int, title: str, body: str, actor: str) -> Post:
        """Sửa nội dung. Nếu nội dung đã duyệt/đang chờ duyệt bị thay đổi:
        tạo phiên bản mới, hủy phê duyệt và hủy các lệnh đăng đang chờ."""
        post = self.get(post_id)
        if post.status == PostStatus.ARCHIVED:
            raise ApprovalError("Nội dung đã lưu trữ, không thể sửa.")
        title, body = _validate(title, body)
        h = content_hash(body)
        now = self.db.now_iso()

        with self.db.transaction():
            if h == post.content_hash:
                if title != post.title:
                    self.db.execute("UPDATE posts SET title = ?, updated_at = ? WHERE id = ?", (title, now, post_id))
                    self.audit.record(actor, "post.rename", "post", post_id, title=title)
                return self.get(post_id) if title != post.title else post

            new_version = post.version + 1
            self.db.execute(
                "UPDATE posts SET title = ?, body = ?, content_hash = ?, version = ?, status = 'draft', "
                "approved_by = NULL, approved_at = NULL, approved_hash = NULL, review_note = NULL, "
                "updated_at = ? WHERE id = ?",
                (title, body, h, new_version, now, post_id),
            )
            self._snapshot(post_id, new_version, title, body, h, actor, now)
            reason = None
            if post.status in (PostStatus.APPROVED, PostStatus.PENDING):
                reason = "Nội dung thay đổi sau khi gửi duyệt/đã duyệt — cần duyệt lại"
            self.audit.record(actor, "post.edit", "post", post_id, reason=reason,
                              version=new_version, prev_status=post.status.value, hash=h[:12])
            self._cancel_active_jobs(post_id, actor, "Nội dung đã được sửa thành phiên bản mới")
        return self.get(post_id)

    def submit(self, post_id: int, actor: str) -> Post:
        post = self.get(post_id)
        if post.status not in (PostStatus.DRAFT, PostStatus.REJECTED):
            raise ApprovalError(f"Chỉ gửi duyệt được bản nháp hoặc bản bị từ chối (hiện tại: {post.status.value}).")
        with self.db.transaction():
            self.db.execute(
                "UPDATE posts SET status = 'pending', review_note = NULL, updated_at = ? WHERE id = ?",
                (self.db.now_iso(), post_id),
            )
            self.audit.record(actor, "post.submit", "post", post_id, version=post.version)
        return self.get(post_id)

    def approve(self, post_id: int, approver: str, note: str = "", expected_hash: str | None = None) -> Post:
        """Phê duyệt và khóa phiên bản. `expected_hash` bảo đảm người duyệt duyệt đúng
        nội dung họ đang xem (tránh nội dung bị đổi giữa chừng)."""
        approver = (approver or "").strip()
        if not approver:
            raise ApprovalError("Cần nhập tên người duyệt.")
        post = self.get(post_id)
        if post.status != PostStatus.PENDING:
            raise ApprovalError(f"Chỉ duyệt được nội dung đang chờ duyệt (hiện tại: {post.status.value}).")
        if expected_hash is not None and expected_hash != post.content_hash:
            raise ApprovalError("Nội dung đã thay đổi kể từ khi bạn mở — hãy tải lại và xem lại trước khi duyệt.")
        if self.db.get_setting("require_different_approver") and approver.casefold() == post.author.casefold():
            raise ApprovalError("Nguyên tắc 4 mắt đang bật: người duyệt phải khác người soạn.")
        now = self.db.now_iso()
        with self.db.transaction():
            self.db.execute(
                "UPDATE posts SET status = 'approved', approved_by = ?, approved_at = ?, approved_hash = ?, "
                "review_note = ?, updated_at = ? WHERE id = ?",
                (approver, now, post.content_hash, note or None, now, post_id),
            )
            self.audit.record(approver, "post.approve", "post", post_id, reason=note or None,
                              version=post.version, hash=post.content_hash[:12])
        return self.get(post_id)

    def reject(self, post_id: int, approver: str, note: str) -> Post:
        approver = (approver or "").strip()
        if not approver:
            raise ApprovalError("Cần nhập tên người duyệt.")
        if not (note or "").strip():
            raise ApprovalError("Cần ghi lý do từ chối.")
        post = self.get(post_id)
        if post.status != PostStatus.PENDING:
            raise ApprovalError(f"Chỉ từ chối được nội dung đang chờ duyệt (hiện tại: {post.status.value}).")
        with self.db.transaction():
            self.db.execute(
                "UPDATE posts SET status = 'rejected', review_note = ?, updated_at = ? WHERE id = ?",
                (note.strip(), self.db.now_iso(), post_id),
            )
            self.audit.record(approver, "post.reject", "post", post_id, reason=note.strip(), version=post.version)
        return self.get(post_id)

    def revoke(self, post_id: int, actor: str, reason: str) -> Post:
        """Thu hồi phê duyệt (về bản nháp) và hủy các lệnh đăng đang chờ."""
        if not (reason or "").strip():
            raise ApprovalError("Cần ghi lý do thu hồi.")
        post = self.get(post_id)
        if post.status != PostStatus.APPROVED:
            raise ApprovalError("Chỉ thu hồi được nội dung đã duyệt.")
        with self.db.transaction():
            self.db.execute(
                "UPDATE posts SET status = 'draft', approved_by = NULL, approved_at = NULL, approved_hash = NULL, "
                "updated_at = ? WHERE id = ?",
                (self.db.now_iso(), post_id),
            )
            self.audit.record(actor, "post.revoke", "post", post_id, reason=reason.strip(), version=post.version)
            self._cancel_active_jobs(post_id, actor, f"Thu hồi phê duyệt: {reason.strip()}")
        return self.get(post_id)

    def archive(self, post_id: int, actor: str) -> Post:
        post = self.get(post_id)
        with self.db.transaction():
            self.db.execute("UPDATE posts SET status = 'archived', updated_at = ? WHERE id = ?",
                            (self.db.now_iso(), post_id))
            self.audit.record(actor, "post.archive", "post", post_id, prev_status=post.status.value)
            self._cancel_active_jobs(post_id, actor, "Nội dung đã được lưu trữ")
        return self.get(post_id)

    # -------------------------------------------------------------- helpers
    def _snapshot(self, post_id, version, title, body, h, actor, now) -> None:
        self.db.execute(
            "INSERT INTO post_versions(post_id, version, title, body, content_hash, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (post_id, version, title, body, h, actor, now),
        )

    def _cancel_active_jobs(self, post_id: int, actor: str, reason: str) -> None:
        # Lệnh đã bàn giao (handed_off) không bị hủy: người dùng có thể đã gửi thật,
        # nên vẫn cần họ xác nhận "Đã gửi" hoặc "Bỏ qua".
        placeholders = ",".join("?" * len(PENDING_JOB_STATUSES))
        rows = self.db.query(
            f"SELECT id FROM jobs WHERE post_id = ? AND status IN ({placeholders})",
            (post_id, *PENDING_JOB_STATUSES),
        )
        now = self.db.now_iso()
        for r in rows:
            self.db.execute(
                "UPDATE jobs SET status = ?, block_reason = ?, updated_at = ? WHERE id = ?",
                (JobStatus.CANCELLED.value, reason, now, r["id"]),
            )
            self.audit.record(actor, "job.cancel", "job", r["id"], reason=reason, post_id=post_id)
