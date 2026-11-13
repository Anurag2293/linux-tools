plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val home = providers.gradleProperty("fileviewHome").get()
val homeHost: String = home.substringAfter("://").substringBefore("/")

android {
    namespace = "dev.anurag.fileview"
    compileSdk = 35

    defaultConfig {
        applicationId = "dev.anurag.fileview"
        minSdk = 29
        targetSdk = 35
        versionCode = 2
        versionName = "2.0"
        buildConfigField("String", "HOME_URL", "\"$home\"")
        manifestPlaceholders["fileviewHost"] = homeHost
    }

    buildFeatures {
        buildConfig = true
        compose = true
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    packaging {
        resources.excludes += setOf("META-INF/LICENSE*", "META-INF/NOTICE*")
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("io.coil-kt:coil-compose:2.7.0")
    implementation("io.coil-kt:coil-svg:2.7.0")
    implementation("io.coil-kt:coil-gif:2.7.0")
    implementation("androidx.media3:media3-exoplayer:1.5.0")
    implementation("androidx.media3:media3-ui:1.5.0")
    implementation("androidx.media3:media3-datasource-okhttp:1.5.0")

    val markwon = "4.6.2"
    implementation("io.noties.markwon:core:$markwon")
    implementation("io.noties.markwon:ext-tables:$markwon")
    implementation("io.noties.markwon:ext-strikethrough:$markwon")
    implementation("io.noties.markwon:ext-tasklist:$markwon")
    implementation("io.noties.markwon:html:$markwon")
    implementation("io.noties.markwon:image:$markwon")
    implementation("io.noties.markwon:linkify:$markwon")
}
