"""Giao diện: bảng màu, stylesheet (QSS), thẻ (card), nút, huy hiệu trạng thái."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QLabel, QPushButton, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem, QVBoxLayout,
)

# ------------------------------------------------------------------ palette
PRIMARY = "#0068FF"        # xanh Zalo
PRIMARY_HOVER = "#0057D9"
PRIMARY_SOFT = "#E8F1FF"
DANGER = "#E5484D"
DANGER_HOVER = "#CE3A3F"
BG = "#F4F6FA"
SURFACE = "#FFFFFF"
BORDER = "#E3E8EF"
TEXT = "#1A2233"
MUTED = "#6B7689"
SIDEBAR = "#0F1B2D"
SIDEBAR_TEXT = "#C9D3E3"

# Màu huy hiệu: chữ -> (nền, chữ)
BADGE_COLORS: dict[str, tuple[str, str]] = {
    # Trạng thái nội dung
    "Nháp": ("#EEF1F5", "#4A5568"),
    "Chờ duyệt": ("#FFF4E0", "#B25E00"),
    "Đã duyệt": ("#E3F8EC", "#1B7F45"),
    "Bị từ chối": ("#FDECEC", "#C0392B"),
    "Lưu trữ": ("#EEF1F5", "#8A94A6"),
    # Trạng thái lệnh
    "Đang chờ": (PRIMARY_SOFT, PRIMARY),
    "Bị chặn": ("#FDECEC", "#C0392B"),
    "Đã bàn giao": ("#F1E9FF", "#6B3FD4"),
    "Đã gửi": ("#E3F8EC", "#1B7F45"),
    "Bỏ qua": ("#EEF1F5", "#4A5568"),
    "Lỗi": ("#FDECEC", "#C0392B"),
    "Đã hủy": ("#EEF1F5", "#8A94A6"),
    # Nhóm
    "Hoạt động": ("#E3F8EC", "#1B7F45"),
    "Tạm dừng": ("#FFF4E0", "#B25E00"),
    # Có / không
    "Có": ("#E3F8EC", "#1B7F45"),
    "Không": ("#FDECEC", "#C0392B"),
    "Đã xác nhận": ("#E3F8EC", "#1B7F45"),
    # Kênh
    "Thủ công": ("#EEF1F5", "#334155"),
    "Official API": (PRIMARY_SOFT, PRIMARY),
}

CHECK_ICON = (Path(__file__).parent / "assets" / "check.svg").as_posix()

STYLESHEET = f"""
* {{
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, QWidget#Page, QStackedWidget {{
    background: {BG};
}}
QToolTip {{
    background: {SIDEBAR}; color: white; border: none; padding: 6px 8px; border-radius: 6px;
}}

/* ---------- Sidebar ---------- */
QFrame#Sidebar {{
    background: {SIDEBAR};
}}
QLabel#Brand {{
    color: white; font-size: 17px; font-weight: 700;
}}
QLabel#BrandSub {{
    color: #7F8DA6; font-size: 11px;
}}
QListWidget#Nav {{
    background: transparent; border: none; outline: none;
}}
QListWidget#Nav::item {{
    color: {SIDEBAR_TEXT}; padding: 10px 14px; margin: 2px 10px; border-radius: 8px;
}}
QListWidget#Nav::item:hover {{
    background: #1B2A42; color: white;
}}
QListWidget#Nav::item:selected {{
    background: {PRIMARY}; color: white; font-weight: 600;
}}
QLabel#Operator {{
    color: {SIDEBAR_TEXT}; font-size: 12px;
}}

/* ---------- Header ---------- */
QLabel#PageTitle {{
    font-size: 22px; font-weight: 700;
}}
QLabel#PageSubtitle {{
    color: {MUTED};
}}
QFrame#Stat {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px;
}}
QLabel#StatValue {{
    font-size: 22px; font-weight: 700;
}}
QLabel#StatLabel {{
    color: {MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 0.5px;
}}
QFrame#Banner {{
    background: #FDECEC; border: 1px solid #F5C2C4; border-radius: 10px;
}}
QLabel#BannerText {{
    color: #A3262B; font-weight: 600;
}}

/* ---------- Cards ---------- */
QFrame#Card {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px;
}}
QLabel#CardTitle {{
    font-size: 15px; font-weight: 700;
}}
QLabel#Hint {{
    color: {MUTED};
}}
QLabel#Muted {{
    color: {MUTED}; font-size: 12px;
}}
QLabel#InfoBox {{
    background: {PRIMARY_SOFT}; color: #1F3B66; border-radius: 8px; padding: 10px 12px;
}}
QGroupBox {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px;
    margin-top: 14px; padding: 18px 14px 12px 14px; font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {TEXT};
}}

/* ---------- Inputs ---------- */
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateTimeEdit {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 7px 10px;
    selection-background-color: {PRIMARY};
}}
QPlainTextEdit {{
    padding: 10px; font-size: 14px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDateTimeEdit:focus {{
    border: 1.5px solid {PRIMARY};
}}
QLineEdit:disabled, QComboBox:disabled, QDateTimeEdit:disabled {{
    background: #F7F8FA; color: #A0A8B8;
}}
QPlainTextEdit[readOnly="true"] {{
    background: #FAFBFC;
}}
QComboBox::drop-down, QDateTimeEdit::drop-down {{
    border: none; width: 24px;
}}
QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 5px; border: 1.5px solid #B8C2D3; background: white;
}}
QCheckBox::indicator:checked {{
    background: {PRIMARY}; border-color: {PRIMARY};
    image: url("{CHECK_ICON}");
}}
QCheckBox::indicator:hover {{
    border-color: {PRIMARY};
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 14px; font-weight: 600;
}}
QPushButton:hover {{
    background: #F2F5FA; border-color: #CBD3E1;
}}
QPushButton:pressed {{
    background: #E8EDF5;
}}
QPushButton:disabled {{
    color: #A9B1C0; background: #F7F8FA; border-color: #EDF0F4;
}}
QPushButton[variant="primary"] {{
    background: {PRIMARY}; color: white; border: 1px solid {PRIMARY};
}}
QPushButton[variant="primary"]:hover {{
    background: {PRIMARY_HOVER}; border-color: {PRIMARY_HOVER};
}}
QPushButton[variant="primary"]:disabled {{
    background: #A9C8FA; border-color: #A9C8FA; color: white;
}}
QPushButton[variant="danger"] {{
    background: {DANGER}; color: white; border: 1px solid {DANGER};
}}
QPushButton[variant="danger"]:hover {{
    background: {DANGER_HOVER};
}}
QPushButton[variant="success"] {{
    background: #1F9D55; color: white; border: 1px solid #1F9D55;
}}
QPushButton[variant="success"]:hover {{
    background: #198246;
}}
QPushButton[variant="success"]:disabled {{
    background: #A7DABD; border-color: #A7DABD; color: white;
}}
QPushButton[variant="ghost"] {{
    background: transparent; border: none; color: {PRIMARY};
}}
QPushButton[variant="ghost"]:hover {{
    background: {PRIMARY_SOFT};
}}
QPushButton#KillSwitch {{
    background: {DANGER}; color: white; border: none; border-radius: 10px; padding: 11px; font-weight: 700;
}}
QPushButton#KillSwitch:hover {{
    background: {DANGER_HOVER};
}}
QPushButton#KillSwitch[active="true"] {{
    background: #F5A524; color: #1A1200;
}}

/* ---------- Tables & lists ---------- */
QTableWidget, QListWidget#Checklist {{
    background: {SURFACE}; border: none; gridline-color: transparent;
    selection-background-color: {PRIMARY_SOFT}; selection-color: {TEXT};
    alternate-background-color: #FAFBFD;
}}
QListWidget#Checklist {{
    border: 1px solid {BORDER}; border-radius: 8px; padding: 4px;
}}
QListWidget#Checklist::item {{
    padding: 6px 4px; border-radius: 6px;
}}
QListWidget#Checklist::item:hover {{
    background: #F2F5FA;
}}
QTableWidget::item {{
    padding: 0 8px; border-bottom: 1px solid #EEF1F5;
}}
QHeaderView::section {{
    background: {SURFACE}; color: {MUTED}; font-size: 11px; font-weight: 700;
    border: none; border-bottom: 1px solid {BORDER}; padding: 9px 8px;
}}
QTableCornerButton::section {{
    background: {SURFACE}; border: none;
}}

/* ---------- Tabs (trang Lịch sử) ---------- */
QTabWidget::pane {{
    border: none;
}}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 8px 16px; margin-right: 4px;
    border-bottom: 2px solid transparent; font-weight: 600;
}}
QTabBar::tab:selected {{
    color: {PRIMARY}; border-bottom: 2px solid {PRIMARY};
}}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #CDD5E1; border-radius: 4px; min-height: 30px;
}}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #CDD5E1; border-radius: 4px; min-width: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    width: 0; height: 0; background: none;
}}
QSplitter::handle {{
    background: transparent;
}}

QDialog, QMessageBox, QInputDialog {{
    background: {SURFACE};
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(["Segoe UI", "Inter", "SF Pro Text", "Noto Sans", "Helvetica Neue", "Arial"])
    font.setPointSizeF(10)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)


# ------------------------------------------------------------------ helpers
def card(title: str | None = None, subtitle: str | None = None, margins: int = 16) -> tuple[QFrame, QVBoxLayout]:
    """Tạo thẻ trắng bo góc có bóng nhẹ. Trả về (frame, layout)."""
    frame = QFrame()
    frame.setObjectName("Card")
    shadow = QGraphicsDropShadowEffect(frame)
    shadow.setBlurRadius(18)
    shadow.setOffset(0, 2)
    shadow.setColor(QColor(15, 27, 45, 18))
    frame.setGraphicsEffect(shadow)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setObjectName("CardTitle")
        lay.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("Hint")
        s.setWordWrap(True)
        lay.addWidget(s)
    return frame, lay


def button(text: str, variant: str | None = None, slot=None) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    if variant:
        b.setProperty("variant", variant)
    if slot is not None:
        b.clicked.connect(slot)
    return b


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def repolish(widget) -> None:
    """Áp lại stylesheet sau khi đổi dynamic property."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class BadgeDelegate(QStyledItemDelegate):
    """Vẽ ô bảng dưới dạng huy hiệu bo tròn có màu theo trạng thái."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        text = index.data(Qt.DisplayRole) or ""
        key = text.replace(" 🔒", "")
        colors = BADGE_COLORS.get(key)
        if not colors:
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        f = QFont(option.font)
        f.setPointSizeF(max(8.0, option.font.pointSizeF() - 1))
        f.setBold(True)
        painter.setFont(f)
        fm = painter.fontMetrics()
        w = fm.horizontalAdvance(text) + 20
        h = fm.height() + 8
        r = option.rect
        rect = QRectF(r.x() + 8, r.y() + (r.height() - h) / 2, min(w, r.width() - 12), h)
        path = QPainterPath()
        path.addRoundedRect(rect, h / 2, h / 2)
        painter.fillPath(path, QColor(colors[0]))
        painter.setPen(QColor(colors[1]))
        painter.drawText(rect, Qt.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        s = super().sizeHint(option, index)
        return QSize(s.width() + 28, max(s.height(), 34))
