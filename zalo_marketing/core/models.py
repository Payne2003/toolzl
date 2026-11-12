"""Kiểu dữ liệu và trạng thái dùng chung."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum


class PostStatus(str, Enum):
    DRAFT = "draft"            # Bản nháp, đang soạn
    PENDING = "pending"        # Đã gửi duyệt
    APPROVED = "approved"      # Đã duyệt — nội dung bị khóa
    REJECTED = "rejected"      # Bị từ chối
    ARCHIVED = "archived"      # Lưu trữ, không dùng nữa


class GroupStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class JobStatus(str, Enum):
    QUEUED = "queued"              # Đang chờ trong hàng đợi
    BLOCKED = "blocked"            # Safety Gate chặn
    HANDED_OFF = "handed_off"      # Đã chép nội dung & mở Zalo, chờ người dùng xác nhận
    SENT = "sent"                  # Người dùng xác nhận đã gửi / API trả về thành công
    SKIPPED = "skipped"            # Người dùng bỏ qua
    FAILED = "failed"              # Lỗi khi gửi qua API
    CANCELLED = "cancelled"        # Hủy (ví dụ: nội dung bị sửa sau khi duyệt)


# Lệnh còn có thể bị hủy (chưa rời khỏi phần mềm)
PENDING_JOB_STATUSES = (JobStatus.QUEUED.value, JobStatus.BLOCKED.value)
# Lệnh chưa kết thúc (gồm cả lệnh đã bàn giao, chờ người dùng xác nhận)
ACTIVE_JOB_STATUSES = (*PENDING_JOB_STATUSES, JobStatus.HANDED_OFF.value)


class Channel(str, Enum):
    MANUAL = "manual"      # Manual Handoff — người dùng tự kiểm tra và gửi trên Zalo
    OFFICIAL_API = "api"   # Chỉ bật khi có API & quyền truy cập nhóm được Zalo xác nhận


def normalize_body(body: str) -> str:
    return "\n".join(line.rstrip() for line in body.replace("\r\n", "\n").strip().split("\n"))


def content_hash(body: str, attachment_hashes: list[str] | tuple[str, ...] = ()) -> str:
    """Băm nội dung gửi đi (chữ đã chuẩn hóa + mã băm các tệp đính kèm theo thứ tự)
    — dùng để khóa phiên bản và chống gửi trùng.

    Tiêu đề chỉ là nhãn nội bộ nên không nằm trong mã băm.
    """
    payload = normalize_body(body)
    if attachment_hashes:
        payload += "\n\x00attachments:" + ",".join(attachment_hashes)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class Post:
    id: int
    title: str
    body: str
    status: PostStatus
    version: int
    content_hash: str
    author: str
    created_at: str
    updated_at: str
    approved_by: str | None = None
    approved_at: str | None = None
    approved_hash: str | None = None
    review_note: str | None = None
    attachments: list = field(default_factory=list)

    @property
    def is_locked(self) -> bool:
        """Nội dung đã duyệt bị khóa: phải tạo phiên bản mới để sửa."""
        return self.status == PostStatus.APPROVED

    @property
    def approval_valid(self) -> bool:
        return (
            self.status == PostStatus.APPROVED
            and self.approved_hash is not None
            and self.approved_hash == self.content_hash
        )


@dataclass
class Group:
    id: int
    name: str
    link: str
    allowed: bool
    can_post: bool
    status: GroupStatus
    api_group_id: str | None
    api_verified: bool
    notes: str
    created_at: str
    updated_at: str


@dataclass
class Job:
    id: int
    post_id: int
    post_version: int
    content_hash: str
    group_id: int
    channel: Channel
    status: JobStatus
    scheduled_at: str | None
    block_reason: str | None
    created_by: str
    created_at: str
    updated_at: str
    handed_off_at: str | None = None
    completed_at: str | None = None
    completed_by: str | None = None


@dataclass
class AuditEntry:
    id: int
    ts: str
    actor: str
    action: str
    entity: str
    entity_id: int | None
    reason: str | None
    detail: str | None
