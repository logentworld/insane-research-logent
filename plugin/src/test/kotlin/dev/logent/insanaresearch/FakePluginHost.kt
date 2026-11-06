package dev.logent.insanaresearch

import dev.logent.plugin.PluginHost
import dev.logent.plugin.ProcessResult

/** 셸 명령과 출력을 그대로 붙잡아 두는 테스트 호스트예요. */
internal class FakePluginHost(
    override val appVersion: String = "0.0.0-test",
    override val apkPath: String = "/data/app/~~abc/dev.logent-1/base.apk",
) : PluginHost {
    val commands = mutableListOf<String>()
    val timeouts = mutableListOf<Int>()
    val progressMessages = mutableListOf<String>()

    var respond: (String) -> Result<ProcessResult> = {
        Result.success(ProcessResult(0, "INSANE_RESEARCH_DEPLOYED", false))
    }

    override suspend fun shell(command: String, timeoutSeconds: Int): Result<ProcessResult> {
        commands += command
        timeouts += timeoutSeconds
        return respond(command)
    }

    override suspend fun ensureDesktop(): Result<Unit> = Result.success(Unit)

    override suspend fun contentArchive(assetPrefix: String): Result<String> = Result.success(apkPath)

    override suspend fun readAsset(path: String): Result<ByteArray> =
        Result.failure(IllegalArgumentException("테스트에서는 자산을 읽지 않아요: $path"))

    override fun progress(message: String) {
        progressMessages += message
    }
}
