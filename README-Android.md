# Jio IDU Unlock for Android

Native Android front end for the Jio IDU Unlock engine.

## Build

- JDK 17 or newer
- Android SDK Platform 36 and Build Tools 36.0.0
- Gradle wrapper downloads Gradle 9.6.0 when needed

Build the debug APK with:

```sh
./gradlew :app:assembleDebug
```

Set `JAVA_HOME` to a JDK 17+ and `ANDROID_HOME` to the Android SDK if they are
not already configured. On macOS with the standard Android Studio install:

```sh
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
ANDROID_HOME="$HOME/Library/Android/sdk" \
./gradlew :app:assembleDebug
```

The project uses Android Gradle Plugin 9.1.1 with built-in Kotlin. The app
package is `com.jioidu.unlock`; minimum Android version is 8.0 (API 26), and
compile/target SDK are 36. JSch provides the SSH client used for backup. JUnit
4.13.2 is available for local unit tests.

## App behavior

Enter the private HTTPS router URL and admin password for Detect, Check, and
Backup. Detect identifies the device; Check reports firmware compatibility.
Unlock guidance displays desktop utility instructions only. It does not run an
unlock backend or change router settings, and it does not require the router
URL or admin password.

Before the first authenticated router request, the app displays the router
certificate's SHA-256 fingerprint. Verify it through a trusted source
independent of the current network before confirming. The app pins the
certificate per router and blocks password transmission if the certificate
changes. To accept a legitimate replacement certificate, clear the app's data
only after independently verifying the new fingerprint.

Backup also verifies the SSH host key. On first connection, compare its
fingerprint with an independent trusted source. Changed SSH host keys are
rejected. After independently verifying a legitimate replacement key, clear
the app's data to accept the new certificate and host key.

Backup requires root SSH to be enabled already. After confirmation, choose a
destination with Android's system folder picker. The app uses the Storage Access
Framework to write there. It creates an app-private RSA key for SSH; the key is
not exported with the backup. Backup includes factory credentials and flash
data, so keep the selected folder private. The app does not unlock the router
as part of a backup.

Run the app only on equipment you own or are authorized to access.

Passwords are held in memory for the operation, are not written to logs or
saved as preferences, are filtered from visible logs, and are cleared from the
field when an operation ends. Router operations run on a worker thread.
