import hashlib

import pytest

from zalo_marketing.core import updater
from zalo_marketing.core.updater import UpdateError, is_newer, parse_release, parse_version


def test_version_compare():
    assert parse_version("v1.2") == (1, 2, 0)
    assert is_newer("v1.0.1", "1.0.0")
    assert is_newer("1.10.0", "1.9.9")
    assert not is_newer("v1.0.0", "1.0.0")
    assert not is_newer("0.9.0-beta", "1.0.0")
    with pytest.raises(UpdateError):
        parse_version("latest")


def release(tag="v1.1.0", **kw):
    data = {
        "tag_name": tag, "body": "- Sửa lỗi", "published_at": "2026-11-20T00:00:00Z",
        "html_url": "https://github.com/x/y/releases/tag/" + tag,
        "assets": [
            {"name": "ZaloMarketing-Setup-1.1.0.exe", "browser_download_url": "https://e.x/s.exe",
             "size": 123, "digest": "sha256:ABC"},
            {"name": "ZaloMarketing-Portable-1.1.0.zip", "browser_download_url": "https://e.x/p.zip"},
        ],
    }
    data.update(kw)
    return data


def test_parse_release():
    info = parse_release(release())
    assert info.version == "1.1.0" and info.sha256 == "abc"
    assert info.setup_url == "https://e.x/s.exe" and info.portable_url == "https://e.x/p.zip"
    with pytest.raises(UpdateError):
        parse_release(release(prerelease=True))


def test_check_for_update(monkeypatch):
    import io, json

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr(updater, "_get", lambda url, accept=None: Resp(json.dumps(release()).encode()))
    assert updater.check_for_update(current="1.0.0").version == "1.1.0"
    assert updater.check_for_update(current="1.1.0") is None
    with pytest.raises(UpdateError):
        updater.check_for_update("http://insecure.example")


def test_download_verifies_sha256(tmp_path, monkeypatch):
    payload = b"installer-bytes" * 1000

    class Resp:
        headers = {"Content-Length": str(len(payload))}
        def __init__(self): self.pos = 0
        def read(self, n):
            chunk = payload[self.pos:self.pos + n]; self.pos += n; return chunk
        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr(updater, "_get", lambda url, accept=None: Resp())
    good = hashlib.sha256(payload).hexdigest()
    seen = []
    out = updater.download("https://e.x/s.exe", tmp_path / "s.exe", good, lambda d, t: seen.append(d) or True)
    assert out.read_bytes() == payload and seen[-1] == len(payload)
    with pytest.raises(UpdateError):
        updater.download("https://e.x/s.exe", tmp_path / "bad.exe", "0" * 64)
    assert not (tmp_path / "bad.exe").exists() and not (tmp_path / "bad.exe.part").exists()
    with pytest.raises(UpdateError):
        updater.download("https://e.x/s.exe", tmp_path / "c.exe", progress=lambda d, t: False)
