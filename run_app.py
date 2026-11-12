"""Điểm vào cho PyInstaller (không dùng import tương đối)."""

from zalo_marketing.app import main

if __name__ == "__main__":
    raise SystemExit(main())
