"""Kênh gửi bài.

* Manual Handoff (mặc định): phần mềm chỉ chép nội dung vào clipboard và mở nhóm
  trong Zalo; người dùng tự kiểm tra và bấm gửi. Không giả lập thao tác, không gọi
  endpoint không chính thức.

* Official API: chỉ là điểm mở rộng. Phần mềm KHÔNG kèm sẵn bất kỳ endpoint nào —
  khi tổ chức của bạn được Zalo cấp API và quyền truy cập nhóm, hãy viết một lớp con
  của `OfficialApiPublisher` theo đúng tài liệu Zalo đã cấp, rồi đăng ký trong
  `zalo_marketing/app.py` (xem README).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class HandoffPackage:
    job_id: int
    group_name: str
    group_link: str
    text: str
    attachments: list[str] = field(default_factory=list)  # đường dẫn tuyệt đối ảnh / video


@dataclass
class PublishResult:
    ok: bool
    message: str = ""
    external_id: str | None = None


class OfficialApiPublisher(ABC):
    """Giao diện cho adapter API chính thức (đã được Zalo xác nhận)."""

    name = "official-api"

    @abstractmethod
    def is_configured(self) -> bool:
        """True khi đã có đủ thông tin xác thực hợp lệ."""

    @abstractmethod
    def publish(self, api_group_id: str, text: str) -> PublishResult:
        """Gửi nội dung vào nhóm qua API chính thức."""


class UnconfiguredPublisher(OfficialApiPublisher):
    """Mặc định: chưa có API → Safety Gate luôn chặn kênh API."""

    name = "unconfigured"

    def is_configured(self) -> bool:
        return False

    def publish(self, api_group_id: str, text: str) -> PublishResult:  # pragma: no cover
        return PublishResult(ok=False, message="Chưa cấu hình adapter Official API")
