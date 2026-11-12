from datetime import datetime, timedelta, timezone

import pytest

from zalo_marketing.core.errors import ApprovalError, GateBlocked, ValidationError
from zalo_marketing.core.models import Channel, JobStatus, PostStatus
from zalo_marketing.core.publishers import OfficialApiPublisher, PublishResult
from zalo_marketing.core.safety import in_quiet_hours
from zalo_marketing.core.services import Services


class FakeClock:
    def __init__(self):
        # 10:00 giờ địa phương — ngoài khung giờ yên lặng mặc định
        local = datetime.now().astimezone().replace(hour=10, minute=0, second=0, microsecond=0)
        self.t = local.astimezone(timezone.utc)

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def svc(clock):
    s = Services(":memory:", clock=clock)
    yield s
    s.close()


def approved_post(svc, body="Khuyến mãi tháng 11 — giảm 20%"):
    p = svc.posts.create("KM T11", body, "an")
    svc.posts.submit(p.id, "an")
    return svc.posts.approve(p.id, "binh", expected_hash=p.content_hash)


def ok_group(svc, name="Nhóm A", link="https://zalo.me/g/abc123"):
    return svc.groups.add(name, "an", link=link, allowed=True, can_post=True)


def actions(svc):
    return [e.action for e in reversed(svc.audit.list())]


# ---------------------------------------------------------------- approval
def test_approval_flow_and_version_lock(svc):
    p = svc.posts.create("KM", "Nội dung v1", "an")
    assert p.status == PostStatus.DRAFT and p.version == 1
    with pytest.raises(ApprovalError):
        svc.posts.approve(p.id, "binh")  # chưa gửi duyệt
    svc.posts.submit(p.id, "an")
    p = svc.posts.approve(p.id, "binh", note="ok")
    assert p.approval_valid and p.is_locked

    p2 = svc.posts.edit(p.id, "KM", "Nội dung v2", "an")
    assert p2.version == 2 and p2.status == PostStatus.DRAFT and not p2.approval_valid
    assert [v["version"] for v in svc.posts.versions(p.id)] == [2, 1]


def test_rename_only_keeps_approval(svc):
    p = approved_post(svc)
    p2 = svc.posts.edit(p.id, "Tên mới", p.body + "   \n", "an")  # khoảng trắng cuối dòng bị chuẩn hóa
    assert p2.approval_valid and p2.version == p.version and p2.title == "Tên mới"


def test_approve_rejects_stale_view(svc):
    p = svc.posts.create("KM", "v1", "an")
    svc.posts.submit(p.id, "an")
    with pytest.raises(ApprovalError):
        svc.posts.approve(p.id, "binh", expected_hash="khac")


def test_four_eyes(svc):
    svc.db.set_setting("require_different_approver", True)
    p = svc.posts.create("KM", "v1", "an")
    svc.posts.submit(p.id, "an")
    with pytest.raises(ApprovalError):
        svc.posts.approve(p.id, "AN")
    assert svc.posts.approve(p.id, "binh").approval_valid


def test_reject_requires_reason(svc):
    p = svc.posts.create("KM", "v1", "an")
    svc.posts.submit(p.id, "an")
    with pytest.raises(ApprovalError):
        svc.posts.reject(p.id, "binh", "")
    assert svc.posts.reject(p.id, "binh", "Sai giá").status == PostStatus.REJECTED
    svc.posts.submit(p.id, "an")  # gửi lại được


# ------------------------------------------------------------------ groups
def test_group_link_validation(svc):
    with pytest.raises(ValidationError):
        svc.groups.add("X", "an", link="https://evil.example/g/abc")
    g = svc.groups.add("X", "an", link="")
    assert not g.allowed and not g.can_post  # mặc định an toàn


# ------------------------------------------------------------------- queue
def test_enqueue_requires_approval_and_whitelist(svc):
    p = svc.posts.create("KM", "v1", "an")
    g = ok_group(svc)
    with pytest.raises(ApprovalError):
        svc.dispatcher.enqueue(p.id, [g.id], "an")

    p = approved_post(svc)
    bad = svc.groups.add("Không phép", "an", link="https://zalo.me/g/zzz")
    r = svc.dispatcher.enqueue(p.id, [g.id, bad.id, g.id], "an")
    assert len(r.created) == 1 and r.skipped[0][0] == bad.id
    # Không tạo lệnh trùng khi lệnh cũ còn đang chờ
    r2 = svc.dispatcher.enqueue(p.id, [g.id], "an")
    assert r2.created == [] and len(r2.skipped) == 1


def test_manual_handoff_happy_path(svc):
    p, g = approved_post(svc), ok_group(svc)
    (jid,) = svc.dispatcher.enqueue(p.id, [g.id], "an").created
    pkg = svc.dispatcher.handoff(jid, "an")
    assert pkg.text == p.body and pkg.group_link == g.link
    assert svc.dispatcher.get(jid).status == JobStatus.HANDED_OFF
    job = svc.dispatcher.confirm_sent(jid, "an")
    assert job.status == JobStatus.SENT and job.completed_by == "an"
    assert {"job.enqueue", "job.handoff", "job.confirm_sent"} <= set(actions(svc))


def test_kill_switch_blocks_and_is_audited(svc):
    p, g = approved_post(svc), ok_group(svc)
    (jid,) = svc.dispatcher.enqueue(p.id, [g.id], "an").created
    with pytest.raises(ValidationError):
        svc.dispatcher.set_kill_switch(True, "an", "")
    svc.dispatcher.set_kill_switch(True, "an", "Nhóm báo spam")
    with pytest.raises(GateBlocked) as ei:
        svc.dispatcher.handoff(jid, "an")
    assert any("Dừng khẩn cấp" in r for r in ei.value.reasons)
    assert svc.dispatcher.get(jid).status == JobStatus.BLOCKED
    svc.dispatcher.set_kill_switch(False, "an", "Đã xử lý")
    svc.dispatcher.refresh()
    assert svc.dispatcher.get(jid).status == JobStatus.QUEUED
    entry = svc.audit.list(action="kill_switch.on")[0]
    assert entry.reason == "Nhóm báo spam" and entry.actor == "an"


def test_group_permission_revoked_blocks(svc):
    p, g = approved_post(svc), ok_group(svc)
    (jid,) = svc.dispatcher.enqueue(p.id, [g.id], "an").created
    svc.groups.update(g.id, "an", can_post=False, reason="Admin tắt quyền đăng")
    res = svc.dispatcher.check(jid)
    assert not res.ok and any("quyền đăng" in r for r in res.reasons)
    svc.groups.update(g.id, "an", status="paused")
    assert any("paused" in r for r in svc.dispatcher.check(jid).reasons)


def test_edit_after_approval_cancels_pending_jobs(svc):
    p, g = approved_post(svc), ok_group(svc)
    (jid,) = svc.dispatcher.enqueue(p.id, [g.id], "an").created
    svc.posts.edit(p.id, p.title, "Nội dung đã sửa", "an")
    assert svc.dispatcher.get(jid).status == JobStatus.CANCELLED


def test_edit_does_not_cancel_handed_off_job(svc):
    p, g = approved_post(svc), ok_group(svc)
    (jid,) = svc.dispatcher.enqueue(p.id, [g.id], "an").created
    svc.dispatcher.handoff(jid, "an")
    svc.posts.edit(p.id, p.title, "Nội dung đã sửa", "an")
    assert svc.dispatcher.get(jid).status == JobStatus.HANDED_OFF


def test_dedupe_and_rate_limits(svc, clock):
    svc.db.set_setting("min_interval_minutes", 60)
    p, g = approved_post(svc), ok_group(svc)
    (j1,) = svc.dispatcher.enqueue(p.id, [g.id], "an").created
    svc.dispatcher.handoff(j1, "an")
    svc.dispatcher.confirm_sent(j1, "an")

    # Cùng nội dung, cùng nhóm → chặn trùng (7 ngày)
    (j2,) = svc.dispatcher.enqueue(p.id, [g.id], "an").created
    reasons = svc.dispatcher.check(j2).reasons
    assert any("đã gửi vào nhóm" in r for r in reasons)
    assert any("Chưa đủ 60 phút" in r for r in reasons)
    clock.advance(days=8)
    assert svc.dispatcher.check(j2).ok


def test_per_group_and_daily_limits(svc, clock):
    svc.db.set_setting("min_interval_minutes", 0)
    svc.db.set_setting("per_group_daily_limit", 1)
    svc.db.set_setting("daily_limit", 2)
    g1, g2, g3 = ok_group(svc, "A", "https://zalo.me/g/a"), ok_group(svc, "B", "https://zalo.me/g/b"), \
        ok_group(svc, "C", "https://zalo.me/g/c")
    p1 = approved_post(svc, "bài 1")
    p2 = approved_post(svc, "bài 2")
    ja, jb, jc = svc.dispatcher.enqueue(p1.id, [g1.id, g2.id, g3.id], "an").created
    svc.dispatcher.handoff(ja, "an")
    (ja2,) = svc.dispatcher.enqueue(p2.id, [g1.id], "an").created
    assert any("1 bài / 24 giờ" in r for r in svc.dispatcher.check(ja2).reasons)
    svc.dispatcher.handoff(jb, "an")
    assert any("tất cả các nhóm" in r for r in svc.dispatcher.check(jc).reasons)


def test_quiet_hours():
    base = datetime(2026, 1, 1)
    assert in_quiet_hours(base.replace(hour=23), "22:00", "07:00")
    assert in_quiet_hours(base.replace(hour=6, minute=59), "22:00", "07:00")
    assert not in_quiet_hours(base.replace(hour=7), "22:00", "07:00")
    assert in_quiet_hours(base.replace(hour=13), "12:00", "14:00")
    assert not in_quiet_hours(base.replace(hour=13), "", "")


def test_schedule_waits_without_blocking(svc, clock):
    p, g = approved_post(svc), ok_group(svc)
    (jid,) = svc.dispatcher.enqueue(p.id, [g.id], "an", scheduled_at=clock() + timedelta(hours=2)).created
    res = svc.dispatcher.refresh()[jid]
    assert res.waiting and svc.dispatcher.get(jid).status == JobStatus.QUEUED
    assert svc.dispatcher.next_ready() is None
    clock.advance(hours=2)
    assert svc.dispatcher.next_ready().id == jid


def test_skip_and_return_to_queue(svc):
    p, g = approved_post(svc), ok_group(svc)
    (jid,) = svc.dispatcher.enqueue(p.id, [g.id], "an").created
    svc.dispatcher.handoff(jid, "an")
    svc.dispatcher.return_to_queue(jid, "an")
    assert svc.dispatcher.get(jid).status == JobStatus.QUEUED
    svc.dispatcher.handoff(jid, "an")
    with pytest.raises(ValidationError):
        svc.dispatcher.skip(jid, "an", "")
    assert svc.dispatcher.skip(jid, "an", "Nhóm đang tranh luận").status == JobStatus.SKIPPED


def test_audit_log_is_append_only(svc):
    import sqlite3
    svc.groups.add("X", "an")
    with pytest.raises(sqlite3.DatabaseError):
        svc.db.execute("DELETE FROM audit_log")
    with pytest.raises(sqlite3.DatabaseError):
        svc.db.execute("UPDATE audit_log SET actor = 'x'")


# ------------------------------------------------------------- official api
def test_api_channel_blocked_by_default(svc):
    p = approved_post(svc)
    g = ok_group(svc)
    r = svc.dispatcher.enqueue(p.id, [g.id], "an", channel=Channel.OFFICIAL_API)
    assert r.created == [] and "API" in r.skipped[0][1]


class FlakyPublisher(OfficialApiPublisher):
    def __init__(self, ok):
        self.ok = ok

    def is_configured(self):
        return True

    def publish(self, api_group_id, text):
        if self.ok:
            return PublishResult(ok=True, external_id="m1")
        raise RuntimeError("HTTP 500")


def _api_setup(clock, ok):
    s = Services(":memory:", clock=clock, api_publisher=FlakyPublisher(ok))
    s.db.set_setting("official_api_enabled", True)
    s.db.set_setting("min_interval_minutes", 0)
    s.db.set_setting("auto_stop_after_failures", 2)
    gs = []
    for i in range(3):
        g = ok_group(s, f"G{i}", f"https://zalo.me/g/x{i}")
        s.groups.update(g.id, "an", api_group_id=f"gid{i}", api_verified=True)
        gs.append(g.id)
    p = approved_post(s)
    return s, s.dispatcher.enqueue(p.id, gs, "an", channel=Channel.OFFICIAL_API).created


def test_api_send_success(clock):
    s, jobs = _api_setup(clock, ok=True)
    assert s.dispatcher.send_via_api(jobs[0], "an").status == JobStatus.SENT


def test_api_failures_trigger_auto_stop(clock):
    s, jobs = _api_setup(clock, ok=False)
    assert s.dispatcher.send_via_api(jobs[0], "an").status == JobStatus.FAILED
    assert not s.db.get_setting("kill_switch")
    s.dispatcher.send_via_api(jobs[1], "an")
    assert s.db.get_setting("kill_switch")
    with pytest.raises(GateBlocked):
        s.dispatcher.send_via_api(jobs[2], "an")
    assert s.audit.list(action="kill_switch.on")[0].actor == "system"


# --------------------------------------------------------------- templates
def test_template_render_fills_and_drops_empty_optional_lines():
    from zalo_marketing.core.templates import render, DEFAULT_PROFILE
    profile = {**DEFAULT_PROFILE, "link": "https://hanamedia.example", "tinh_nang": "Đăng lịch\n- Thống kê"}
    out = render("🚀 {ten_san_pham}\n💰 Giá: {gia}\n{tinh_nang}\n👉 {link}\n❓ {van_de}", profile)
    assert "Tool HanaMedia" in out and "Giá" not in out
    assert "✅ Đăng lịch\n✅ Thống kê" in out
    assert "{van_de}" in out  # biến ngoài hồ sơ giữ nguyên để người soạn điền


def test_builtin_templates_seeded_once_and_apply(svc):
    names = [t.name for t in svc.templates.list()]
    assert "Giới thiệu sản phẩm" in names
    svc.templates.delete(svc.templates.list()[0].id, "an")
    from zalo_marketing.core.templates import TemplateRepository
    TemplateRepository(svc.db, svc.audit)  # không seed lại
    assert len(svc.templates.list()) == len(names) - 1
    svc.templates.save_profile("an", {"ten_san_pham": "Tool HanaMedia", "mo_ta_ngan": "Trợ lý đăng bài",
                                      "uu_dai": "Giảm 30%", "link": "https://hanamedia.example"})
    tin_ngan = next(t for t in svc.templates.list() if t.name == "Tin ngắn")
    title, body = svc.templates.apply(tin_ngan.id)
    assert title == "Tool HanaMedia — Tin ngắn"
    assert body == "⚡ Tool HanaMedia — Trợ lý đăng bài\n🎁 Giảm 30%\n👉 https://hanamedia.example"


def test_profile_link_validation(svc):
    with pytest.raises(ValidationError):
        svc.templates.save_profile("an", {"link": "hanamedia.vn"})


def test_submit_blocked_with_unfilled_placeholders(svc):
    p = svc.posts.create("KM", "Bạn đang gặp {van_de}?", "an")
    with pytest.raises(ApprovalError):
        svc.posts.submit(p.id, "an")
