package com.sleepysoong.logent.insanaresearch

import com.sleepysoong.logent.plugin.PluginHost
import com.sleepysoong.logent.plugin.ProcessResult
import com.sleepysoong.logent.plugin.shellQuote
import java.security.MessageDigest
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** Termux 홈 기준 런타임 경로와 고정 버전이에요. */
internal const val RUNTIME_VERSION = "8f92b33d5d806a5437cc9e9d2e8b795ecc421315"
internal const val RUNTIME_ASSET_ENTRY = "assets/plugins/insane-research/runtime.zip"
internal const val RESEARCH_HOME = "plugins/insane-research"
internal const val SEARCH_ENGINE_DIR = "plugins/insane-search/engine"
internal const val DEPLOY_TIMEOUT_SECONDS = 300
internal const val DEPLOYED_MARKER = "INSANE_RESEARCH_DEPLOYED"
internal const val READY_MARKER = "INSANE_RESEARCH_READY"

/**
 * insane-research 게이트 스크립트와 템플릿을 Termux 홈에 배포해요.
 *
 * 콘텐츠 아카이브 자산은 argv 한도를 피하려고 `unzip -p`로 꺼내고,
 * 임시 디렉터리에서 레이아웃을 검증한 뒤 `scripts`·`refs`·`templates`를 교체해요.
 * VERSION은 교체가 모두 끝난 뒤에만 기록해 실패한 배포가 성공으로 굳지 않게 해요.
 */
internal class ResearchRuntime(private val runtimeVersion: String = RUNTIME_VERSION) {
    private val mutex = Mutex()

    @Volatile
    var host: PluginHost? = null
        private set

    @Volatile
    private var ready = false

    suspend fun ensureReady(host: PluginHost): Result<Unit> = mutex.withLock {
        this.host = host
        if (ready) return@withLock Result.success(Unit)
        val archive = host.contentArchive("plugins/insane-research")
            .getOrElse { return@withLock Result.failure(it) }
        if (archive.isBlank()) {
            return@withLock Result.failure(IllegalStateException("콘텐츠 아카이브 경로가 비어 있어요."))
        }
        val identity = MessageDigest.getInstance("SHA-256")
            .digest("$archive\u0000${host.appVersion}".toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
        val executed = host.shell(deployCommand(archive, identity), DEPLOY_TIMEOUT_SECONDS)
            .getOrElse { return@withLock Result.failure(it) }
        val output = executed.output
        if (!executed.success || (!output.contains(DEPLOYED_MARKER) && !output.contains(READY_MARKER))) {
            return@withLock Result.failure(IllegalStateException(failureReason(output)))
        }
        ready = true
        Result.success(Unit)
    }

    suspend fun execute(command: String, timeoutSeconds: Int): Result<ProcessResult> {
        val activeHost = host
            ?: return Result.failure(IllegalStateException("insane-research 런타임이 아직 준비되지 않았어요."))
        ensureReady(activeHost).onFailure { return Result.failure(it) }
        return activeHost.shell(command, timeoutSeconds)
    }

    internal fun deployCommand(apkPath: String, identity: String): String = """
        |export PATH=/data/data/com.termux/files/usr/bin:${'$'}PATH
        |DIR="${'$'}HOME/.logent/plugins/insane-research"
        |mkdir -p "${'$'}DIR" || { echo "INSANE_RESEARCH_DIR_FAILED"; exit 1; }
        |if [ "$(cat "${'$'}DIR/VERSION" 2>/dev/null)" = '$runtimeVersion' ] && [ "$(cat "${'$'}DIR/CONTENT" 2>/dev/null)" = '$identity' ] && [ -f "${'$'}DIR/scripts/validate_ledger.py" ]; then
        |  echo "$READY_MARKER"
        |  exit 0
        |fi
        |command -v python3 >/dev/null 2>&1 || { echo "INSANE_RESEARCH_PYTHON_MISSING"; exit 78; }
        |command -v unzip >/dev/null 2>&1 || { echo "INSANE_RESEARCH_UNZIP_MISSING"; exit 78; }
        |APK=${shellQuote(apkPath)}
        |STAGE=${'$'}(mktemp -d "${'$'}DIR/stage.XXXXXXXX") || { echo "INSANE_RESEARCH_STAGE_FAILED"; exit 1; }
        |trap 'rm -rf "${'$'}STAGE"' EXIT
        |unzip -p "${'$'}APK" '$RUNTIME_ASSET_ENTRY' > "${'$'}STAGE/runtime.zip" 2>/dev/null || { echo "INSANE_RESEARCH_ASSET_FAILED"; exit 1; }
        |[ -s "${'$'}STAGE/runtime.zip" ] || { echo "INSANE_RESEARCH_ASSET_EMPTY"; exit 1; }
        |python3 - "${'$'}STAGE/runtime.zip" "${'$'}STAGE/unpacked" <<'PY'
        |import pathlib, sys, zipfile
        |archive = pathlib.Path(sys.argv[1])
        |stage = pathlib.Path(sys.argv[2])
        |stage.mkdir(parents=True, exist_ok=True)
        |try:
        |    with zipfile.ZipFile(archive) as z:
        |        for info in z.infolist():
        |            parts = pathlib.PurePosixPath(info.filename).parts
        |            if info.filename.startswith("/") or ".." in parts:
        |                raise SystemExit("unsafe zip path")
        |        z.extractall(stage)
        |except Exception as exc:
        |    print(f"INSANE_RESEARCH_EXTRACT_FAILED: ${'$'}{exc}", file=sys.stderr)
        |    raise SystemExit(1)
        |PY
        |[ "${'$'}?" -eq 0 ] || { echo "INSANE_RESEARCH_EXTRACT_FAILED"; exit 1; }
        |for part in scripts refs templates; do
        |  [ -d "${'$'}STAGE/unpacked/${'$'}part" ] || { echo "INSANE_RESEARCH_LAYOUT_FAILED:${'$'}part"; exit 1; }
        |done
        |[ -f "${'$'}STAGE/unpacked/scripts/validate_ledger.py" ] || { echo "INSANE_RESEARCH_SCRIPTS_MISSING"; exit 1; }
        |mkdir "${'$'}STAGE/previous" || exit 1
        |for part in scripts refs templates; do
        |  if [ -e "${'$'}DIR/${'$'}part" ]; then
        |    cp -a "${'$'}DIR/${'$'}part" "${'$'}STAGE/previous/${'$'}part" || exit 1
        |  fi
        |done
        |printf '%s' '$identity' > "${'$'}STAGE/CONTENT" || exit 1
        |# 중간에 종료되면 어떤 콘텐츠 선택도 다음 시작에 다시 배포하게 해요.
        |rm -f "${'$'}DIR/CONTENT" || exit 1
        |for part in scripts refs templates; do
        |  if ! { rm -rf "${'$'}DIR/${'$'}part" && mv "${'$'}STAGE/unpacked/${'$'}part" "${'$'}DIR/${'$'}part"; }; then
        |    for restore in scripts refs templates; do
        |      rm -rf "${'$'}DIR/${'$'}restore"
        |      if [ -e "${'$'}STAGE/previous/${'$'}restore" ]; then
        |        mv "${'$'}STAGE/previous/${'$'}restore" "${'$'}DIR/${'$'}restore"
        |      fi
        |    done
        |    echo "INSANE_RESEARCH_REPLACE_FAILED:${'$'}part"; exit 1
        |  fi
        |done
        |chmod 700 "${'$'}DIR/scripts/"*.py "${'$'}DIR/refs/"*.py 2>/dev/null || true
        |for file in LICENSE LOGENT-NOTICE.md UPSTREAM_COMMIT; do
        |  [ -f "${'$'}STAGE/unpacked/${'$'}file" ] && cp -f "${'$'}STAGE/unpacked/${'$'}file" "${'$'}DIR/${'$'}file"
        |done
        |test -f "${'$'}DIR/scripts/validate_ledger.py" || { echo "INSANE_RESEARCH_SCRIPTS_MISSING"; exit 1; }
        |printf '%s' '$runtimeVersion' > "${'$'}DIR/VERSION" || exit 1
        |mv -f "${'$'}STAGE/CONTENT" "${'$'}DIR/CONTENT" || exit 1
        |echo "$DEPLOYED_MARKER"
    """.trimMargin()

    private fun failureReason(output: String): String =
        output.lineSequence().firstOrNull { it.contains("INSANE_RESEARCH_") }
            ?: output.lineSequence().lastOrNull { it.isNotBlank() }
            ?: "insane-research 런타임 배포에 실패했어요."
}
