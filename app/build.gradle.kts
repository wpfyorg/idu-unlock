plugins {
    id("com.android.application")
}

android {
    namespace = "com.jioidu.unlock"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.jioidu.unlock"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("com.github.mwiede:jsch:0.2.26")
    testImplementation("junit:junit:4.13.2")
}
