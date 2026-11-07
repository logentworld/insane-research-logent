package com.sleepysoong.logent.insanaresearch

import com.sleepysoong.logent.plugin.PluginContext
import com.sleepysoong.logent.plugin.ProcessResult
import com.sleepysoong.logent.plugin.ToolResult
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DeepResearchToolTest {
    private val json = Json

    private fun args(value: String) = json.parseToJsonElement(value).jsonObject

    private fun deployment(command: String): Boolean = command.contains("unzip -p")

    private suspend fun plugin(
        respond: (String) -> Result<ProcessResult> = {
            Result.success(ProcessResult(0, "INSANE_RESEARCH_DEPLOYED", false))
        },
    ): Pair<InsaneResearchPlugin, FakePluginHost> {
        val host = FakePluginHost().also { it.respond = respond }
        val plugin = InsaneResearchPlugin()
        plugin.ensureReady(host).getOrThrow()
        return plugin to host
    }

    private suspend fun InsaneResearchPlugin.run(arguments: JsonObject): ToolResult =
        tools().single().execute(
            arguments,
            PluginContext(sessionId = "session", workspace = "/workspace"),
        )

    @Test
    fun `start는 주제를 셸 인용해 세션을 만들고 결과를 돌려줘요`() = runBlocking {
        val (plugin, host) = plugin { command ->
            if (deployment(command)) {
                Result.success(ProcessResult(0, "INSANE_RESEARCH_DEPLOYED", false))
            } else {
                Result.success(ProcessResult(0, """{"session_id":"topic_20261104_120000"}""", false))
            }
        }

        val result = plugin.run(args("""{"action":"start","topic":"AI ; $(touch 위험)"}"""))

        assertFalse(result.text, result.isError)
        assertTrue(result.text.contains("session_id"))
        val command = host.commands.last()
        assertTrue(command.contains("/.logent/plugins/insane-research/scripts/orchestrator.py"))
        assertTrue(command.contains(" init --topic 'AI ; \$(touch 위험)' --base RESEARCH"))
        assertEquals(180, host.timeouts.last())
        assertTrue(plugin.tools().single().summarize(args("""{"action":"start"}""")) == "deep_research start")
    }

    @Test
    fun `세션 경로 이탈과 알 수 없는 action은 실행 전에 거부해요`() = runBlocking {
        val (plugin, host) = plugin()
        val before = host.commands.size

        for (bad in listOf(
            """{"action":"validate","session":"../secret"}""",
            """{"action":"validate","session":"a/b"}""",
            """{"action":"delete","session":"topic_1"}""",
            """{"action":"start","topic":"t","session":"topic_1"}""",
            """{"action":"start","topic":"t","extra":true}""",
            """{"action":"status","browser_manifest":"browser.json"}""",
            """{"action":"snapshot","session":"topic_1","browser_manifest":null}""",
            """{"action":"snapshot","session":"topic_1","browser_manifest":true}""",
            """{"action":"snapshot","session":"topic_1","browser_manifest":""}""",
            """{"action":"snapshot","session":"topic_1","browser_manifest":"/tmp/browser.json"}""",
            """{"action":"snapshot","session":"topic_1","browser_manifest":"../browser.json"}""",
            """{"action":"snapshot","session":"topic_1","browser_manifest":"sources/../browser.json"}""",
            """{"action":"snapshot","session":"topic_1","browser_manifest":"sources//browser.json"}""",
            """{"action":"snapshot","session":"topic_1","browser_manifest":"sources\\browser.json"}""",
            """{"action":"snapshot","session":"topic_1","browser_manifest":"browser.txt"}""",
        )) {
            assertTrue(bad, plugin.run(args(bad)).isError)
        }
        assertEquals(before, host.commands.size)
        assertTrue(host.progressMessages.isEmpty())
    }

    @Test
    fun `한글 세션 이름을 상태 조회에 쓸 수 있어요`() = runBlocking {
        val (plugin, host) = plugin { command ->
            if (deployment(command)) {
                Result.success(ProcessResult(0, "INSANE_RESEARCH_DEPLOYED", false))
            } else {
                Result.success(ProcessResult(0, """{"session_id":"AI_연구_20261104_120000"}""", false))
            }
        }

        val result = plugin.run(args("""{"action":"status","session":"AI_연구_20261104_120000"}"""))

        assertFalse(result.text, result.isError)
        assertTrue(host.commands.last().contains("AI_연구_20261104_120000"))
        assertTrue(host.commands.last().contains("test -f 'RESEARCH/AI_연구_20261104_120000/state.json'"))
    }

    @Test
    fun `게이트 실패는 출력을 보존한 채 오류로 돌려줘요`() = runBlocking {
        val (plugin, host) = plugin { command ->
            if (deployment(command)) {
                Result.success(ProcessResult(0, "INSANE_RESEARCH_DEPLOYED", false))
            } else {
                Result.success(ProcessResult(1, "게이트 실패: 원문 인용이 없어요", false))
            }
        }

        val result = plugin.run(args("""{"action":"validate","session":"topic_1"}"""))

        assertTrue(result.isError)
        assertTrue(result.text.contains("게이트 실패"))
        assertTrue(result.text.contains("종료 코드: 1"))
        assertTrue(host.commands.last().contains("test -f 'RESEARCH/topic_1/state.json'"))
        assertTrue(host.commands.last().contains("validate_ledger.py"))
    }

    @Test
    fun `snapshot은 manifest 없이 HTTP 수집 결과를 그대로 돌려줘요`() = runBlocking {
        val (plugin, host) = plugin { command ->
            if (deployment(command)) {
                Result.success(ProcessResult(0, "INSANE_RESEARCH_DEPLOYED", false))
            } else {
                Result.success(ProcessResult(0, "snapshot ok", false))
            }
        }

        val result = plugin.run(args("""{"action":"snapshot","session":"topic_1"}"""))

        assertFalse(result.text, result.isError)
        val command = host.commands.last()
        assertTrue(command.contains("snapshot_sources.py"))
        assertTrue(command.contains("--session 'RESEARCH/topic_1'"))
        assertTrue(command.contains("--engine-dir \"\$HOME/.logent/plugins/insane-search/engine\""))
        assertFalse(command.contains("INSANE_SEARCH_ENGINE_MISSING"))
        assertFalse(command.contains("--browser-manifest"))
        assertEquals(600, host.timeouts.last())
    }

    @Test
    fun `snapshot CLI 실패는 원인과 종료 코드를 보존해요`() = runBlocking {
        val (plugin, _) = plugin { command ->
            if (deployment(command)) {
                Result.success(ProcessResult(0, "INSANE_RESEARCH_DEPLOYED", false))
            } else {
                Result.success(ProcessResult(1, "원문이 부족해요: S1", false))
            }
        }

        val result = plugin.run(args("""{"action":"snapshot","session":"topic_1"}"""))

        assertTrue(result.isError)
        assertTrue(result.text.contains("원문이 부족해요: S1"))
        assertTrue(result.text.contains("종료 코드: 1"))
    }

    @Test
    fun `snapshot은 브라우저 manifest를 셸 인용하고 엔진 사전 검사 없이 실행해요`() = runBlocking {
        val (plugin, host) = plugin { command ->
            if (deployment(command)) {
                Result.success(ProcessResult(0, "INSANE_RESEARCH_DEPLOYED", false))
            } else {
                Result.success(ProcessResult(0, "브라우저 원문을 저장했어요", false))
            }
        }

        val result = plugin.run(args("""{"action":"snapshot","session":"topic_1","browser_manifest":"sources/browser ; $(touch 위험).json"}"""))

        assertFalse(result.text, result.isError)
        assertTrue(result.text.contains("브라우저 원문을 저장했어요"))
        assertTrue(host.commands.last().contains("--browser-manifest 'sources/browser ; \$(touch 위험).json'"))
        assertFalse(host.commands.last().contains("INSANE_SEARCH_ENGINE_MISSING"))
    }

    @Test
    fun `런타임 준비가 실패하면 게이트 스크립트를 실행하지 않아요`() = runBlocking {
        val host = FakePluginHost().also {
            it.respond = { Result.failure(IllegalStateException("Termux 없음")) }
        }
        val plugin = InsaneResearchPlugin()
        assertTrue(plugin.ensureReady(host).isFailure)

        val result = plugin.run(args("""{"action":"status"}"""))

        assertTrue(result.isError)
        assertTrue(result.text.contains("런타임을 준비하지 못했어요"))
        assertTrue(host.commands.isNotEmpty())
        assertTrue(host.commands.none { it.contains("orchestrator.py") })
    }

    @Test
    fun `준비되지 않은 플러그인은 도구 실행을 거부해요`() = runBlocking {
        val host = FakePluginHost()
        val plugin = InsaneResearchPlugin()

        val result = plugin.run(args("""{"action":"status"}"""))

        assertTrue(result.isError)
        assertTrue(result.text.contains("아직 준비되지 않았어요"))
        assertTrue(host.commands.isEmpty())
    }

    @Test
    fun `status는 세션이 없으면 전체 목록을 읽어요`() = runBlocking {
        val (plugin, host) = plugin { command ->
            if (deployment(command)) {
                Result.success(ProcessResult(0, "INSANE_RESEARCH_DEPLOYED", false))
            } else {
                Result.success(ProcessResult(0, """{"sessions":[]}""", false))
            }
        }

        val result = plugin.run(args("""{"action":"status"}"""))

        assertFalse(result.text, result.isError)
        assertTrue(host.commands.last().contains("orchestrator.py"))
        assertTrue(host.commands.last().contains("list --base RESEARCH"))
        assertFalse(host.commands.last().contains("test -f"))
    }

    @Test
    fun `빈 출력과 잘린 출력은 성공으로 포장하지 않아요`() = runBlocking {
        val (blankPlugin, _) = plugin { command ->
            if (deployment(command)) {
                Result.success(ProcessResult(0, "INSANE_RESEARCH_DEPLOYED", false))
            } else {
                Result.success(ProcessResult(0, "", false))
            }
        }
        assertTrue(blankPlugin.run(args("""{"action":"status"}""")).isError)

        val (truncatedPlugin, _) = plugin { command ->
            if (deployment(command)) {
                Result.success(ProcessResult(0, "INSANE_RESEARCH_DEPLOYED", false))
            } else {
                Result.success(ProcessResult(0, "부분 결과", true))
            }
        }
        val truncated = truncatedPlugin.run(args("""{"action":"status"}"""))
        assertTrue(truncated.isError)
        assertTrue(truncated.text.contains("잘렸어요"))
    }

    @Test
    fun `ensureReady는 runtime zip을 APK에서 꺼내 VERSION을 마지막에 기록해요`() = runBlocking {
        val host = FakePluginHost(apkPath = "/data/app/base apk.apk")
        val plugin = InsaneResearchPlugin()

        assertTrue(plugin.ensureReady(host).isSuccess)
        val command = host.commands.single()

        assertTrue(command.contains("APK='/data/app/base apk.apk'"))
        assertTrue(command.contains("unzip -p \"\$APK\" 'assets/plugins/insane-research/runtime.zip'"))
        assertTrue(command.contains("HOME/.logent/plugins/insane-research"))
        assertTrue(command.contains("for part in scripts refs templates; do"))
        assertTrue(command.contains("scripts/validate_ledger.py"))
        assertTrue(command.contains("> \"\$DIR/VERSION\""))
        assertTrue(command.contains(RUNTIME_VERSION))
        assertFalse(command.contains("base64"))
        assertEquals(300, host.timeouts.single())
        assertTrue(
            "VERSION은 부분 교체가 끝난 뒤에 기록해야 해요",
            command.indexOf("> \"\$DIR/VERSION\"") > command.indexOf("for part in scripts refs templates; do"),
        )
    }

    @Test
    fun `이미 배포된 버전이면 배포 명령을 다시 실행하지 않아요`() = runBlocking {
        val (host, plugin) = FakePluginHost() to InsaneResearchPlugin()

        plugin.ensureReady(host).getOrThrow()
        plugin.ensureReady(host).getOrThrow()

        assertEquals(1, host.commands.size)
    }
}
