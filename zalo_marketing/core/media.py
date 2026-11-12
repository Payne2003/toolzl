"""Kho tệp đính kèm (ảnh / video) cho bài viết.

Tệp được chép vào thư mục dữ liệu của phần mềm, đặt tên theo SHA-256 nên bất biến:
nội dung đã duyệt không thể bị thay đổi ngầm bằng cách sửa tệp gốc.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .errors import ValidationError

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}

# Giới hạn của phần mềm (không phải giới hạn chính thức của Zalo).
MAX_ATTACHMENTS = 10
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_VIDEO_BYTES = 1024 * 1024 * 1024


def kind_of(path: str | Path) -> str | None:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


class MediaStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def add(self, source: str | Path) -> dict:
        """Chép tệp vào kho. Trả về mô tả tệp đính kèm (lưu kèm bài viết)."""
        src = Path(source)
        if not src.is_file():
            raise ValidationError(f"Không tìm thấy tệp: {src}")
        kind = kind_of(src)
        if kind is None:
            raise ValidationError(
                f"Định dạng không hỗ trợ: {src.name}. Ảnh: {', '.join(sorted(IMAGE_EXTS))}; "
                f"video: {', '.join(sorted(VIDEO_EXTS))}.")
        size = src.stat().st_size
        limit = MAX_IMAGE_BYTES if kind == "image" else MAX_VIDEO_BYTES
        if size > limit:
            raise ValidationError(f"{src.name} quá lớn ({human_size(size)}; tối đa {human_size(limit)}).")
        if size == 0:
            raise ValidationError(f"{src.name} là tệp rỗng.")
        sha = file_sha256(src)
        ext = src.suffix.lower()
        dest = self.root / f"{sha}{ext}"
        if not dest.exists():
            tmp = dest.with_suffix(ext + ".part")
            shutil.copyfile(src, tmp)
            tmp.replace(dest)
        return {"sha256": sha, "name": src.name, "ext": ext, "kind": kind, "size": size}

    def path(self, att: dict) -> Path:
        return self.root / f"{att['sha256']}{att['ext']}"

    def export(self, attachments: list[dict], folder_name: str) -> list[str]:
        """Tạo bản sao mang TÊN GỐC (để khi dán vào Zalo không hiện tên mã băm).
        Dùng hard link khi có thể để không tốn thêm dung lượng."""
        import os
        out_dir = self.root / "handoff" / folder_name
        out_dir.mkdir(parents=True, exist_ok=True)
        paths, used = [], set()
        for i, att in enumerate(attachments, 1):
            name = Path(att["name"]).name or f"tep{i}{att['ext']}"
            stem, ext = Path(name).stem, Path(name).suffix
            n = 1
            while name.lower() in used:
                n += 1
                name = f"{stem} ({n}){ext}"
            used.add(name.lower())
            dest = out_dir / name
            if not dest.exists() or dest.stat().st_size != att["size"]:
                dest.unlink(missing_ok=True)
                try:
                    os.link(self.path(att), dest)
                except OSError:
                    shutil.copyfile(self.path(att), dest)
            paths.append(str(dest))
        return paths

    def verify(self, attachments: list[dict]) -> list[str]:
        """Trả về danh sách lỗi (tệp bị thiếu / bị thay đổi)."""
        problems = []
        for att in attachments:
            p = self.path(att)
            if not p.is_file():
                problems.append(f"Thiếu tệp đính kèm '{att['name']}'")
            elif p.stat().st_size != att["size"]:
                problems.append(f"Tệp đính kèm '{att['name']}' đã bị thay đổi")
        return problems


def validate_attachments(attachments: list[dict] | None) -> list[dict]:
    attachments = list(attachments or [])
    if len(attachments) > MAX_ATTACHMENTS:
        raise ValidationError(f"Tối đa {MAX_ATTACHMENTS} tệp đính kèm mỗi bài.")
    seen = set()
    clean = []
    for a in attachments:
        if a["sha256"] in seen:
            continue
        seen.add(a["sha256"])
        clean.append({k: a[k] for k in ("sha256", "name", "ext", "kind", "size")})
    return clean
