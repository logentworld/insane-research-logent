# insane-research 통합

Logent는 [fivetaku/insane-research](https://github.com/fivetaku/insane-research) 2.11.1
(커밋 `8f92b33d5d806a5437cc9e9d2e8b795ecc421315`, MIT)의 7단계 리서치 스킬을 기본 내장해요.
검색·페이지 읽기는 기존 `web_search`·`web_fetch`·`insane-search`를 그대로 쓰고,
리서치 세션·출처 등록·claim ledger·원문 대조·보고서 게이트를 `deep_research` 도구가 맡아요.

## 구성

| 항목 | 위치 |
|---|---|
| 메인 스킬 | `skills/insane-research-main/SKILL.md` (APK 자산) |
| 쿼리 빌더 | `skills/insane-research-query/SKILL.md` |
| 레퍼런스 이미지 수집 | `skills/insane-research-refs/SKILL.md` |
| 참조·템플릿·예시 | 같은 스킬 디렉터리의 `references/`·`assets/templates/`·`examples/` |
| Python 게이트 | `~/.logent/insane-research/scripts/` (Termux 배포) |
| refs 스크립트 | `~/.logent/insane-research/refs/` |
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
| `snapshot` | `session` | high-risk 출처를 insane-search로 받아 `sources/snapshots/`에 남겨요. Playwright는 끄고 HTTPS만 써요. |
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
- refs는 HTTPS 공용 주소만 받고, 게이트 스냅샷은 insane-search의 공용 주소 검사에 의존해요.
- 표시 출력은 26KB로 제한하고, 세션 파일은 workspace의 `RESEARCH/` 안에서만 다뤄요.
- 검증 게이트는 결정론적이지만, 서브에이전트의 조사 품질·검색 엔진의 가용성·원문 스냅샷 성공 여부는
  결과에 영향을 줘요. 검증되지 않은 주장은 `Unresolved`/`Refuted`로 남겨요.
- Playwright 폴백은 보안 경계와 Termux 의존성 때문에 기본으로 끄고, 필요한 픽셀 확인은 `browser_use`를 써요.
- 실제 기기에서 전체 7단계를 실행한 E2E는 아직 확인하지 않았어요. 스크립트 CLI·세션 생성·JVM 계약·
  APK 자산·배포 스크립트를 검증했고, 실제 Termux 리서치는 사용자가 요청할 때 확인해요.

## 검증

- `DeepResearchToolTest`: start/status/gate 실패/snapshot/배포 실패/세션 이탈·인자 검증.
- `TermuxScriptsTest`: ZIP 추출 성공 뒤에만 VERSION을 쓰고, 손상 ZIP은 버전을 남기지 않아요.
- `test_insane_research.py`: `orchestrator.py init/status/list`와 `ledger_schema: 2`를 확인해요.
- `SkillCatalogNativeTest`: 세 스킬·참조·게이트 스크립트를 APK 자산에서 읽고, 런타임 실패를 본문에 알려요.
- `ResearchCommandTest`: `/research`·`/insane-research` 모드별 안내.
