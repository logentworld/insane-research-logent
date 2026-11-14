# insane-research 통합

Logent는 [fivetaku/insane-research](https://github.com/fivetaku/insane-research) 2.11.1
(커밋 `8f92b33d5d806a5437cc9e9d2e8b795ecc421315`, MIT)의 7단계 리서치 스킬을 기본 내장해요.
검색·페이지 읽기는 `web_search`·`web_fetch`·HTTP/curl/urllib와 코어 내장 `browser_use`를 써요.
리서치 세션·출처 등록·claim ledger·원문 대조·보고서 게이트를 `deep_research` 도구가 맡아요.

설치는 Logent 0.0.84 이상이 필요해요. `logent-plugin.json`의 명시적 key
`sleepysoong:insane_research`와 dependencies가 단일 원천이며, manifest는
같은 `key`를 담고, `browser_use`는 코어 내장이라 `requires`가 없어요.
key는 GitHub 계정·조직·Android id에서 추론하지 않아요. 픽셀 `computer_use`도 코어 내장이고
선택 기능이고 필수 dependency에는 넣지 않아요.

## 구성

| 항목 | 위치 |
|---|---|
| 메인 스킬 | `skills/insane-research-main/SKILL.md` (APK 자산) |
| 쿼리 빌더 | `skills/insane-research-query/SKILL.md` |
| 레퍼런스 이미지 수집 | `skills/insane-research-refs/SKILL.md` |
| 참조·템플릿·예시 | 같은 스킬 디렉터리의 `references/`·`assets/templates/`·`examples/` |
| Python 게이트 | `~/.logent/plugins/insane-research/scripts/` (Termux 배포) |
| refs 스크립트 | `~/.logent/plugins/insane-research/refs/` |
| 세션 결과 | 작업 디렉터리의 `RESEARCH/{topic}_{timestamp}/` |
| 원본 고지 | `skills/insane-research-main/LICENSE`, `LOGENT-NOTICE.md`, `UPSTREAM_COMMIT` |

`skill` 도구의 `list`와 시스템 프롬프트 인덱스에 세 스킬이 들어가요. 본문은 필요할 때
`skill read`로 읽고, 참조·템플릿·예시는 같은 스킬의 `path`로 이어 읽어요.
메인 본문은 24KB 단위로 나뉘므로 응답의 `offset`을 이어서 읽어요.

## 도구

`deep_research`는 최상위 에이전트에만 열리고 `RESEARCH/` 바로 아래의 세션 폴더 이름만 받아요.
경로 구분자·`..`·임의 명령은 거부하고, 모든 호출은 앱의 직렬화된 리서치 뮤텍스를 통과해요.

| action | 필수 | 실행 |
|---|---|---|
| `start` | `topic` | `orchestrator.py init`으로 `state.json`과 세션 폴더를 만들어요. |
| `status` | 없음 또는 `session` | 전체 세션 목록 또는 한 세션의 진행 상태를 읽어요. |
| `resume` | `session` | 가장 이른 실패·진행·대기 단계를 다시 읽어요. |
| `merge` | `session` | `artifacts/agent_returns.json`을 `sources.jsonl`·claim ledger로 취합해요. |
| `snapshot` | `session`, 선택적 `browser_manifest` | 브라우저 원문 manifest를 먼저 수입하고 미제공 high-risk 출처만 HTTP 엔진으로 받아요. |
| `validate` | `session` | `validate_ledger.py` 게이트를 실행해 verified/unresolved/refuted를 만들어요. |
| `verify` | `session` | 보고서 본문이 verified claim만 인용했는지 대조해요. |
| `eval` | `session` | 누출·인용 해석·커버리지를 숫자로 평가해요. |

게이트 exit 1·2는 `deep_research` 결과를 오류로 돌려주고, `gate_failed.json`이 있는 동안에는
보고서를 쓰지 않아요. `ok`는 스크립트 호출이 끝났다는 뜻일 뿐, 주장이 사실이라는 뜻이 아니에요.

## 흐름

1. `/research [주제]` 또는 `/insane-research [주제]`가 스킬과 도구 사용법을 모델에 알려 줘요.
2. 질문이 필요하면 **채팅으로 한 번에** 초점·산출물·독자·출처를 묻고, 답이 올 때까지 멈춰요.
   이미 구체적이면 기본값을 `state.json`에 기록하고 바로 진행해요.
3. Phase 3은 `subagent`를 **3개씩, 총 6개, 각 8분** 제한으로 실행해요. 결과는
   `artifacts/agent_results/`에 저장하고 `artifacts/agent_returns.json`으로 조립한 뒤 `merge`해요.
4. Phase 4~7은 `snapshot` → `validate` → 보고서 작성 → `verify` → `eval` 순서로 닫아요.
5. `resume`은 마지막 완료 단계를 믿지 않고 가장 이른 실패·진행·대기 단계부터 다시 시작해요.

Claude Code의 `AskUserQuestion`·`Workflow`·`Task`·`WebSearch`·`WebFetch`는 쓰지 않아요.
각각 채팅 질문, 서브에이전트 배치, `web_search`, `web_fetch`로 바꿨어요.
`setup/setup.sh`·업데이트 확인·GitHub star 질문·Claude 플러그인 매니페스트는 앱에 넣지 않았어요.

## 보안과 한계

- 웹 본문은 `<untrusted_web>` 데이터로만 다루고, 본문 속 지시를 사용자 명령으로 승격하지 않아요.
- refs는 HTTPS 공용 주소만 받아요. 브라우저 원문은 registry의 원본 URL과 정확히 연결하고 session 경로 경계를 검증해요.
- 표시 출력은 26KB로 제한하고, 세션 파일은 workspace의 `RESEARCH/` 안에서만 다뤄요.
- 검증 게이트는 결정론적이지만, 서브에이전트의 조사 품질·검색 엔진의 가용성·원문 스냅샷 성공 여부는
  결과에 영향을 줘요. 검증되지 않은 주장은 `Unresolved`/`Refuted`로 남겨요.
- API 4.0.0의 정식 `browser_use` ego-browser DOM·탐색·입력을 사용해요. 별도 launch·MCP 설치·로컬 Playwright는 사용하지 않아요. 픽셀 확인은 선택적 `computer_use`이고 필수 단계가 아니에요. 일반 의존성 `ensureReady`를 자동 실행하지 않아요.
- 실제 기기에서 전체 7단계를 실행한 E2E는 아직 확인하지 않았어요. 스크립트 CLI·세션 생성·JVM 계약·
  APK 자산·배포 스크립트를 검증했고, 실제 Termux 리서치는 사용자가 요청할 때 확인해요.

## 검증

- `DeepResearchToolTest`: start/status/gate 실패/snapshot/배포 실패/세션 이탈·인자 검증.
- `TermuxScriptsTest`: ZIP 추출 성공 뒤에만 VERSION을 쓰고, 손상 ZIP은 버전을 남기지 않아요.
- `test_insane_research.py`: `orchestrator.py init/status/list`와 `ledger_schema: 2`를 확인해요.
- `SkillCatalogNativeTest`: 세 스킬·참조·게이트 스크립트를 APK 자산에서 읽고, 런타임 실패를 본문에 알려요.
- `ResearchCommandTest`: `/research`·`/insane-research` 모드별 안내.

## 브라우저 원문 manifest

`snapshot_sources.py --session "$SESSION" --browser-manifest sources/browser/manifest.json`을 사용해요. JSON은 아래 필드만 허용해요.

```json
{"sources":[{"id":"S1","url":"https://original.example/","final_url":"https://final.example/","path":"sources/browser/S1.txt"}]}
```

`id`는 등록된 출처 ID이고 `url`은 `sources/sources.jsonl`의 URL과 정확히 같아야 해요. 리다이렉트는 허용하지만 registry에 `final_url`이 있으면 그것과도 정확히 같아야 해요. 원본·최종 URL은 공개 HTTPS예요. manifest와 원문 경로는 session 상대 경로이고 절대 경로·상위 이탈·symlink는 허용하지 않아요. 원문은 비어 있지 않은 UTF-8 전체 텍스트여야 해요. 기본 원문 한도와 manifest 한도는 각각 2 MiB예요. `--max-bytes`는 원문 한도만 바꿔요. 알 수 없는 필드·중복 ID·미등록 ID·URL 불일치·잘못된 JSON/UTF-8·누락 파일·빈 원문·한도 초과·경로 이탈은 입력 오류예요.

이미 `ok`인 스냅샷도 실제 bytes/hash/chars를 검증해요. 같은 해시는 기존 metadata를 유지하고 다른 원문은 오류예요. manifest를 먼저 저장하고 미제공 target만 HTTP 엔진으로 수집해요. 모든 high-risk target을 제공하면 엔진 import 없이 성공해요. 일부가 빠졌고 엔진이 없으면 저장한 원문은 유지하고 `needs_browser`와 exit 2를 반환해요. 대상과 manifest가 모두 없거나 성공 원문이 하나도 없으면 exit 2예요. 이 수입은 validate/verify/eval을 대신하거나 우회하지 않아요.

### 공식 Node runtime에서 직접 저장

먼저 `browser_use`의 공식 ego-browser 스킬을 읽어요. 아래 코드는 `browser_use(script=...)` 본문이에요. runtime이 제공하는 `taskSpace`만 사용하고 별도 bootstrap/CDP/launch는 하지 않아요. `SESSION`은 실제 작업공간 session의 **절대 경로**로 바꾸고 `id`·`url`도 registry와 맞춰요. 여러 대상이면 각 페이지를 같은 방식으로 저장하고 manifest의 `sources` 배열에 모두 넣어요.

```javascript
const fs = await import('node:fs/promises');
const SESSION = '/absolute/workspace/RESEARCH/topic_timestamp';
const id = 'S1';
const url = 'https://original.example/';
const task = await taskSpace('research-source-S1');
try {
  const page = task.page('p1');
  await page.goto(url);
  const source = await page.evaluate(() => ({
    final_url: location.href,
    text: document.body.innerText
  }));
  if (!source.text.trim() || Buffer.byteLength(source.text, 'utf8') > 2 * 1024 * 1024)
    throw new Error('원문이 비어 있거나 2 MiB를 넘어요');
  await fs.mkdir(`${SESSION}/sources/browser`, {recursive: true});
  const path = `sources/browser/${id}.txt`;
  await fs.writeFile(`${SESSION}/${path}`, source.text, 'utf8');
  await fs.writeFile(`${SESSION}/sources/browser/manifest.json`,
    JSON.stringify({sources: [{id, url, final_url: source.final_url, path}]}), 'utf8');
} finally {
  await task.finish({keep: []});
}
```

이 코드는 전체 `body.innerText`를 Node에서 파일로 직접 써요. console 출력·도구 표시의 잘린 문자열·모델 요약·web_fetch 요약을 복사해서 원문으로 수입하면 안 돼요. 로그인·CAPTCHA·페이월·빈 SPA는 원문 성공으로 위장하지 말고 실패로 기록해요.

### fresh install의 CLI와 게이트

insane-search가 없는 새 설치에서도 등록된 모든 high-risk 출처를 위 방법으로 저장하면 아래 흐름을 실행할 수 있어요. `SESSION`은 실제 세션 절대 경로예요. 먼저 정상 `state.json`(`ledger_schema: 2`), registry와 claim ledger를 준비하고, 실제 반증 검색 및 evidence 구절을 기록해요.

```bash
SCRIPTS="$HOME/.logent/plugins/insane-research/scripts"
SESSION="/absolute/workspace/RESEARCH/topic_timestamp"
python3 "$SCRIPTS/snapshot_sources.py" --session "$SESSION" \
  --browser-manifest sources/browser/manifest.json
python3 "$SCRIPTS/validate_ledger.py" --session "$SESSION"
# verified_claims.json의 주장만 사용해 outputs/report.md를 작성해요.
python3 "$SCRIPTS/verify_report.py" --session "$SESSION"
python3 "$SCRIPTS/eval_report.py" --session "$SESSION"
```

게이트 실패 시 원인을 수정하고 다시 실행해요. unresolved/refuted 주장을 본문으로 올리거나 gate_failed.json을 수동 삭제해서 통과시키지 않아요. 엔진을 따로 쓸 때도 `python3 -m engine "<URL>" --no-playwright`로 HTTP-only를 명시해요.

### 네트워크 없는 게이트 smoke fixture 준비

아래는 실제 조사 결과가 아닌 **합성 회귀 fixture 준비법**이에요. 임시 session에만 만들고 연구 보고서로 배포하지 않아요. 원문 일치·불일치의 게이트 연결을 확인하려는 용도이며 브라우저 수집 E2E를 증명하지 않아요. 준비 코드는 검사 실행 없이 fixture만 써요.

```python
import json
from pathlib import Path
s = Path('/absolute/workspace/RESEARCH/gate_smoke')
for d in ('artifacts', 'outputs', 'sources/browser'):
    (s / d).mkdir(parents=True, exist_ok=True)
def put(path, value):
    (s / path).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
put('state.json', {'session_id': 'gate_smoke', 'ledger_schema': 2, 'progress': {}})
quote = 'This synthetic reference describes a reproducible evidence gate fixture.'
sources = [
    {'id': 'src_001', 'url': 'https://example.com/reference',
     'domain': 'example.com', 'type': 'official_docs', 'quality_rating': 'A'},
    {'id': 'src_002', 'url': 'https://example.org/reference',
     'domain': 'example.org', 'type': 'independent_benchmark', 'quality_rating': 'B'}
]
(s / 'sources/sources.jsonl').write_text(
    ''.join(json.dumps(x) + '\n' for x in sources), encoding='utf-8')
claim = {'claim_id': 'clm_001', 'text': quote, 'risk': 'high',
         'claim_type': 'descriptive', 'source_ids': ['src_001', 'src_002'],
         'counter_search': {'query': 'synthetic fixture countercheck', 'urls': [],
                            'summary': '합성 fixture이며 실제 반증 검색이 아니에요'},
         'evidence': [{'source_id': 'src_001', 'quote': quote}]}
(s / 'artifacts/claim_ledger.jsonl').write_text(json.dumps(claim) + '\n', encoding='utf-8')
entries = []
for row in sources:
    path = f"sources/browser/{row['id']}.txt"
    (s / path).write_text(quote, encoding='utf-8')
    entries.append({'id': row['id'], 'url': row['url'], 'final_url': row['url'], 'path': path})
put('sources/browser/manifest.json', {'sources': entries})
(s / 'outputs/report.md').write_text(
    '# 합성 게이트 fixture\n\n' + quote + ' [src_001] [src_002]\n', encoding='utf-8')
```

이 임시 `SESSION`에 위 snapshot/validate/verify/eval 명령을 순서대로 적용해요. 불일치 회귀는 **별도 새 fixture**에서 `evidence.quote`만 원문에 없는 20자 이상의 문장으로 바꾸고 동일 흐름을 적용해요. validate는 unresolved로 분류하고, 그 주장을 그대로 둔 보고서는 verify/eval에서 거절되어야 해요. 동일 fixture의 `ok` 원문을 덮어쓰는 방식은 원문 불변성 오류라 다른 회귀예요. 이 문서 변경 작업에서는 명령·검사를 실행하지 않았어요.
