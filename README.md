# insane-research-logent

[fivetaku/insane-research](https://github.com/fivetaku/insane-research)를 포크해 Logent의
`deep_research` 도구와 세 가지 리서치 스킬로 묶은 저장소예요. 원본 이력과 MIT 고지를
유지하고, Logent에 필요한 변경만 `logent` 브랜치에 얹어요.

- 원본: `fivetaku/insane-research` v2.11.1 (`8f92b33d5d806a5437cc9e9d2e8b795ecc421315`, MIT)
- 원본 README 원문: [`README.upstream.md`](README.upstream.md)
- Logent 변경 내역: [`NOTICE`](NOTICE), [`docs/insane-research.md`](docs/insane-research.md)
- 플러그인 id: `dev.logent.insane-research` (기존 설치와 같은 id를 유지해요)

## 무엇을 하나요

한 질문을 7단계 리서치 세션으로 나눠 출처 등급·인용·claim ledger·원문 스냅샷을 남기고,
검증 게이트를 통과한 보고서만 만들어요. `AskUserQuestion`·`Workflow` 대신 채팅 질문과
Logent 서브에이전트(한 번에 3개, 총 6개, 각 8분)를 써요. 세션은 작업 디렉터리의
`RESEARCH/` 아래에만 만들어요.

## 구조

```text
skills/insane-research-main/   원본 메인 스킬·스크립트·템플릿 (upstream 경로)
skills/insane-research-query/  질문 설계 스킬
skills/insane-research-refs/   참조 이미지 수집 스킬
plugin/                        Logent Kotlin 플러그인과 deep_research 도구
tests/python/                  Logent가 추가한 런타임 회귀 테스트
scripts/                       검증·서명 .lpg·릴리스
```

스킬 본문은 upstream과 같은 경로를 단일 원천으로 써요. `plugin/build.gradle.kts`가
스킬 자산과 게이트 스크립트만 `runtime.zip`·`skills/`로 동기화하고,
`plugin/src/main/assets/`는 빌드 산출물이라 저장소에 넣지 않아요.

## 검증과 빌드

Android SDK 37, JDK 21, Python 3.11 이상이 필요해요. API artifact는
`plugin-api.lock`에 고정하며 GitHub Packages 읽기 권한이 있는 `GITHUB_ACTOR`와
`GITHUB_TOKEN`을 환경에서 받아요.

```bash
./scripts/test.sh --python-only
./scripts/test.sh
LOGENT_CONTENT_SIGNING_KEY_FILE="$HOME/.local/share/logent/content-signing.pem" \
  ./scripts/build.sh
# build/dist/logent-insane-research-v<VERSION>.lpg
```

서명 개인키는 저장소 밖에만 두고, APK에 고정된 ECDSA P-256 공개키와 맞는 패키지만
설치돼요.

## upstream 업데이트

```bash
git fetch upstream
git switch logent
git merge upstream/main
./scripts/test.sh
git push origin logent
```

합친 뒤 `UPSTREAM_COMMIT`을 갱신하고, Logent 패치(`orchestrator.py` CLI,
`verify_report.py`의 전체 보고서 검사, `snapshot_sources.py`·`collect_ref_images.py`의
`~/.logent/plugins/insane-search/engine` 경로와 HTTPS 제한)가 유지됐는지 확인해요.
upstream의 `.claude-plugin/`·`commands/`·`setup/`·Claude 마켓플레이스 파일은
Logent `.lpg`에 넣지 않아요.

## 라이선스

원본 스킬·스크립트는 MIT이며 `skills/insane-research-main/LICENSE`와 원문 고지를
그대로 보존해요. `plugin/`의 Logent Kotlin 통합 코드는 GPL-3.0(`plugin/LICENSE`)이에요.
