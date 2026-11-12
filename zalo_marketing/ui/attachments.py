"""Ô hiển thị tệp đính kèm (ảnh / video) có ảnh thu nhỏ, kéo-thả vào và kéo ra."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget, QListWidgetItem

from ..core.media import IMAGE_EXTS, VIDEO_EXTS, human_size

THUMB = QSize(112, 84)


def _video_icon() -> QPixmap:
    pm = QPixmap(THUMB)
    pm.fill(QColor("#1A2233"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 220))
    cx, cy = THUMB.width() / 2, THUMB.height() / 2
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPolygonF
    p.drawPolygon(QPolygonF([QPointF(cx - 10, cy - 14), QPointF(cx - 10, cy + 14), QPointF(cx + 15, cy)]))
    f = QFont()
    f.setPixelSize(10)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#9FB3D1"))
    p.drawText(pm.rect().adjusted(0, 0, -6, -4), Qt.AlignRight | Qt.AlignBottom, "VIDEO")
    p.end()
    return pm


def thumbnail(path: str | Path, kind: str) -> QIcon:
    if kind == "image":
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid():
            reader.setScaledSize(size.scaled(THUMB, Qt.KeepAspectRatio))
        img = reader.read()
        if not img.isNull():
            canvas = QPixmap(THUMB)
            canvas.fill(QColor("#EEF1F5"))
            p = QPainter(canvas)
            p.drawImage((THUMB.width() - img.width()) // 2, (THUMB.height() - img.height()) // 2, img)
            p.end()
            return QIcon(canvas)
    return QIcon(_video_icon())


class AttachmentList(QListWidget):
    """Danh sách tệp đính kèm. Mỗi item giữ (đường dẫn, mô tả tệp) trong UserRole."""

    files_dropped = Signal(list)  # list[str] đường dẫn được thả vào

    def __init__(self, editable: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("Checklist")
        self.setViewMode(QListView.IconMode)
        self.setIconSize(THUMB)
        self.setGridSize(QSize(THUMB.width() + 18, THUMB.height() + 40))
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setWordWrap(True)
        self.setTextElideMode(Qt.ElideMiddle)
        self.setSpacing(4)
        self.setFixedHeight(THUMB.height() + 66)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(False)
        self.editable = editable
        # Cho phép kéo tệp ra ngoài (ví dụ thả thẳng vào khung chat Zalo)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop if editable else QAbstractItemView.DragOnly)
        self.setAcceptDrops(editable)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def set_items(self, entries: list[tuple[str, dict]]) -> None:
        self.clear()
        for path, att in entries:
            it = QListWidgetItem(thumbnail(path, att["kind"]), att["name"])
            it.setToolTip(f"{att['name']} · {human_size(att['size'])}")
            it.setData(Qt.UserRole, (path, att))
            it.setSizeHint(self.gridSize())
            self.addItem(it)

    def entries(self) -> list[tuple[str, dict]]:
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]

    def paths(self) -> list[str]:
        return [p for p, _ in self.entries()]

    # ---- kéo ra: cung cấp danh sách file cho ứng dụng khác
    def mimeData(self, items):  # noqa: N802
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(it.data(Qt.UserRole)[0]) for it in items])
        return md

    def mimeTypes(self):  # noqa: N802
        return ["text/uri-list"]

    # ---- thả vào: thêm tệp
    def _accepts(self, event) -> bool:
        if not self.editable or not event.mimeData().hasUrls() or event.source() is self:
            return False
        exts = IMAGE_EXTS | VIDEO_EXTS
        return any(Path(u.toLocalFile()).suffix.lower() in exts for u in event.mimeData().urls())

    def dragEnterEvent(self, event):  # noqa: N802
        if self._accepts(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802
        if self._accepts(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        if self._accepts(event):
            self.files_dropped.emit([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
            event.acceptProposedAction()
        else:
            event.ignore()
