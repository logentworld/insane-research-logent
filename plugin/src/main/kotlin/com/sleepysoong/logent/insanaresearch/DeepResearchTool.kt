package com.sleepysoong.logent.insanaresearch

import com.sleepysoong.logent.plugin.PluginContext
import com.sleepysoong.logent.plugin.PluginHost
import com.sleepysoong.logent.plugin.ProcessResult
import com.sleepysoong.logent.plugin.ToolResult
import com.sleepysoong.logent.plugin.shellQuote
import com.sleepysoong.logent.plugin.text
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * insane-research의 세션 상태와 결정론적 검증 게이트를 Termux에서 실행해요.
 *
 * 스킬 본문은 모델이 `skill read`로 읽고, 실제 게이트는 이 도구가 고정된 스크립트 경로와
 * 인자만 받아 실행해요. 세션 이름은 `RESEARCH/` 아래 한 단계 폴더만 허용해 경로 이탈을 막아요.
 */
internal class DeepResearchTool(private val runtime: ResearchRuntime) {
    private val lock = Mutex()

    suspend fun execute(
        arguments: JsonObject,
        host: PluginHost,
        context: PluginContext,
    ): ToolResult = lock.withLock {
        val invalid = validate(arguments)
        if (invalid != null) return@withLock ToolResult(invalid, isError = true)
        val action = arguments.text("action").orEmpty().trim()
        val topic = arguments.text("topic")?.trim().orEmpty()
        val session = arguments.text("session")?.trim()?.takeIf { it.isNotEmpty() }

        context.progress("insane-research 런타임을 확인하는 중이에요.")
        runtime.ensureReady(host).exceptionOrNull()?.let {
            return@withLock ToolResult("insane-research 런타임을 준비하지 못했어요: ${it.message}", isError = true)
        }

        val command = buildString {
            append("source \"\$HOME/.logent/env\" 2>/dev/null || true\n")
            if (session != null && action != "start") {
                append("test -f ")
                append(shellQuote("RESEARCH/$session/state.json"))
                append(" || { echo ")
                append(shellQuote("RESEARCH/$session 세션을 찾지 못했어요. deep_research(status)로 세션을 확인하세요."))
                append("; exit 78; }\n")
            }
            append("python3 ")
            append(scriptPath(scriptFor(action)))
            when (action) {
                "start" -> {
                    append(" init --topic ").append(shellQuote(topic))
                    append(" --base RESEARCH")
                }
                "status" -> {
                    if (session != null) {
                        append(" status --session ").append(shellQuote(session)).append(" --base RESEARCH")
                    } else {
                        append(" list --base RESEARCH")
                    }
                }
                "resume" -> append(" resume --session ").append(shellQuote(session.orEmpty())).append(" --base RESEARCH")
                "merge" -> append(" --session ").append(shellQuote("RESEARCH/${session.orEmpty()}"))
                "snapshot" -> {
                    append(" --session ").append(shellQuote("RESEARCH/${session.orEmpty()}"))
                    append(" --engine-dir \"\$HOME/.logent/plugins/insane-search/engine\"")
                    arguments.text("browser_manifest")?.let {
                        append(" --browser-manifest ").append(shellQuote(it))
                    }
                }
                "validate", "verify", "eval" -> {
                    append(" --session ").append(shellQuote("RESEARCH/${session.orEmpty()}"))
                }
            }
        }
        val timeout = if (action == "snapshot") 600 else 180
        val execution = runtime.execute(command, timeout).getOrElse { error ->
            return@withLock ToolResult(
                "deep_research 실행 결과를 확인하지 못했어요: ${error.message}",
                isError = true,
            )
        }
        result(action, session, execution)
    }

    private fun result(action: String, session: String?, execution: ProcessResult): ToolResult {
        val body = execution.output.trim()
        val text = buildString {
            append("deep_research ").append(action)
            if (!session.isNullOrBlank()) append(" · ").append(session)
            append('\n')
            append(body.ifBlank { "출력이 없어요." })
            if (execution.exitCode != 0) append("\n종료 코드: ").append(execution.exitCode)
            if (execution.truncated) append("\n응답이 출력 한도에서 잘렸어요.")
        }
        val limited = truncate(text)
        return ToolResult(
            limited,
            isError = !execution.success || execution.truncated || body.isBlank() || limited.length < text.length,
        )
    }

    private fun truncate(text: String, max: Int = MAX_TOOL_TEXT): String {
        if (text.length <= max) return text
        val suffix = "\n… 도구 출력 한도에서 잘렸어요."
        return text.take((max - suffix.length).coerceAtLeast(0)).trimEnd() + suffix
    }

    private fun scriptFor(action: String): String = when (action) {
        "start", "status", "resume" -> "orchestrator.py"
        "merge" -> "merge_agent_returns.py"
        "snapshot" -> "snapshot_sources.py"
        "validate" -> "validate_ledger.py"
        "verify" -> "verify_report.py"
        "eval" -> "eval_report.py"
        else -> error("검증된 action이 아니에요: $action")
    }

    private fun scriptPath(name: String): String = "\"\$HOME/.logent/plugins/insane-research/scripts/$name\""

    private fun validate(arguments: JsonObject): String? {
        if (arguments.keys.any { it !in ALLOWED_ARGS }) return "지원하지 않는 deep_research 인자가 있어요."
        val action = arguments.text("action")?.trim()
            ?: return "action이 필요해요."
        if (action !in ACTIONS) return "지원하지 않는 deep_research action이에요: $action"
        if ("browser_manifest" in arguments) {
            if (action != "snapshot") return "browser_manifest는 snapshot에서만 쓸 수 있어요."
            val value = arguments["browser_manifest"] as? JsonPrimitive
            val path = value?.takeIf { it.isString }?.content
                ?: return "browser_manifest는 세션 기준 JSON 상대 경로 문자열이어야 해요."
            if (path.isBlank() || path.startsWith('/') || '\\' in path || ':' in path ||
                path.any { it.isISOControl() } || !path.endsWith(".json") ||
                path.split('/').any { it.isEmpty() || it == "." || it == ".." }
            ) {
                return "browser_manifest는 세션 안의 JSON 상대 경로여야 해요. 절대 경로와 경로 이탈은 허용하지 않아요."
            }
        }
        val topic = arguments.text("topic")?.trim()
        val session = arguments.text("session")?.trim()?.takeIf { it.isNotEmpty() }
        if (action == "start") {
            if (topic.isNullOrBlank()) return "start에는 topic이 필요해요."
            if (topic.length > 300 || '\u0000' in topic) return "topic이 너무 길거나 올바르지 않아요."
            if (session != null) return "start에는 session을 함께 보낼 수 없어요."
        } else {
            if (!topic.isNullOrBlank()) return "topic은 start에서만 쓸 수 있어요."
            if (action != "status" && session == null) return "$action 에는 session이 필요해요."
            if (session != null && !SESSION.matches(session)) {
                return "session은 RESEARCH 바로 아래 폴더 이름만 허용해요. 경로 구분자와 '..'는 쓸 수 없어요."
            }
        }
        return null
    }

    private companion object {
        const val MAX_TOOL_TEXT = 26_000
        val ACTIONS = setOf("start", "status", "resume", "merge", "snapshot", "validate", "verify", "eval")
        val ALLOWED_ARGS = setOf("action", "topic", "session", "browser_manifest")
        // orchestrator는 한글 주제를 그대로 세션 이름에 쓰므로 유니코드 문자·숫자를 허용해요.
        val SESSION = Regex("[\\p{L}\\p{N}][\\p{L}\\p{N}._-]{0,119}")
    }
}
