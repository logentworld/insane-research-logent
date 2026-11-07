package com.sleepysoong.logent.insanaresearch

import java.io.File
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

/** orchestrator 파이썬 테스트를 같은 저장소에서 실행해요. */
class RuntimePythonTest {

    @Test
    fun `게이트 스크립트 파이썬 테스트가 통과해요`() {
        val python = python()
        assumeTrue("python3가 없어 파이썬 게이트 테스트를 건너뛰어요.", python != null)
        val root = File(System.getProperty("logent.repo.root") ?: "..").canonicalFile
        assertTrue(
            "저장소 루트를 찾지 못했어요: $root",
            File(root, "skills/insane-research-main/scripts/orchestrator.py").isFile,
        )

        val process = ProcessBuilder(
            python,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests/python",
            "-p",
            "test_*.py",
        )
            .directory(root)
            .redirectErrorStream(true)
            .start()
        val output = process.inputStream.bufferedReader().use { it.readText() }
        val finished = process.waitFor(120, TimeUnit.SECONDS)
        if (!finished) process.destroyForcibly()
        assertTrue("파이썬 테스트가 120초 안에 끝나지 않았어요.\n$output", finished)
        assertEquals(output, 0, process.exitValue())
    }

    private fun python(): String? {
        for (candidate in listOf("python3", "python")) {
            val ok = runCatching {
                ProcessBuilder(candidate, "--version")
                    .redirectErrorStream(true)
                    .start()
                    .also { it.waitFor(10, TimeUnit.SECONDS) }
                    .exitValue() == 0
            }.getOrDefault(false)
            if (ok) return candidate
        }
        return null
    }
}
