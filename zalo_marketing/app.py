"""Điểm khởi chạy ứng dụng."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .core.publishers import OfficialApiPublisher, UnconfiguredPublisher
from .core.services import Services


def default_db_path() -> Path:
    base = os.environ.get("ZALO_MARKETING_HOME")
    if base:
        return Path(base) / "zalo_marketing.db"
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home()))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "ZaloMarketing" / "zalo_marketing.db"


def build_api_publisher() -> OfficialApiPublisher:
    """Đăng ký adapter Official API tại đây khi đã được Zalo cấp quyền (xem README)."""
    return UnconfiguredPublisher()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Zalo Personal Marketing Bot — Group Posting")
    parser.add_argument("--db", type=Path, default=None, help="Đường dẫn file SQLite")
    args = parser.parse_args(argv)

    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("ZaloMarketing")
    from .ui.theme import apply_theme
    apply_theme(app)

    svc = Services(args.db or default_db_path(), api_publisher=build_api_publisher())
    win = MainWindow(svc)
    win.show()
    win.ensure_operator()
    try:
        return app.exec()
    finally:
        svc.close()


if __name__ == "__main__":
    raise SystemExit(main())
