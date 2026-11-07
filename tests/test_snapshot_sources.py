"""snapshot_sources.py 테스트 — 가짜 insane-search 엔진을 주입해 네트워크 없이 검증한다."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "insane-research-main" / "scripts"

FAKE_ENGINE = '''
from dataclasses import dataclass

PAGES = {
    "https://docs.example.com/a": "The default timeout is 90 seconds in every region.",
    "https://big.example.com/b": "x" * 3_000_000,
}

@dataclass
class R:
    ok: bool
    content: str = ""
    final_url: str = ""
    verdict: str = ""
    extraction_source: str = ""

CALLS = []

def fetch(url, **kw):
    assert kw.get("enable_playwright") is False
    with open(__file__ + ".calls", "a") as f:
        f.write(url + "\\n")
    if url in PAGES:
        return R(ok=True, content=PAGES[url], final_url=url, verdict="strong_ok", extraction_source="raw")
    return R(ok=False, verdict="challenge")
'''


def make(tmp_path, claims, sources):
    eng = tmp_path / "fake_engine_root"
    (eng / "engine").mkdir(parents=True)
    (eng / "engine" / "__init__.py").write_text(FAKE_ENGINE, encoding="utf-8")
    s = tmp_path / "session"
    (s / "artifacts").mkdir(parents=True)
    (s / "sources").mkdir()
    (s / "sources" / "sources.jsonl").write_text("\n".join(json.dumps(x) for x in sources) + "\n")
    (s / "artifacts" / "claim_ledger.jsonl").write_text("\n".join(json.dumps(x) for x in claims) + "\n")
    return s, eng


def run(s, eng, browser_manifest=None, *extra):
    command = [sys.executable, str(SCRIPTS / "snapshot_sources.py"), "--session", str(s),
               "--engine-dir", str(eng)]
    if browser_manifest is not None:
        command.extend(["--browser-manifest", str(browser_manifest)])
    return subprocess.run(command + list(extra), capture_output=True, text=True)


SOURCES = [
    {"id": "src_001", "url": "https://docs.example.com/a"},
    {"id": "src_002", "url": "https://blocked.example.com/x"},
    {"id": "src_003", "url": "https://normal-only.example.com/n"},
    {"id": "src_004", "url": "https://big.example.com/b"},
]
CLAIMS = [
    {"claim_id": "clm_001", "risk": "high", "source_ids": ["src_001", "src_002"]},
    {"claim_id": "clm_002", "risk": "normal", "source_ids": ["src_003"]},
    {"claim_id": "clm_003", "risk": "high", "source_ids": ["src_004"]},
]


def load_sources(s):
    return {x["id"]: x for x in map(json.loads, (s / "sources" / "sources.jsonl").read_text().splitlines())}


def test_snapshots_only_high_risk_sources(tmp_path):
    s, eng = make(tmp_path, CLAIMS, SOURCES)
    r = run(s, eng)
    assert r.returncode == 0, r.stderr
    calls = (eng / "engine" / "__init__.py.calls").read_text().split()
    assert "https://normal-only.example.com/n" not in calls  # normal 주장만 인용한 출처는 수집 안 함
    src = load_sources(s)
    ok = src["src_001"]["snapshot"]
    assert ok["status"] == "ok" and ok["path"] == "sources/snapshots/src_001.txt"
    body = (s / ok["path"]).read_bytes()
    assert ok["sha256"] == hashlib.sha256(body).hexdigest() and ok["chars"] == len(body.decode())
    assert ok["via"] == "raw" and ok["fetched_at"]
    assert src["src_002"]["snapshot"]["status"] == "blocked"
    assert src["src_004"]["snapshot"]["status"] == "too_large"
    assert not (s / "sources" / "snapshots" / "src_004.txt").exists()
    assert "snapshot" not in src["src_003"]


def test_rerun_skips_existing_ok_snapshot(tmp_path):
    s, eng = make(tmp_path, CLAIMS, SOURCES)
    assert run(s, eng).returncode == 0
    (eng / "engine" / "__init__.py.calls").unlink()
    assert run(s, eng).returncode == 0
    calls = (eng / "engine" / "__init__.py.calls").read_text().split()
    assert "https://docs.example.com/a" not in calls  # 이미 ok면 재수집 안 함 (해시 고정)


def test_snapshot_feeds_gate_end_to_end(tmp_path):
    """스냅샷 → validate_ledger 대조까지 실제로 물린다."""
    srcs = [
        {"id": "src_001", "url": "https://docs.example.com/a", "domain": "docs.example.com",
         "type": "official_docs", "quality_rating": "A"},
        {"id": "src_002", "url": "https://bench.other.net/b", "domain": "bench.other.net",
         "type": "independent_benchmark", "quality_rating": "B"},
    ]
    claims = [{"claim_id": "clm_001", "text": "기본 타임아웃은 90초", "risk": "high", "claim_type": "numeric",
               "source_ids": ["src_001", "src_002"],
               "counter_search": {"query": "q", "urls": [], "summary": "none"},
               "evidence": [{"source_id": "src_001", "quote": "The default timeout is 90 seconds"}]}]
    s, eng = make(tmp_path, claims, srcs)
    (s / "state.json").write_text('{"ledger_schema": 2}')
    (s / "outputs").mkdir()
    assert run(s, eng).returncode == 0
    g = subprocess.run([sys.executable, str(SCRIPTS / "validate_ledger.py"), "--session", str(s)],
                       capture_output=True, text=True)
    assert g.returncode == 0, g.stderr
    verified = json.loads((s / "outputs" / "verified_claims.json").read_text())
    assert [c["claim_id"] for c in verified] == ["clm_001"]
    assert verified[0]["evidence_check"]["passed"] == 1


def test_missing_engine_exit2(tmp_path):
    s, _ = make(tmp_path, CLAIMS, SOURCES)
    r = subprocess.run([sys.executable, str(SCRIPTS / "snapshot_sources.py"), "--session", str(s),
                        "--engine-dir", str(tmp_path / "nope")], capture_output=True, text=True)
    assert r.returncode == 2
    assert "needs_browser" in r.stderr


def browser_input(session, sources, texts=None):
    """browser_use가 저장한 파일 바이트와 manifest를 준비해요."""
    raw = session / "sources" / "browser"
    raw.mkdir(exist_ok=True)
    entries = []
    for src in sources:
        rel = f"sources/browser/{src['id']}.txt"
        text = (texts or {}).get(src["id"], "The default timeout is 90 seconds in every region.\n한글 원문이에요.")
        (session / rel).write_bytes(text.encode("utf-8"))
        entries.append({"id": src["id"], "url": src["url"], "final_url": src["url"], "path": rel})
    manifest = session / "sources" / "browser_manifest.json"
    manifest.write_text(json.dumps({"sources": entries}), encoding="utf-8")
    return "sources/browser_manifest.json", entries


def save_manifest(session, entries):
    (session / "sources" / "browser_manifest.json").write_text(
        json.dumps({"sources": entries}), encoding="utf-8")


def test_browser_only_fresh_install_preserves_exact_bytes(tmp_path):
    s, _ = make(tmp_path, CLAIMS, SOURCES)
    selected = [SOURCES[n] for n in (0, 1, 3)]
    manifest, entries = browser_input(s, selected)
    r = run(s, tmp_path / "not-installed", manifest)
    assert r.returncode == 0, r.stderr
    sources = load_sources(s)
    for item in entries:
        rec = sources[item["id"]]["snapshot"]
        data = (s / item["path"]).read_bytes()
        assert (s / rec["path"]).read_bytes() == data
        assert rec["sha256"] == hashlib.sha256(data).hexdigest()
        assert rec["chars"] == len(data.decode("utf-8"))
        assert rec["status"] == "ok" and rec["via"] == "browser_use"
        assert rec["url"] == item["url"] and rec["final_url"] == item["final_url"]
        assert rec["fetched_at"]
    assert "snapshot" not in sources["src_003"]


def test_complete_browser_input_never_imports_optional_engine(tmp_path):
    s, eng = make(tmp_path, CLAIMS, SOURCES)
    (eng / "engine" / "__init__.py").write_text(
        'raise RuntimeError("optional engine must not load")', encoding="utf-8")
    manifest, _ = browser_input(s, [SOURCES[n] for n in (0, 1, 3)])
    r = run(s, eng, manifest)
    assert r.returncode == 0, r.stderr
    assert "optional engine must not load" not in r.stderr


def test_partial_browser_input_fetches_only_remaining_targets(tmp_path):
    s, eng = make(tmp_path, CLAIMS, SOURCES)
    manifest, _ = browser_input(s, [SOURCES[1]])
    r = run(s, eng, manifest)
    assert r.returncode == 0, r.stderr
    calls = (eng / "engine" / "__init__.py.calls").read_text().splitlines()
    assert calls == [SOURCES[0]["url"], SOURCES[3]["url"]]
    assert load_sources(s)["src_002"]["snapshot"]["via"] == "browser_use"


def test_partial_browser_input_reports_missing_sources_without_failed_overwrite(tmp_path):
    s, _ = make(tmp_path, CLAIMS, SOURCES)
    manifest, _ = browser_input(s, [SOURCES[1]])
    r = run(s, tmp_path / "missing", manifest)
    assert r.returncode == 2 and "needs_browser" in r.stderr
    assert "src_001" in r.stderr and "src_004" in r.stderr
    sources = load_sources(s)
    assert sources["src_002"]["snapshot"]["status"] == "ok"
    assert "snapshot" not in sources["src_001"]
    assert "snapshot" not in sources["src_004"]


@pytest.mark.parametrize("change", [
    {"id": "unknown"}, {"url": "https://different.example/a"},
    {"url": 1}, {"final_url": None}, {"path": ["sources/browser/src_001.txt"]},
    {"final_url": "file:///etc/passwd"}, {"final_url": "https://"},
    {"unexpected": "field"},
])
def test_invalid_browser_record_is_rejected_before_any_import(tmp_path, change):
    s, eng = make(tmp_path, CLAIMS, SOURCES)
    manifest, entries = browser_input(s, [SOURCES[0]])
    before = (s / "sources/sources.jsonl").read_bytes()
    entries[0].update(change)
    save_manifest(s, entries)
    r = run(s, eng, manifest)
    assert r.returncode == 2, r.stderr
    assert (s / "sources/sources.jsonl").read_bytes() == before
    assert not (eng / "engine/__init__.py.calls").exists()
    assert not (s / "sources/snapshots").exists()


@pytest.mark.parametrize("payload", [[], None, {}, {"sources": {}}, {"sources": []},
                                      {"sources": [False]}, {"sources": [], "extra": 1}])
def test_invalid_manifest_shape_is_rejected(tmp_path, payload):
    s, eng = make(tmp_path, CLAIMS, SOURCES)
    manifest, _ = browser_input(s, [SOURCES[0]])
    (s / manifest).write_text(json.dumps(payload), encoding="utf-8")
    r = run(s, eng, manifest)
    assert r.returncode == 2
    assert not (eng / "engine/__init__.py.calls").exists()


@pytest.mark.parametrize("field", ["id", "path", "url"])
def test_duplicate_browser_inputs_are_rejected(tmp_path, field):
    s, eng = make(tmp_path, [CLAIMS[0]], SOURCES)
    srcs = [dict(SOURCES[0]), dict(SOURCES[1])]
    if field == "url":
        srcs[1]["url"] = srcs[0]["url"]
        (s / "sources/sources.jsonl").write_text(
            "\n".join(json.dumps(src) for src in srcs), encoding="utf-8")
    manifest, entries = browser_input(s, srcs)
    entries[1][field] = entries[0][field]
    save_manifest(s, entries)
    r = run(s, eng, manifest)
    assert r.returncode == 2
    assert not (eng / "engine/__init__.py.calls").exists()


def test_duplicate_manifest_json_keys_are_rejected(tmp_path):
    s, eng = make(tmp_path, CLAIMS, SOURCES)
    manifest, _ = browser_input(s, [SOURCES[0]])
    (s / manifest).write_text('{"sources":[],"sources":[]}', encoding="utf-8")
    assert run(s, eng, manifest).returncode == 2


@pytest.mark.parametrize("rel", ["../outside.txt", "/etc/passwd",
                                 "sources/browser/../src_001.txt", "sources\\browser\\x"])
def test_browser_raw_path_escape_is_rejected(tmp_path, rel):
    s, eng = make(tmp_path, CLAIMS, SOURCES)
    manifest, entries = browser_input(s, [SOURCES[0]])
    entries[0]["path"] = rel
    save_manifest(s, entries)
    r = run(s, eng, manifest)
    assert r.returncode == 2
    assert not (eng / "engine/__init__.py.calls").exists()


@pytest.mark.parametrize("kind", ["file", "directory", "manifest", "output"])
def test_symlink_escape_is_rejected(tmp_path, kind):
    s, eng = make(tmp_path, CLAIMS, SOURCES)
    manifest, entries = browser_input(s, [SOURCES[0]])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "raw.txt").write_text("Original full body text.", encoding="utf-8")
    if kind == "file":
        raw = s / entries[0]["path"]
        raw.unlink()
        raw.symlink_to(outside / "raw.txt")
    elif kind == "directory":
        (s / "sources/link").symlink_to(outside, target_is_directory=True)
        entries[0]["path"] = "sources/link/raw.txt"
        save_manifest(s, entries)
    elif kind == "manifest":
        content = (s / manifest).read_bytes()
        (s / manifest).unlink()
        (outside / "manifest.json").write_bytes(content)
        (s / manifest).symlink_to(outside / "manifest.json")
    else:
        (s / "sources/snapshots").symlink_to(outside, target_is_directory=True)
    before = (s / "sources/sources.jsonl").read_bytes()
    assert run(s, eng, manifest).returncode == 2
    assert (s / "sources/sources.jsonl").read_bytes() == before
    assert not (outside / "src_001.txt").exists()


def test_manifest_path_must_be_session_relative(tmp_path):
    s, eng = make(tmp_path, CLAIMS, SOURCES)
    manifest, _ = browser_input(s, [SOURCES[0]])
    assert run(s, eng, s / manifest).returncode == 2
    assert run(s, eng, "../session/" + manifest).returncode == 2


@pytest.mark.parametrize("data", [b"", b" \n\t", b"\xff"])
def test_empty_or_invalid_utf8_raw_is_rejected(tmp_path, data):
    s, eng = make(tmp_path, CLAIMS, SOURCES)
    manifest, entries = browser_input(s, [SOURCES[0]])
    (s / entries[0]["path"]).write_bytes(data)
    assert run(s, eng, manifest).returncode == 2
    assert not (eng / "engine/__init__.py.calls").exists()


def test_raw_limit_counts_utf8_bytes_not_characters(tmp_path):
    s, eng = make(tmp_path, CLAIMS, SOURCES)
    manifest, _ = browser_input(s, [SOURCES[0]], {"src_001": "가" * 10})
    r = run(s, eng, manifest, "--max-bytes", "29")
    assert r.returncode == 2 and "29 bytes" in r.stderr
    assert not (s / "sources/snapshots").exists()


def test_manifest_size_is_bounded(tmp_path):
    s, eng = make(tmp_path, CLAIMS, SOURCES)
    manifest, _ = browser_input(s, [SOURCES[0]])
    (s / manifest).write_bytes(b" " * (2 * 1024 * 1024 + 1))
    assert run(s, eng, manifest).returncode == 2


def test_final_redirect_url_is_recorded_but_pinned_registry_url_must_match(tmp_path):
    source = dict(SOURCES[0], final_url="https://redirect.example/final")
    s, eng = make(tmp_path, [CLAIMS[0]], [source, SOURCES[1]])
    manifest, entries = browser_input(s, [source, SOURCES[1]])
    assert run(s, eng, manifest).returncode == 2
    entries[0]["final_url"] = source["final_url"]
    save_manifest(s, entries)
    r = run(s, eng, manifest)
    assert r.returncode == 0, r.stderr
    assert load_sources(s)["src_001"]["snapshot"]["final_url"] == source["final_url"]


def test_browser_rerun_preserves_entire_existing_ok_record(tmp_path):
    s, eng = make(tmp_path, [CLAIMS[0]], SOURCES[:2])
    manifest, _ = browser_input(s, SOURCES[:2])
    assert run(s, eng, manifest).returncode == 0
    before = (s / "sources/sources.jsonl").read_bytes()
    assert run(s, tmp_path / "missing", manifest).returncode == 0
    assert (s / "sources/sources.jsonl").read_bytes() == before
    assert not (eng / "engine/__init__.py.calls").exists()


@pytest.mark.parametrize("damage", ["raw", "snapshot", "sha256", "chars", "missing"])
def test_existing_ok_snapshot_is_never_silently_replaced(tmp_path, damage):
    s, eng = make(tmp_path, [CLAIMS[0]], SOURCES[:2])
    manifest, entries = browser_input(s, SOURCES[:2])
    assert run(s, eng, manifest).returncode == 0
    sources = load_sources(s)
    snapshot_path = s / sources["src_001"]["snapshot"]["path"]
    if damage == "raw":
        (s / entries[0]["path"]).write_text("Different browser body text.", encoding="utf-8")
    elif damage == "snapshot":
        snapshot_path.write_text("Tampered snapshot body.", encoding="utf-8")
    elif damage == "missing":
        snapshot_path.unlink()
    else:
        sources["src_001"]["snapshot"][damage] = "0" * 64 if damage == "sha256" else 0
        (s / "sources/sources.jsonl").write_text(
            "".join(json.dumps(src) + "\n" for src in sources.values()), encoding="utf-8")
    before = (s / "sources/sources.jsonl").read_bytes()
    r = run(s, eng, manifest if damage == "raw" else None)
    assert r.returncode == 2
    assert (s / "sources/sources.jsonl").read_bytes() == before
    assert not (eng / "engine/__init__.py.calls").exists()


def test_no_targets_or_successful_raw_does_not_report_success(tmp_path):
    s, eng = make(tmp_path, [], SOURCES)
    assert run(s, eng).returncode == 2
    (s / "artifacts/claim_ledger.jsonl").write_text(
        json.dumps({"risk": "high", "source_ids": ["src_002"]}) + "\n", encoding="utf-8")
    r = run(s, eng)
    assert r.returncode == 2
    assert load_sources(s)["src_002"]["snapshot"]["status"] == "blocked"


def test_browser_snapshot_uses_real_hash_and_quote_gate(tmp_path):
    srcs = [
        dict(SOURCES[0], domain="docs.example.com", type="official_docs", quality_rating="A"),
        dict(SOURCES[1], domain="independent.example.net", type="independent_benchmark", quality_rating="B"),
    ]
    claims = [{
        "claim_id": "clm_001", "text": "기본 타임아웃은 90초예요.", "risk": "high",
        "claim_type": "numeric", "source_ids": ["src_001", "src_002"],
        "counter_search": {"query": "timeout counterexample", "urls": [], "summary": "반증이 없어요."},
        "evidence": [{"source_id": "src_001", "quote": "The default timeout is 90 seconds"}],
    }]
    s, _ = make(tmp_path, claims, srcs)
    (s / "state.json").write_text('{"ledger_schema": 2}', encoding="utf-8")
    (s / "outputs").mkdir()
    manifest, _ = browser_input(s, srcs)
    assert run(s, tmp_path / "missing", manifest).returncode == 0
    command = [sys.executable, str(SCRIPTS / "validate_ledger.py"), "--session", str(s)]
    gate = subprocess.run(command, capture_output=True, text=True)
    assert gate.returncode == 0, gate.stderr
    verified = json.loads((s / "outputs/verified_claims.json").read_text())
    assert [claim["claim_id"] for claim in verified] == ["clm_001"]
    snapshot_path = s / load_sources(s)["src_001"]["snapshot"]["path"]
    snapshot_path.write_text("The default timeout is 90 seconds, but this file was tampered.", encoding="utf-8")
    gate = subprocess.run(command, capture_output=True, text=True)
    assert gate.returncode == 0, gate.stderr
    assert json.loads((s / "outputs/verified_claims.json").read_text()) == []
    unresolved = json.loads((s / "outputs/unresolved_claims.json").read_text())
    assert unresolved[0]["evidence_check"]["passed"] == 0


def test_browser_input_cannot_overwrite_another_sources_existing_ok_file(tmp_path):
    s, eng = make(tmp_path, [CLAIMS[0]], SOURCES)
    manifest, _ = browser_input(s, SOURCES[:2])
    preserved = s / "sources/snapshots/src_001.txt"
    preserved.parent.mkdir()
    data = b"An already pinned source snapshot."
    preserved.write_bytes(data)
    sources = load_sources(s)
    sources["src_003"]["snapshot"] = {
        "path": "sources/snapshots/src_001.txt", "status": "ok",
        "sha256": hashlib.sha256(data).hexdigest(), "chars": len(data),
    }
    (s / "sources/sources.jsonl").write_text(
        "".join(json.dumps(src) + "\n" for src in sources.values()), encoding="utf-8")
    r = run(s, eng, manifest)
    assert r.returncode == 2
    assert preserved.read_bytes() == data
    assert not (eng / "engine/__init__.py.calls").exists()
