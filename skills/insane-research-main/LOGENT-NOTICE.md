# insane-research 출처와 Logent 변경

- 원본: https://github.com/fivetaku/insane-research
- 버전: 2.11.1
- 커밋: 8f92b33d5d806a5437cc9e9d2e8b795ecc421315
- 라이선스: MIT, Copyright (c) 2026 fivetaku (`LICENSE`)

## Logent에서 바꾼 것

- Claude Code 전용 `AskUserQuestion`·`Workflow`·`Task`·`WebSearch`·`WebFetch`·`Read/Write/Glob/Grep` 지시를 Logent 도구(`web_search`, `web_fetch`, `termux_shell`, `file_*`, `subagent`, `deep_research`)로 바꿨어요.
- 범위 질문은 채팅으로 한 번에 하고, 서브에이전트는 한 번에 3개·총 6개·각 8분으로 제한했어요. 2.11.1의 8–10 동시 배치 기본값은 Logent 제한에 맞춰 사용하지 않아요.
- `setup/setup.sh`, 업데이트 확인, GitHub star 질문, `.claude-plugin/`, `commands/`, `routing.json`, `README.*`, `assets/hero.png`는 앱에 넣지 않았어요. 리서치 동작과 무관하거나 Claude 플러그인 설치용이에요.
- `snapshot_sources.py`와 `collect_ref_images.py`가 `~/.logent/plugins/insane-search`를 먼저 찾고, Playwright 폴백을 끄며, refs는 HTTPS만 허용하도록 패치했어요.
- `orchestrator.py`에 `init`·`resume`·`status`·`list` CLI를 추가했어요. 원본은 하드코딩된 주제만 실행했어요.
- `verify_report.py`가 `outputs/*.md`뿐 아니라 `outputs/**/*.md`의 전체 보고서를 검사하도록 넓혔어요.
- Logent의 `deep_research` 도구가 세션 시작·상태·재개·취합·스냅샷·검증·평가를 실행해요.
- 메인·쿼리·refs 스킬 본문은 APK 자산에서 읽고, Python 게이트 스크립트와 템플릿은 `~/.logent/plugins/insane-research/`에 배포해요.

원본의 라이선스와 저작권 고지는 `LICENSE`에 그대로 보존했어요.
