"""Hồ sơ sản phẩm quảng cáo & thư viện mẫu bài viết.

Mẫu dùng biến dạng {ten_bien}. Khi áp dụng mẫu:
* Biến có trong hồ sơ sản phẩm và có giá trị → được thay thế.
* Biến có trong hồ sơ nhưng đang để trống → cả dòng chứa biến đó bị bỏ (trường tùy chọn).
* Biến không có trong hồ sơ → giữ nguyên để người soạn tự điền; Approval Engine sẽ
  không cho gửi duyệt khi nội dung vẫn còn biến chưa điền.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .audit import AuditLog
from .db import Database
from .errors import NotFound, ValidationError

PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")

PROFILE_FIELDS: list[tuple[str, str, str]] = [
    # (khóa, nhãn, gợi ý)
    ("ten_san_pham", "Tên sản phẩm", "Tool HanaMedia"),
    ("mo_ta_ngan", "Mô tả ngắn (1 câu)", "Công cụ hỗ trợ … dành cho …"),
    ("tinh_nang", "Tính năng nổi bật (mỗi dòng một ý)", "Tính năng 1\nTính năng 2\nTính năng 3"),
    ("doi_tuong", "Dành cho ai", "Chủ shop online, người làm nội dung…"),
    ("uu_dai", "Ưu đãi hiện tại", "Giảm 30% cho 50 khách đầu tiên"),
    ("han_uu_dai", "Hạn ưu đãi", "30/11"),
    ("gia", "Giá", "từ 199.000đ/tháng"),
    ("link", "Link đăng ký / dùng thử", "https://…"),
    ("lien_he", "Liên hệ (Zalo / hotline)", "Zalo 09xx xxx xxx"),
]

DEFAULT_PROFILE: dict[str, str] = {k: "" for k, _, _ in PROFILE_FIELDS}
DEFAULT_PROFILE["ten_san_pham"] = "Tool HanaMedia"

# Mẫu dựng sẵn cho quảng cáo Tool HanaMedia. Chỉ dùng thông tin từ hồ sơ sản phẩm —
# không tự bịa tính năng, số liệu hay lời khen của khách hàng.
BUILTIN_TEMPLATES: list[tuple[str, str]] = [
    ("Giới thiệu sản phẩm", """🚀 {ten_san_pham} — {mo_ta_ngan}

👥 Dành cho: {doi_tuong}

✨ Tính năng nổi bật:
{tinh_nang}

🎁 {uu_dai}
💰 Giá: {gia}

👉 Đăng ký / dùng thử: {link}
📞 Hỗ trợ: {lien_he}"""),
    ("Ưu đãi có thời hạn", """🔥 ƯU ĐÃI {ten_san_pham}

🎁 {uu_dai}
⏰ Áp dụng đến hết {han_uu_dai}
💰 Giá: {gia}

Những gì bạn nhận được:
{tinh_nang}

👉 Nhận ưu đãi tại: {link}
📞 Cần tư vấn, nhắn ngay: {lien_he}"""),
    ("Giải quyết vấn đề", """❓ Bạn đang mất nhiều thời gian cho {van_de}?

{ten_san_pham} giúp bạn:
{tinh_nang}

👥 Phù hợp với: {doi_tuong}

👉 Tìm hiểu thêm: {link}
📞 {lien_he}"""),
    ("Hướng dẫn nhanh", """📘 Bắt đầu với {ten_san_pham} chỉ trong 3 bước:

1️⃣ Đăng ký tại: {link}
2️⃣ {buoc_2}
3️⃣ {buoc_3}

Cần hỗ trợ cài đặt? Nhắn {lien_he} — đội ngũ sẽ hướng dẫn tận tình 💬"""),
    ("Cập nhật phiên bản mới", """🆕 {ten_san_pham} vừa cập nhật!

Có gì mới:
{tinh_nang_moi}

🎁 {uu_dai}
👉 Cập nhật / dùng thử: {link}"""),
    ("Tin ngắn", """⚡ {ten_san_pham} — {mo_ta_ngan}
🎁 {uu_dai}
👉 {link}"""),
]


def find_placeholders(text: str) -> list[str]:
    return list(dict.fromkeys(PLACEHOLDER_RE.findall(text or "")))


def _format_value(key: str, value: str) -> str:
    value = value.strip()
    if key in ("tinh_nang", "tinh_nang_moi"):
        items = [line.strip(" -•✅*\t") for line in value.splitlines() if line.strip()]
        return "\n".join(f"✅ {item}" for item in items)
    return value


def render(body: str, profile: dict[str, str]) -> str:
    out: list[str] = []
    for line in body.splitlines():
        keys = PLACEHOLDER_RE.findall(line)
        if any(k in profile and not (profile.get(k) or "").strip() for k in keys):
            continue  # trường tùy chọn đang trống → bỏ cả dòng
        out.append(PLACEHOLDER_RE.sub(
            lambda m: _format_value(m.group(1), profile[m.group(1)]) if (profile.get(m.group(1)) or "").strip()
            else m.group(0), line))
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)  # gộp các dòng trống thừa sau khi bỏ dòng
    return text.strip()


@dataclass
class Template:
    id: int
    name: str
    body: str
    builtin: bool


class TemplateRepository:
    def __init__(self, db: Database, audit: AuditLog):
        self.db = db
        self.audit = audit
        self._seed()

    def _seed(self) -> None:
        if self.db.query_one("SELECT 1 FROM meta WHERE key = 'templates_seeded'"):
            return
        now = self.db.now_iso()
        with self.db.transaction():
            for name, body in BUILTIN_TEMPLATES:
                self.db.execute("INSERT INTO templates(name, body, builtin, created_at) VALUES (?, ?, 1, ?)",
                                (name, body, now))
            self.db.execute("INSERT INTO meta(key, value) VALUES ('templates_seeded', '1')")

    # ------------------------------------------------------------ templates
    def list(self) -> list[Template]:
        return [Template(r["id"], r["name"], r["body"], bool(r["builtin"]))
                for r in self.db.query("SELECT * FROM templates ORDER BY builtin DESC, id")]

    def get(self, template_id: int) -> Template:
        r = self.db.query_one("SELECT * FROM templates WHERE id = ?", (template_id,))
        if r is None:
            raise NotFound(f"Không tìm thấy mẫu #{template_id}")
        return Template(r["id"], r["name"], r["body"], bool(r["builtin"]))

    def add(self, name: str, body: str, actor: str) -> Template:
        name, body = (name or "").strip(), (body or "").strip()
        if not name or not body:
            raise ValidationError("Tên mẫu và nội dung mẫu không được để trống.")
        with self.db.transaction():
            cur = self.db.execute("INSERT INTO templates(name, body, builtin, created_at) VALUES (?, ?, 0, ?)",
                                  (name, body, self.db.now_iso()))
            tid = int(cur.lastrowid)
            self.audit.record(actor, "template.create", "template", tid, name=name)
        return self.get(tid)

    def delete(self, template_id: int, actor: str) -> None:
        t = self.get(template_id)
        with self.db.transaction():
            self.db.execute("DELETE FROM templates WHERE id = ?", (template_id,))
            self.audit.record(actor, "template.delete", "template", template_id, name=t.name)

    # -------------------------------------------------------------- profile
    def profile(self) -> dict[str, str]:
        stored = self.db.get_setting("brand_profile") or {}
        return {**DEFAULT_PROFILE, **{k: v for k, v in stored.items() if k in DEFAULT_PROFILE}}

    def save_profile(self, actor: str, values: dict[str, str]) -> None:
        new = {k: (values.get(k) or "").strip() for k in DEFAULT_PROFILE}
        link = new["link"]
        if link and not re.match(r"^https?://\S+$", link):
            raise ValidationError("Link phải bắt đầu bằng http:// hoặc https://")
        old = self.profile()
        changed = sorted(k for k in new if new[k] != old.get(k))
        if not changed:
            return
        with self.db.transaction():
            self.db.set_setting("brand_profile", new)
            self.audit.record(actor, "profile.update", "system", None, fields=changed)

    def apply(self, template_id: int) -> tuple[str, str]:
        """Trả về (tiêu đề gợi ý, nội dung đã điền)."""
        t = self.get(template_id)
        p = self.profile()
        title = f"{p['ten_san_pham'] or 'Sản phẩm'} — {t.name}"
        return title, render(t.body, p)
