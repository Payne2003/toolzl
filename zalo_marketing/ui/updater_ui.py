"""Giao diện cập nhật: kiểm tra nền, hộp thoại thông tin bản mới, tải & cài đặt."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QMessageBox, QProgressDialog, QTextBrowser, QVBoxLayout

from .. import __version__
from ..core import updater
from ..core.updater import UpdateError, UpdateInfo
from .theme import button, label


class _Signals(QObject):
    done = Signal(object)      # UpdateInfo | None | Path
    failed = Signal(str)
    progress = Signal(int, int)


class _Task(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self):  # chạy trong luồng nền
        try:
            result = self.fn(self.signals)
        except UpdateError as e:
            self.signals.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.signals.failed.emit(f"{type(e).__name__}: {e}")
        else:
            self.signals.done.emit(result)


class UpdateDialog(QDialog):
    LATER, SKIP, INSTALL = 0, 1, 2

    def __init__(self, info: UpdateInfo, mode: str, parent=None):
        super().__init__(parent)
        self.choice = self.LATER
        self.setWindowTitle("Có bản cập nhật mới")
        self.resize(560, 460)
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(info.notes or "_Không có ghi chú phát hành._")

        size = f" · {info.setup_size / 1024 / 1024:.0f} MB" if info.setup_size else ""
        if mode == "installed" and info.setup_url:
            how = "Phần mềm sẽ tải bộ cài, kiểm tra tính toàn vẹn, cài đè và tự mở lại. Dữ liệu của bạn được giữ nguyên."
            action = f"⬆  Cập nhật ngay{size}"
        else:
            how = ("Bạn đang dùng bản portable / mã nguồn — trang tải bản mới sẽ được mở trong trình duyệt. "
                   "Dữ liệu được giữ nguyên khi thay bản mới.")
            action = "Mở trang tải về"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(label(f"Phiên bản {info.version} đã sẵn sàng", "PageTitle"))
        lay.addWidget(label(f"Bạn đang dùng phiên bản {__version__}. {how}", "InfoBox", wrap=True))
        lay.addWidget(label("CÓ GÌ MỚI", "StatLabel"))
        lay.addWidget(notes, 1)
        row = QHBoxLayout()
        row.addWidget(button("Bỏ qua phiên bản này", "ghost", lambda: self._done(self.SKIP)))
        row.addStretch()
        row.addWidget(button("Để sau", slot=lambda: self._done(self.LATER)))
        b = button(action, "success", lambda: self._done(self.INSTALL))
        b.setDefault(True)
        row.addWidget(b)
        lay.addLayout(row)

    def _done(self, choice: int) -> None:
        self.choice = choice
        self.accept()


class UpdateController(QObject):
    """Điều phối kiểm tra cập nhật. Phát `available(info)` khi có bản mới."""

    available = Signal(object)
    checking = Signal(bool)

    def __init__(self, svc, parent_widget):
        super().__init__(parent_widget)
        self.svc = svc
        self.parent_widget = parent_widget
        self.pool = QThreadPool.globalInstance()
        self.latest: UpdateInfo | None = None
        self._busy = False

    def _source(self) -> str:
        return self.svc.db.get_setting("update_url") or updater.DEFAULT_UPDATE_URL

    def check(self, silent: bool = True) -> None:
        """silent=True: kiểm tra nền khi khởi động, không báo lỗi / không báo 'đã mới nhất'."""
        if self._busy:
            return
        self._busy = True
        self.checking.emit(True)
        url = self._source()
        task = _Task(lambda _s: updater.check_for_update(url))
        task.signals.done.connect(lambda info: self._on_checked(info, silent))
        task.signals.failed.connect(lambda msg: self._on_failed(msg, silent))
        self.pool.start(task)

    def _finish(self):
        self._busy = False
        self.checking.emit(False)

    def _on_checked(self, info: UpdateInfo | None, silent: bool) -> None:
        self._finish()
        self.latest = info
        if info is None:
            if not silent:
                QMessageBox.information(self.parent_widget, "Cập nhật",
                                        f"Bạn đang dùng phiên bản mới nhất ({__version__}).")
            return
        self.available.emit(info)
        skipped = self.svc.db.get_setting("skipped_version")
        if not silent or skipped != info.version:
            self.prompt(info)

    def _on_failed(self, msg: str, silent: bool) -> None:
        self._finish()
        if not silent:
            QMessageBox.warning(self.parent_widget, "Cập nhật", f"Không kiểm tra được bản cập nhật.\n\n{msg}")

    # ------------------------------------------------------------- install
    def prompt(self, info: UpdateInfo | None = None) -> None:
        info = info or self.latest
        if info is None:
            return
        mode = updater.install_mode()
        dlg = UpdateDialog(info, mode, self.parent_widget)
        dlg.exec()
        if dlg.choice == UpdateDialog.SKIP:
            self.svc.db.set_setting("skipped_version", info.version)
        elif dlg.choice == UpdateDialog.INSTALL:
            if mode == "installed" and info.setup_url:
                self._download_and_install(info)
            else:
                QDesktopServices.openUrl(QUrl(info.page_url))

    def _download_and_install(self, info: UpdateInfo) -> None:
        dest = Path(tempfile.gettempdir()) / "ZaloMarketingUpdate" / (info.setup_name or "setup.exe")
        dlg = QProgressDialog("Đang tải bản cập nhật…", "Hủy", 0, 100, self.parent_widget)
        dlg.setWindowTitle(f"Cập nhật lên {info.version}")
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setValue(0)
        cancelled = {"v": False}
        dlg.canceled.connect(lambda: cancelled.__setitem__("v", True))

        def work(signals: _Signals):
            def cb(done, total):
                signals.progress.emit(done, total)
                return not cancelled["v"]
            return updater.download(info.setup_url, dest, info.sha256, cb)

        def on_progress(done, total):
            if total:
                dlg.setMaximum(100)
                dlg.setValue(int(done * 100 / total))
                dlg.setLabelText(f"Đang tải bản cập nhật… {done / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB")
            else:
                dlg.setMaximum(0)

        task = _Task(work)
        task.signals.progress.connect(on_progress)
        task.signals.done.connect(lambda path: (dlg.close(), self._run_installer(Path(path))))
        task.signals.failed.connect(lambda msg: (dlg.close(), None if cancelled["v"] else
                                                 QMessageBox.warning(self.parent_widget, "Cập nhật", msg)))
        self.pool.start(task)
        dlg.show()

    def _run_installer(self, setup: Path) -> None:
        if sys.platform != "win32":
            QMessageBox.information(self.parent_widget, "Cập nhật", f"Đã tải bộ cài: {setup}")
            return
        handed = self.svc.db.query_one("SELECT COUNT(*) n FROM jobs WHERE status = 'handed_off'")["n"]
        msg = "Phần mềm sẽ đóng để cài bản mới và tự mở lại sau khi cài xong."
        if handed:
            msg += f"\n\nLưu ý: còn {handed} lệnh đã bàn giao chưa xác nhận — bạn vẫn xác nhận được sau khi cập nhật."
        if QMessageBox.question(self.parent_widget, "Cài đặt bản cập nhật", msg + "\n\nTiếp tục?") != QMessageBox.Yes:
            return
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([str(setup), "/SP-", "/SILENT", "/NOCANCEL", "/CLOSEAPPLICATIONS"],
                         creationflags=flags, close_fds=True)
        QApplication.quit()
