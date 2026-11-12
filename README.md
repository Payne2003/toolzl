# Zalo Personal Marketing Bot — Module Group Posting V1.0

Phần mềm desktop hỗ trợ đăng bài marketing vào **nhóm Zalo** với quy trình **phê duyệt trước khi đăng**.

- **Công nghệ:** Python 3.10+ · PySide6 · SQLite
- **Vị trí đăng:** Nhóm Zalo (Group)
- **Quy trình:** Approve — nội dung phải được phê duyệt trước khi đăng
- **Nguyên tắc:** Ưu tiên tính năng Zalo hỗ trợ chính thức, **không vượt CAPTCHA, không giả lập API cá nhân**, và **tự động dừng** khi không đủ điều kiện.

> API của Zalo dành cho Official Account **không đồng nghĩa** với quyền tự động đăng bài bằng tài khoản
> Zalo cá nhân vào mọi nhóm. Vì vậy với tài khoản cá nhân, phần mềm dùng phương án **Manual Handoff**:
> chép nội dung, mở nhóm trong Zalo để **người dùng tự kiểm tra và bấm gửi**.

## Kiến trúc

```
PySide6 — Marketing Dashboard        Soạn nội dung · Quản lý nhóm · Hàng đợi · Lịch sử
            │
Approval Engine                       Kiểm tra nhóm được phép · Phê duyệt nội dung · Khóa phiên bản
            │
Safety Gate                           Quyền đăng · Trạng thái nhóm · Chống gửi trùng · Dừng khẩn cấp
            │
   ┌────────┴─────────┐
Manual Handoff     Official API       (API chỉ bật khi có API & quyền truy cập nhóm được Zalo xác nhận)
   └────────┬─────────┘
SQLite Audit Log                      Trạng thái · Người phê duyệt · Thời gian · Lý do dừng
```

| Thành phần | File |
|---|---|
| Dashboard (PySide6) | `zalo_marketing/ui/` |
| Approval Engine | `zalo_marketing/core/approval.py`, `dispatcher.py::enqueue` |
| Safety Gate | `zalo_marketing/core/safety.py` |
| Manual Handoff / Official API | `zalo_marketing/core/dispatcher.py`, `publishers.py` |
| SQLite + Audit Log | `zalo_marketing/core/db.py`, `audit.py` |

## Bản Windows

**Tải về:** vào tab **Actions** của repository → workflow **Build Windows** → lần chạy mới nhất →
mục *Artifacts* → `ZaloMarketing-Windows-<version>`. Trong đó có:

- `ZaloMarketing-Setup-<version>.exe` — bộ cài (không cần quyền Administrator, tạo shortcut Start Menu/Desktop).
- `ZaloMarketing-Portable-<version>.zip` — giải nén và chạy `ZaloMarketing.exe`, không cần cài đặt.

Khi push tag dạng `v1.0.0`, workflow tự tạo GitHub Release đính kèm hai file trên.

> Bản build chưa được ký số (code signing), nên lần đầu chạy Windows SmartScreen có thể cảnh báo
> → bấm **More info → Run anyway**.

**Tự build trên máy Windows:** cài Python 3.10+ (và [Inno Setup 6](https://jrsoftware.org/isinfo.php)
nếu muốn tạo bộ cài), rồi chạy:

```bat
build_windows.bat
```

Kết quả: `dist\ZaloMarketing\ZaloMarketing.exe` và (nếu có Inno Setup) `dist\ZaloMarketing-Setup-1.0.0.exe`.

### Cập nhật phần mềm

Phần mềm tự kiểm tra bản mới trên GitHub Releases khi mở (tắt được trong *Cài đặt*), hoặc bấm
**⟳ Kiểm tra cập nhật** ở cuối thanh bên. Khi có bản mới, nút **⬆ Cập nhật lên vX.Y.Z** xuất hiện:

- Bản cài bằng Setup: tải bộ cài → kiểm tra SHA-256 → cài đè → tự mở lại. Dữ liệu giữ nguyên.
- Bản portable: mở trang tải bản mới trong trình duyệt.

**Phát hành bản mới (cho người phát triển):**

1. Tăng `__version__` trong `zalo_marketing/__init__.py` và thêm mục mới vào `CHANGELOG.md`.
2. Commit, rồi push tag trùng phiên bản:

```bash
git tag v1.1.0 && git push origin v1.1.0
```

Workflow *Build Windows* sẽ build và tạo Release (ghi chú lấy từ `CHANGELOG.md`). Các máy đang chạy bản cũ
sẽ thấy nút cập nhật.

## Cài đặt & chạy từ mã nguồn

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate      # Windows: .venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

```bash
python -m zalo_marketing
```

Dữ liệu lưu tại `%APPDATA%\ZaloMarketing\zalo_marketing.db` (Windows) hoặc
`~/.local/share/ZaloMarketing/zalo_marketing.db` (Linux/macOS). Đổi bằng `--db <đường_dẫn>` hoặc biến
môi trường `ZALO_MARKETING_HOME`.

Chạy kiểm thử:

```bash
pip install -r requirements-dev.txt && pytest
```

## Quy trình sử dụng

0. **Sản phẩm & Mẫu** — điền thông tin sản phẩm quảng cáo (mặc định *Tool HanaMedia*): mô tả, tính năng,
   đối tượng, ưu đãi, giá, link, liên hệ. Chọn một mẫu trong thư viện → **Tạo bài từ mẫu** để mở bản nháp đã
   điền sẵn. Trường để trống thì dòng tương ứng trong mẫu được bỏ qua; biến không có trong hồ sơ (ví dụ
   `{van_de}`) được giữ lại để bạn tự điền — phần mềm **không cho gửi duyệt** khi còn biến chưa điền.
1. **Quản lý nhóm** — thêm nhóm bằng link mời chính thức `https://zalo.me/g/...`. Nhóm mới mặc định
   *không được phép*; bạn phải tích **“Nằm trong danh sách được phép”** và **“Đã xác nhận quyền đăng”**.
2. **Soạn nội dung** — viết bài, đính kèm **ảnh / video** (nút *Thêm ảnh / video* hoặc kéo-thả, tối đa 10 tệp;
   ảnh ≤ 25 MB, video ≤ 1 GB — giới hạn của phần mềm), bấm **Gửi duyệt**. Ảnh/video được tính vào mã khóa
   phiên bản: đổi tệp sau khi duyệt sẽ phải duyệt lại.
3. **Phê duyệt** — người duyệt xem đúng bản sẽ gửi và bấm **Duyệt & khóa phiên bản** (hoặc **Từ chối**
   kèm lý do). Có thể bật *nguyên tắc 4 mắt* (người duyệt ≠ người soạn).
4. **Hàng đợi** — chọn nội dung đã duyệt + các nhóm, bấm **Xếp lệnh** (có thể hẹn giờ).
5. Bấm **▶ Bàn giao lệnh tiếp theo**: Safety Gate kiểm tra lần cuối → nội dung được chép vào clipboard →
   Zalo mở tới nhóm. Bạn **tự dán, đọc lại và bấm Gửi**, rồi quay lại xác nhận
   **Tôi đã gửi** / **Chưa gửi — trả lại hàng đợi** / **Bỏ qua** (kèm lý do).
   Bài có ảnh/video: bấm **Chép N ảnh/video** rồi dán (Ctrl+V) vào khung chat, hoặc kéo tệp từ hộp bàn giao
   thả thẳng vào Zalo, hoặc **Mở thư mục tệp**.
6. **Lịch sử** — xem lịch sử đăng và toàn bộ nhật ký kiểm toán, xuất CSV.

## Approval Engine — khóa phiên bản

- Trạng thái: `Nháp → Chờ duyệt → Đã duyệt 🔒` (hoặc `Bị từ chối`).
- Mỗi lần nội dung thay đổi tạo một **phiên bản mới** (lưu bất biến trong `post_versions`) với mã băm SHA-256.
- Sửa nội dung đã duyệt ⇒ **hủy phê duyệt** + **hủy các lệnh đang chờ** của phiên bản cũ.
- Lệnh đăng ghi lại phiên bản & mã băm; Safety Gate chặn nếu không còn khớp với bản đã duyệt.
- Người duyệt chỉ duyệt được đúng nội dung đang hiển thị (chống đổi nội dung giữa chừng).

## Safety Gate — kiểm tra trước mỗi lần đăng

| Kiểm tra | Mặc định |
|---|---|
| Dừng khẩn cấp (nút đỏ trên cùng, bắt buộc ghi lý do) | tắt |
| Nội dung đã duyệt & đúng phiên bản | bắt buộc |
| Nhóm trong danh sách được phép · đã xác nhận quyền đăng · đang hoạt động | bắt buộc |
| Lịch hẹn giờ | — |
| Khung giờ yên lặng | 22:00 → 07:00 |
| Chống gửi trùng cùng nội dung vào cùng nhóm | 7 ngày |
| Khoảng cách tối thiểu giữa 2 lần đăng / nhóm | 60 phút |
| Tối đa mỗi nhóm / 24 giờ | 2 bài |
| Tối đa tất cả nhóm / 24 giờ | 20 bài |
| Kênh API: đã bật · nhóm được Zalo xác nhận · adapter đã cấu hình | bắt buộc |
| Tự bật dừng khẩn cấp sau N lỗi API liên tiếp | 3 |

Không đủ điều kiện ⇒ lệnh chuyển sang **Bị chặn** kèm lý do cụ thể; không có đường vòng. Khi điều kiện
được khôi phục (ví dụ hết khung giờ yên lặng) lệnh tự trở lại **Đang chờ**.

## SQLite Audit Log

Bảng `audit_log` là **chỉ-thêm** (trigger SQLite chặn `UPDATE`/`DELETE`). Mọi thao tác đều được ghi:
tạo/sửa/duyệt/từ chối nội dung, sửa nhóm, xếp/hủy/bàn giao/xác nhận lệnh, Safety Gate chặn/mở chặn,
bật/tắt dừng khẩn cấp, thay đổi cài đặt — kèm **người thực hiện, thời gian (UTC), lý do** và chi tiết JSON.

## Kênh Official API (mở rộng)

Phần mềm **không kèm sẵn endpoint nào** và không gọi API không chính thức. Kênh API bị Safety Gate chặn
cho tới khi đủ cả 3 điều kiện: bật trong Cài đặt, nhóm có *API group ID* và được đánh dấu *Zalo đã xác nhận*,
và có adapter đã cấu hình.

Khi tổ chức của bạn được Zalo cấp API và quyền truy cập nhóm, viết adapter theo đúng tài liệu Zalo đã cấp:

```python
# zalo_marketing/my_adapter.py
import os
from zalo_marketing.core.publishers import OfficialApiPublisher, PublishResult

class MyZaloAdapter(OfficialApiPublisher):
    name = "zalo-official"

    def is_configured(self) -> bool:
        return bool(os.environ.get("ZALO_ACCESS_TOKEN"))

    def publish(self, api_group_id: str, text: str) -> PublishResult:
        # Gọi endpoint chính thức theo tài liệu Zalo đã cấp cho bạn.
        ...
        return PublishResult(ok=True, external_id="...")
```

rồi trả về adapter đó trong `build_api_publisher()` ở `zalo_marketing/app.py`. Token nên đặt qua biến
môi trường, không lưu trong cơ sở dữ liệu.

## Giới hạn có chủ đích

- Không tự động thao tác giao diện Zalo, không giả lập click/bàn phím, không vượt CAPTCHA.
- Không đăng nhập hay lưu thông tin đăng nhập Zalo.
- Không gửi vào nhóm ngoài danh sách được phép.
