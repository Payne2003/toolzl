"""Kiểm tra & tải bản cập nhật từ GitHub Releases (không phụ thuộc Qt).

Quy trình phát hành: tăng `__version__` trong `zalo_marketing/__init__.py`, push tag `vX.Y.Z`
→ workflow *Build Windows* tạo Release kèm `ZaloMarketing-Setup-X.Y.Z.exe`.
App đọc Release mới nhất, so sánh phiên bản, tải bộ cài và kiểm tra SHA-256 trước khi chạy.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .. import __version__

GITHUB_REPO = "Payne2003/toolzl"
DEFAULT_UPDATE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
USER_AGENT = f"ZaloMarketing-Updater/{__version__}"
TIMEOUT = 15


class UpdateError(Exception):
    pass


@dataclass
class UpdateInfo:
    version: str
    notes: str
    published_at: str
    page_url: str
    setup_url: str | None = None
    setup_name: str | None = None
    setup_size: int = 0
    sha256: str | None = None
    portable_url: str | None = None


def parse_version(value: str) -> tuple[int, ...]:
    """'v1.2.10' -> (1, 2, 10). Bỏ hậu tố như '-beta'."""
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)", value or "")
    if not m:
        raise UpdateError(f"Phiên bản không hợp lệ: {value!r}")
    parts = [int(p) for p in m.group(1).split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def parse_release(data: dict) -> UpdateInfo:
    """Chuyển JSON của GitHub Release thành UpdateInfo."""
    if data.get("draft") or data.get("prerelease"):
        raise UpdateError("Bản phát hành mới nhất là bản nháp / thử nghiệm.")
    tag = data.get("tag_name") or ""
    info = UpdateInfo(
        version=".".join(map(str, parse_version(tag))),
        notes=(data.get("body") or "").strip(),
        published_at=data.get("published_at") or "",
        page_url=data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases",
    )
    for asset in data.get("assets") or []:
        name = asset.get("name") or ""
        url = asset.get("browser_download_url")
        if re.match(r"^ZaloMarketing-Setup-.*\.exe$", name):
            info.setup_url, info.setup_name = url, name
            info.setup_size = int(asset.get("size") or 0)
            digest = asset.get("digest") or ""
            if digest.startswith("sha256:"):
                info.sha256 = digest.split(":", 1)[1].lower()
        elif re.match(r"^ZaloMarketing-Portable-.*\.zip$", name):
            info.portable_url = url
    return info


def _get(url: str, accept: str = "application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    return urllib.request.urlopen(req, timeout=TIMEOUT)  # noqa: S310 — chỉ dùng https


def check_for_update(url: str = DEFAULT_UPDATE_URL, current: str = __version__) -> UpdateInfo | None:
    """Trả về UpdateInfo nếu có bản mới hơn, None nếu đang dùng bản mới nhất."""
    if not url.startswith("https://"):
        raise UpdateError("Nguồn cập nhật phải dùng https://")
    try:
        with _get(url) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # chưa có Release nào
        if e.code == 403:
            raise UpdateError("GitHub tạm giới hạn số lần kiểm tra, vui lòng thử lại sau.") from e
        raise UpdateError(f"Máy chủ cập nhật trả lỗi HTTP {e.code}.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError(f"Không kết nối được máy chủ cập nhật: {getattr(e, 'reason', e)}") from e
    except ValueError as e:
        raise UpdateError("Dữ liệu cập nhật không hợp lệ.") from e
    info = parse_release(data)
    return info if is_newer(info.version, current) else None


def download(
    url: str,
    dest: Path,
    expected_sha256: str | None = None,
    progress: Callable[[int, int], bool] | None = None,
) -> Path:
    """Tải file về `dest`. `progress(đã_tải, tổng)` trả về False để hủy.
    Nếu có `expected_sha256` thì kiểm tra; sai mã băm → xóa file và báo lỗi."""
    if not url.startswith("https://"):
        raise UpdateError("Link tải phải dùng https://")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256()
    try:
        with _get(url, accept="application/octet-stream") as resp, open(tmp, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress and progress(done, total) is False:
                    raise UpdateError("Đã hủy tải bản cập nhật.")
    except UpdateError:
        tmp.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        tmp.unlink(missing_ok=True)
        raise UpdateError(f"Tải bản cập nhật thất bại: {getattr(e, 'reason', e)}") from e

    if expected_sha256 and h.hexdigest().lower() != expected_sha256.lower():
        tmp.unlink(missing_ok=True)
        raise UpdateError("File tải về không khớp mã kiểm tra SHA-256 — đã hủy để bảo đảm an toàn.")
    os.replace(tmp, dest)
    return dest


def install_mode() -> str:
    """'installed' (cài bằng Setup.exe), 'portable' (bản zip) hoặc 'source' (chạy từ mã nguồn)."""
    if not getattr(sys, "frozen", False):
        return "source"
    exe_dir = Path(sys.executable).parent
    return "installed" if any(exe_dir.glob("unins*.exe")) else "portable"
