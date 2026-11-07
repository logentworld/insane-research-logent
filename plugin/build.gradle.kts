import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
}

val pluginRepository = projectDir.parentFile
val pluginVersion = pluginRepository.resolve("VERSION").readText().trim()
version = pluginVersion
val apiPin = Properties().apply {
    pluginRepository.resolve("plugin-api.lock").inputStream().use { load(it) }
}

android {
    namespace = "com.sleepysoong.logent.insanaresearch"
    compileSdk = 37

    defaultConfig {
        minSdk = 26
        buildConfigField("String", "PLUGIN_VERSION", "\"$pluginVersion\"")
    }

    buildFeatures { buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

// 게이트 스크립트만 Termux에 배포해요. 스킬 본문·참조는 플러그인 자산에서 읽어요.
val repositoryRoot = projectDir.parentFile
val runtimeZip = tasks.register<Zip>("insaneResearchRuntimeZip") {
    from(repositoryRoot.resolve("skills/insane-research-main/scripts")) { into("scripts") }
    from(repositoryRoot.resolve("skills/insane-research-refs/scripts")) { into("refs") }
    from(repositoryRoot.resolve("skills/insane-research-main/assets/templates")) { into("templates") }
    from(repositoryRoot.resolve("skills/insane-research-main")) {
        include("LICENSE", "LOGENT-NOTICE.md", "UPSTREAM_COMMIT", "VERSION")
    }
    exclude("**/__pycache__/**", "**/*.pyc")
    archiveFileName.set("runtime.zip")
    destinationDirectory.set(layout.buildDirectory.dir("generated/pluginAssets/plugins/insane-research"))
}

// 스킬 본문은 APK 자산에서 바로 읽어요. Gradle이 저장소 원본을 자산 트리로 동기화해요.
val skillAssets = tasks.register<Sync>("insaneResearchSkillAssets") {
    into(layout.buildDirectory.dir("generated/pluginAssets/plugins/insane-research/skills"))
    from(repositoryRoot.resolve("skills/insane-research-main")) {
        into("insane-research")
        exclude("**/__pycache__/**", "**/*.pyc")
    }
    from(repositoryRoot.resolve("skills/insane-research-query")) {
        into("insane-research-query")
        exclude("**/__pycache__/**", "**/*.pyc")
    }
    from(repositoryRoot.resolve("skills/insane-research-refs")) {
        into("insane-research-refs")
        exclude("**/__pycache__/**", "**/*.pyc")
    }
}

val stagedAssets = tasks.register<Sync>("stagePluginAssets") {
    dependsOn(runtimeZip, skillAssets)
    from(layout.buildDirectory.dir("generated/pluginAssets"))
    into(layout.buildDirectory.dir("staged/pluginAssets"))
}
// AGP 9 레거시 라이브러리 getter의 하위 타입 대신 공통 source-set 계약으로 접근해요.
extensions.getByType<com.android.build.gradle.BaseExtension>().sourceSets.getByName("main").assets.setSrcDirs(
    listOf(layout.buildDirectory.dir("staged/pluginAssets")),
)
apply(from = pluginRepository.resolve("scripts/artifacts.gradle.kts"))

// 자산이 없으면 APK에 빈 plugin 자산이 들어가므로 mergeAssets가 반드시 두 태스크를 기다려요.
tasks.matching { it.name.startsWith("merge") && it.name.endsWith("Assets") }.configureEach {
    dependsOn(stagedAssets)
}
// Lint 모델도 생성 자산을 읽으므로 태스크 순서를 명시해요.
tasks.matching { it.name.contains("Lint", ignoreCase = true) }.configureEach {
    dependsOn(stagedAssets)
}

dependencies {
    implementation("${apiPin.getProperty("group")}:${apiPin.getProperty("artifact")}:${apiPin.getProperty("version")}")
    testImplementation("junit:junit:4.13.2")
}

tasks.withType<Test>().configureEach {
    dependsOn(stagedAssets)
    // 파이썬 게이트 테스트와 스킬 원본을 저장소 기준 경로로 찾아요.
    systemProperty("logent.repo.root", repositoryRoot.absolutePath)
    systemProperty(
        "logent.plugin.assets",
        layout.buildDirectory.dir("staged/pluginAssets").get().asFile.absolutePath,
    )
    maxParallelForks = Runtime.getRuntime().availableProcessors().coerceAtLeast(1)
}
