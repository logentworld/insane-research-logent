#!/usr/bin/env python3
"""고위험 주장 출처의 원문을 저장해요.

browser_use가 직접 저장한 UTF-8 원문을 --browser-manifest로 먼저 가져와요.
나머지 대상은 선택적 insane-search 엔진의 HTTP 전용 fetch로 받아요.
기존 ok 원문은 파일·해시를 확인하고 고정하며, 검증 게이트는 그대로 유지해요.
입력 오류나 수집 가능한 원문이 없으면 종료 코드 2를 반환해요.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import stat
import tempfile
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES_DEFAULT = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024


class InputError(ValueError):
    """원문 입력 계약 위반을 알려요."""


def _session_file(session, rel, must_exist=True):
    if (not isinstance(rel, str) or not rel or "\\" in rel
            or any(part in ("", ".", "..") for part in rel.split("/"))
            or Path(rel).is_absolute()):
        raise InputError(f"세션 상대 파일 경로를 지정해 주세요: {rel!r}")
    root = Path(session).resolve(strict=True)
    path = root / rel
    current = root
    for part in rel.split("/"):
        current = current / part
        if current.is_symlink():
            raise InputError(f"심볼릭 링크 원문 경로는 사용할 수 없어요: {rel}")
    if not path.resolve().is_relative_to(root):
        raise InputError(f"세션 밖 경로는 사용할 수 없어요: {rel}")
    if must_exist and not path.is_file():
        raise InputError(f"입력 파일이 없어요: {rel}")
    return path


def _read_bytes(path, limit):
    with open(path, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise InputError(f"일반 파일 원문만 사용할 수 있어요: {path.name}")
        data = f.read(limit + 1)
    if len(data) > limit:
        raise InputError(f"원문/manifest가 최대 {limit} bytes를 넘어요: {path.name}")
    return data


def _http_url(value):
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme in ("http", "https") and bool(parsed.hostname)
                and not parsed.username and not parsed.password
                and not any(c.isspace() or ord(c) < 32 for c in value))
    except ValueError:
        return False


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"중복 JSON 키를 사용할 수 없어요: {key}")
        result[key] = value
    return result


def _browser_inputs(session, manifest, by_id, max_bytes):
    if manifest is None:
        return {}
    manifest_path = _session_file(session, manifest)
    payload = json.loads(_read_bytes(manifest_path, MAX_MANIFEST_BYTES).decode("utf-8"),
                         object_pairs_hook=_unique_object)
    if (not isinstance(payload, dict) or set(payload) != {"sources"}
            or not isinstance(payload["sources"], list) or not payload["sources"]):
        raise InputError('browser manifest는 비어 있지 않은 {"sources": [...]} 객체여야 해요.')
    result, paths, urls = {}, set(), set()
    for item in payload["sources"]:
        if (not isinstance(item, dict) or set(item) != {"id", "url", "final_url", "path"}
                or any(not isinstance(v, str) or not v for v in item.values())):
            raise InputError("browser 출처에는 문자열 id, url, final_url, path가 필요해요.")
        sid = item["id"]
        if sid not in by_id:
            raise InputError(f"등록되지 않은 browser 출처 id예요: {sid}")
        if not _http_url(item["url"]) or not _http_url(item["final_url"]):
            raise InputError(f"browser 출처에는 공개 HTTP(S) URL이 필요해요: {sid}")
        if item["url"] != by_id[sid].get("url"):
            raise InputError(f"출처 레지스트리와 browser URL이 달라요: {sid}")
        if by_id[sid].get("final_url") not in (None, "", item["final_url"]):
            raise InputError(f"출처 레지스트리와 browser 최종 URL이 달라요: {sid}")
        path = _session_file(session, item["path"])
        if path == manifest_path or sid in result or path in paths or item["url"] in urls:
            raise InputError(f"browser 원문 입력이 중복됐어요: {sid}")
        data = _read_bytes(path, max_bytes)
        text = data.decode("utf-8")
        if not text.strip():
            raise InputError(f"browser 원문이 비어 있어요: {sid}")
        paths.add(path)
        urls.add(item["url"])
        result[sid] = (item, data, text)
    return result


def _write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = f.name
        try:
            f.write(data)
            f.close()
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _write_sources(path, sources):
    data = "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in sources).encode("utf-8")
    _write_bytes(path, data)


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _find_engine_dir(explicit):
    if explicit:
        return explicit
    env = os.environ.get("INSANE_SEARCH_ENGINE_DIR")
    if env:
        return env
    for candidate in ("~/.logent/plugins/insane-search/engine", "~/.logent/plugins/insane-search"):
        path = os.path.expanduser(candidate)
        if os.path.isfile(os.path.join(path, "__main__.py")) or os.path.isdir(os.path.join(path, "engine")):
            return path
    pattern = os.path.expanduser("~/.claude/plugins/cache/*/insane-search/*/skills/insane-search")
    found = sorted(glob.glob(pattern), key=lambda p: [int(x) if x.isdigit() else -1
                                                      for x in p.split("/")[-3].split(".")])
    return found[-1] if found else None


def _load_fetch(engine_dir):
    root = None
    if engine_dir and os.path.isdir(engine_dir):
        if os.path.isfile(os.path.join(engine_dir, "__main__.py")):
            root = os.path.dirname(engine_dir)
        elif os.path.isdir(os.path.join(engine_dir, "engine")):
            root = engine_dir
    if root is None:
        return None
    sys.path.insert(0, root)
    try:
        from engine import fetch  # type: ignore  # noqa: E402
    except Exception as e:  # pragma: no cover - 환경 문제 보고용
        print(f"엔진을 import하지 못했어요: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    return fetch


def target_ids(claims):
    ids = []
    for claim in claims:
        if not isinstance(claim, dict):
            raise InputError("주장 원장에는 JSON 객체가 필요해요.")
        if claim.get("risk") != "high":
            continue
        source_ids = claim.get("source_ids")
        if (not isinstance(source_ids, list) or not source_ids
                or any(not isinstance(sid, str) for sid in source_ids)):
            raise InputError("고위험 주장에는 비어 있지 않은 문자열 source_ids가 필요해요.")
        for sid in source_ids:
            if sid not in ids:
                ids.append(sid)
    return ids


def snapshot(session, fetch=None, max_bytes=MAX_BYTES_DEFAULT, timeout=25,
             browser_manifest=None, engine_dir=None):
    if type(max_bytes) is not int or max_bytes <= 0 or timeout <= 0:
        raise InputError("max-bytes와 timeout에는 양수를 지정해 주세요.")
    sources_path = _session_file(session, "sources/sources.jsonl")
    sources = _read_jsonl(sources_path)
    claims = _read_jsonl(_session_file(session, "artifacts/claim_ledger.jsonl"))
    by_id = {}
    for src in sources:
        if (not isinstance(src, dict) or not isinstance(src.get("id"), str)
                or not re.fullmatch(r"[A-Za-z0-9_-]+", src["id"])
                or src["id"] in by_id):
            raise InputError("출처 id는 중복 없는 영문·숫자·밑줄·하이픈 문자열이어야 해요.")
        by_id[src["id"]] = src
    targets = target_ids(claims)
    for sid in targets:
        if sid not in by_id or not _http_url(by_id[sid].get("url")):
            raise InputError(f"고위험 주장 출처의 등록 id와 HTTP(S) URL을 확인해 주세요: {sid}")
    browser = _browser_inputs(session, browser_manifest, by_id, max_bytes)
    selected = list(dict.fromkeys([*browser, *targets]))
    if not selected:
        raise InputError("수집할 고위험 출처나 browser 원문 입력이 없어요.")

    counts = {"ok": 0, "blocked": 0, "too_large": 0, "error": 0, "skipped": 0}
    existing = set()
    outputs = {}
    for sid in selected:
        src = by_id[sid]
        prev = src.get("snapshot")
        if prev is None:
            prev = {}
        if not isinstance(prev, dict):
            raise InputError(f"snapshot은 객체여야 해요: {sid}")
        if prev.get("status") == "ok":
            path = _session_file(session, prev.get("path"))
            data = _read_bytes(path, max_bytes)
            text = data.decode("utf-8")
            digest = hashlib.sha256(data).hexdigest()
            if (not text.strip() or prev.get("sha256") != digest
                    or type(prev.get("chars")) is not int or prev["chars"] != len(text)):
                raise InputError(f"기존 ok snapshot의 파일·해시·chars가 달라요. 덮어쓰지 않아요: {sid}")
            if sid in browser and hashlib.sha256(browser[sid][1]).hexdigest() != digest:
                raise InputError(f"browser 원문이 기존 ok snapshot 해시와 달라요. 덮어쓰지 않아요: {sid}")
            existing.add(sid)
            counts["skipped"] += 1
        else:
            outputs[sid] = _session_file(session, f"sources/snapshots/{sid}.txt", must_exist=False)
            for other_id, other in by_id.items():
                other_snapshot = other.get("snapshot")
                if (other_id != sid and isinstance(other_snapshot, dict)
                        and other_snapshot.get("status") == "ok"
                        and outputs[sid] == _session_file(session, other_snapshot.get("path"))):
                    raise InputError(f"다른 출처의 기존 ok 원문 경로를 덮어쓸 수 없어요: {sid}")

    for sid, (item, data, text) in browser.items():
        if sid in existing:
            continue
        _write_bytes(outputs[sid], data)
        by_id[sid]["snapshot"] = {
            "path": f"sources/snapshots/{sid}.txt", "status": "ok",
            "sha256": hashlib.sha256(data).hexdigest(), "chars": len(text),
            "fetched_at": datetime.now(timezone.utc).isoformat(), "via": "browser_use",
            "url": item["url"], "final_url": item["final_url"],
        }
        counts["ok"] += 1

    pending = [sid for sid in targets if sid not in existing and sid not in browser]
    if pending and fetch is None:
        fetch = _load_fetch(_find_engine_dir(engine_dir))
    if pending and fetch is None:
        if counts["ok"]:
            _write_sources(sources_path, sources)
        raise InputError("needs_browser: HTTP 엔진이 없어요. browser_use로 전체 원문을 저장한 뒤 "
                         "--browser-manifest를 제공해 주세요. 필요한 출처: " + ", ".join(pending))

    for sid in pending:
        src = by_id[sid]
        rec = {"path": f"sources/snapshots/{sid}.txt",
               "fetched_at": datetime.now(timezone.utc).isoformat()}
        try:
            result = fetch(src["url"], timeout=timeout, enable_playwright=False)
            text = getattr(result, "content", "") or ""
            rec["via"] = (getattr(result, "extraction_source", "")
                          or getattr(result, "verdict", "") or "")
            if not getattr(result, "ok", False) or not text.strip():
                rec["status"] = "blocked"
            else:
                data = text.encode("utf-8")
                if len(data) > max_bytes:
                    rec.update(status="too_large", chars=len(text))
                else:
                    _write_bytes(outputs[sid], data)
                    rec.update(status="ok", chars=len(text), sha256=hashlib.sha256(data).hexdigest())
        except Exception as e:
            rec.update(status="error", error=f"{type(e).__name__}: {str(e)[:120]}")
        src["snapshot"] = rec
        counts[rec["status"]] += 1

    _write_sources(sources_path, sources)
    return counts


def main():
    p = argparse.ArgumentParser(description="고위험 주장 인용 출처의 원문 스냅샷을 저장해요.")
    p.add_argument("--session", required=True)
    p.add_argument("--browser-manifest", help="browser_use 원문 manifest의 세션 상대 JSON 경로예요.")
    p.add_argument("--engine-dir", help="선택적 HTTP 전용 insane-search 엔진 디렉터리예요.")
    p.add_argument("--max-bytes", type=int, default=MAX_BYTES_DEFAULT)
    p.add_argument("--timeout", type=int, default=25)
    args = p.parse_args()
    try:
        c = snapshot(args.session, max_bytes=args.max_bytes, timeout=args.timeout,
                     browser_manifest=args.browser_manifest, engine_dir=args.engine_dir)
    except (OSError, ValueError, TypeError) as e:
        print(f"스냅샷 입력을 확인해 주세요: {e}", file=sys.stderr)
        return 2
    print("=== snapshot_sources ===", file=sys.stderr)
    print(f"  ok={c['ok']} blocked={c['blocked']} too_large={c['too_large']} error={c['error']} "
          f"skipped(기존 ok)={c['skipped']}", file=sys.stderr)
    if c["blocked"] + c["too_large"] + c["error"]:
        print("  원문이 없는 고위험 주장은 검증 게이트에서 unresolved로 남아요.", file=sys.stderr)
    if not c["ok"] + c["skipped"]:
        print("  수집된 원문이 없어요. browser_use 원문 manifest를 제공해 주세요.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
