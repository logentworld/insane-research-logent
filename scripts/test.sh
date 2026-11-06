#!/usr/bin/env bash
# Python 기능 테스트와 JVM 단위 테스트·Android lint를 함께 실행해요.
set -euo pipefail
cd "$(dirname "$0")/.."
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export PYTHONDONTWRITEBYTECODE=1
mode=all
case "${1:-}" in
    --python-only) mode=python; shift ;;
    --jvm-only) mode=jvm; shift ;;
esac
if [[ "$mode" != jvm ]]; then
    command -v python3 >/dev/null || { echo "Python 3이 필요해요." >&2; exit 1; }
    python3 -m unittest discover -s tests/python -p 'test_*.py'
fi
if [[ "$mode" != python ]]; then
    ./scripts/gradle.sh :plugin:testDebugUnitTest :plugin:lintRelease "$@"
fi
