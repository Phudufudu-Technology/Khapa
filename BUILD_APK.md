# BUILD_APK.md: build and sideload the Khapa APK (VS Code only, nothing else installed)

This guide takes you from a Windows PC with **only VS Code** to a Khapa APK running on your phone.
Commands are PowerShell, run in VS Code's built-in terminal (`` Ctrl+` ``). macOS/Linux differences are in Part 11.

> **Read this first: what was and was not verified.**
> The author's sandbox has no Android SDK, no Flutter SDK, and no access to Google's download servers, so
> **`flet build apk` was NOT run to completion** and no APK was tested on a phone.
> What *was* verified: the app runs in the real Flet 1.0.5 desktop client, the test suite passes, `flet run --web`
> serves the app, and `flet build apk` starts, parses `pyproject.toml`, and only stops at the first download
> (Flutter SDK) because the sandbox is offline. Every toolchain version and path below was read from the installed
> Flet 1.0.5 source (`flet_cli`), not guessed. If a step fails, see Part 10, and **do not wait for the build to
> be the last thing you try before a deadline**: `flet run` (Part 4) is a complete, judged demo on its own.

> **Fastest route, no local toolchain:** build the APK in the cloud with GitHub Actions. See `docs/BUILD_WITH_GITHUB_ACTIONS.md`. It uses the same `flet build apk` command (also untested by the author).

| | |
|---|---|
| Tested against | **Flet 1.0.5**, which bundles/pins **Flutter 3.44.8** (printed by `flet --version`), Python 3.12 |
| Auto-installed by `flet build` | Flutter 3.44.8, Temurin JDK 17.0.13, Android cmdline-tools 12.0, `platform-tools`, `platforms;android-35`, `build-tools;34.0.0` |
| Disk space | plan for **10 GB or more** free (estimate, not measured) |
| Time | first build is **long** (estimate: 20 to 45 minutes, mostly downloads); later builds are much faster. Not measured |
| Internet | required for the build (multiple gigabytes: Flutter, JDK, Android SDK, Gradle dependencies); **not** required to run the finished app |
| Output | `build\apk\*.apk` |

---

## Part 1. Install Python 3.12

Open VS Code, then **Terminal > New Terminal**.

```powershell
winget install -e --id Python.Python.3.12
```

Close the terminal (trash icon) and open a new one so `PATH` refreshes, then check:

```powershell
python --version        # expect: Python 3.12.x
```

If `winget` is missing, download the installer from https://www.python.org/downloads/ and tick **"Add python.exe to PATH"**.
If `python` opens the Microsoft Store, run `py -3.12 --version` and use `py -3.12` wherever this guide says `python`.

## Part 2. Open the project

```powershell
cd C:\path\to\khapa-flet      # the folder that contains pyproject.toml and src\
code .
```

## Part 3. Virtual environment and exact versions

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell says *"running scripts is disabled"*:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Your prompt now starts with `(.venv)`. Install the **pinned** versions:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt            # installs flet[all]==1.0.5
flet --version
```

Expected output:

```
Flet: 1.0.5
Flutter: 3.44.8
```

If it shows different numbers, you are not in the venv or an old Flet is first on `PATH`. Do not continue until it matches;
Flet's packaging changes between releases, which is why this project pins an exact version.

## Part 4. Prove it works before building (do this first)

```powershell
pip install -r requirements-dev.txt
pytest -q                                   # expect: 381 passed
flet run src\main.py                        # desktop window
```

Phone-sized window (what judges' phones look like):

```powershell
$env:KHAPA_PREVIEW_PHONE = "1"; flet run src\main.py
```

Browser version (also the easiest way to give a remote judge access, see README):

```powershell
flet run --web --port 8550 src\main.py
```

The first `flet run` downloads the Flet desktop client once.

## Part 5. Windows: enable Developer Mode (required by Flutter)

Flutter needs symbolic-link support to build apps with plugins.

```powershell
start ms-settings:developers
```

Turn **Developer Mode** on. You do **not** need Visual Studio, Android Studio, or Git for an Android-only build.

## Part 6. The Android toolchain

### Option A (recommended): let Flet install everything

Nothing to do. `flet build apk --yes` (Part 7) downloads and installs:

- Flutter 3.44.8 into `%USERPROFILE%\flutter\`
- Temurin JDK 17.0.13+11 into `%USERPROFILE%\java\17.0.13+11\`
- Android command-line tools 12.0, `platform-tools`, `platforms;android-35`, `build-tools;34.0.0` into the Android SDK
  folder (`%LOCALAPPDATA%\Android\Sdk` if it exists, otherwise `%USERPROFILE%\Android\sdk`), and accepts the licences for you.

`--yes` means you accept the Android SDK licences (https://developer.android.com/studio/terms).

### Option B: install the Android pieces yourself (if Option A fails, e.g. blocked downloads)

```powershell
# 1. JDK 17 (Flet requires major version 17)
winget install -e --id EclipseAdoptium.Temurin.17.JDK
# close and reopen the terminal, then:
$jdk = (Get-ChildItem "C:\Program Files\Eclipse Adoptium" -Directory | Where-Object Name -like "jdk-17*" | Select-Object -First 1).FullName
[Environment]::SetEnvironmentVariable("JAVA_HOME", $jdk, "User"); $env:JAVA_HOME = $jdk
& "$jdk\bin\javac.exe" -version            # expect: javac 17.x

# 2. Android command-line tools (no Android Studio)
$sdk = "$env:LOCALAPPDATA\Android\Sdk"
New-Item -ItemType Directory -Force "$sdk\cmdline-tools" | Out-Null
Invoke-WebRequest "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip" -OutFile "$env:TEMP\cmdtools.zip"
Expand-Archive "$env:TEMP\cmdtools.zip" "$sdk\cmdline-tools" -Force
Rename-Item "$sdk\cmdline-tools\cmdline-tools" "latest"
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $sdk, "User"); $env:ANDROID_HOME = $sdk

# 3. Accept licences, install the exact packages Flet uses
& "$sdk\cmdline-tools\latest\bin\sdkmanager.bat" --licenses          # press y, Enter, many times
& "$sdk\cmdline-tools\latest\bin\sdkmanager.bat" "platform-tools" "platforms;android-35" "build-tools;34.0.0"
```

Flutter itself is still downloaded by Flet on the first build.

## Part 7. Build the APK

```powershell
flet build apk --yes -v --build-version 0.1.0 --build-number 1
```

- `-v` prints progress, which is useful on a first build because it looks idle during large downloads.
- The build packages everything in `src\` (not `tests\`, `docs\`, or `tools\`).
- Smaller and faster for most phones (64-bit ARM only): add `--arch arm64-v8a`.
  Per-architecture files: add `--split-per-abi`, then use the `arm64-v8a` APK (the file name contains `arm64-v8a`) on a modern phone.

Result:

```powershell
dir build\apk\
```

An APK built without a keystore is **debug-signed**: it installs and runs fine for sideloading and judging.
Part 8 gives it a stable release identity.

## Part 8. Create a release keystore and sign

`keytool` ships with the JDK that Flet (or Option B) installed.

```powershell
$keytool = if ($env:JAVA_HOME) { "$env:JAVA_HOME\bin\keytool.exe" } else { "$env:USERPROFILE\java\17.0.13+11\bin\keytool.exe" }
& $keytool -genkeypair -v -keystore "$env:USERPROFILE\khapa-release.jks" -alias khapa `
  -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Khapa, O=Khapa, C=ZA"
```

It asks you for a password: choose a strong one and **write it down**. Keep the `.jks` file **outside the project folder** and back it up
(if you lose it you can never publish an update to the same app). Never commit it; `.gitignore` already blocks `*.jks`.

Tell Flet about it (these variables are read by `flet build`, so the password never lands in a file or in your history):

```powershell
$env:FLET_ANDROID_SIGNING_KEY_STORE = "$env:USERPROFILE\khapa-release.jks"
$env:FLET_ANDROID_SIGNING_KEY_ALIAS = "khapa"
$s = Read-Host "Keystore password" -AsSecureString
$pw = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
$env:FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD = $pw
$env:FLET_ANDROID_SIGNING_KEY_PASSWORD = $pw     # same password: PKCS12 keystores use one password
flet build apk --yes -v --build-version 0.1.0 --build-number 2 --arch arm64-v8a
```

Verify the signature (uses the build-tools Flet installed):

```powershell
$sdk = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } elseif (Test-Path "$env:LOCALAPPDATA\Android\Sdk") { "$env:LOCALAPPDATA\Android\Sdk" } else { "$env:USERPROFILE\Android\sdk" }
& "$sdk\build-tools\34.0.0\apksigner.bat" verify --verbose --print-certs (Get-ChildItem build\apk\*.apk | Select-Object -First 1).FullName
```

Look for `Verified using v2 scheme ... : true` and `CN=Khapa` in the certificate line.
Increase `--build-number` every time you rebuild, or Android refuses to install over the old one.

## Part 9. Sideload onto your phone

### Option A: USB with `adb` (most reliable, gives error messages)

1. On the phone: **Settings > About phone**, tap **Build number** 7 times. Then **Settings > System > Developer options > USB debugging** on.
2. Plug in, accept the **"Allow USB debugging?"** prompt on the phone.
3. On the PC:

```powershell
$sdk = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } elseif (Test-Path "$env:LOCALAPPDATA\Android\Sdk") { "$env:LOCALAPPDATA\Android\Sdk" } else { "$env:USERPROFILE\Android\sdk" }
$adb = "$sdk\platform-tools\adb.exe"
& $adb devices                                   # your phone must say "device", not "unauthorized"
& $adb install -r (Get-ChildItem build\apk\*.apk | Select-Object -First 1).FullName
& $adb shell pm list packages | Select-String khapa
```

To uninstall (needed if you switch from a debug-signed to a release-signed build, because the signatures differ):

```powershell
& $adb uninstall za.co.khapa.khapa
```

### Option B: copy the file

Copy the `.apk` to the phone (USB cable, Google Drive, WhatsApp-to-self). Open it from the Files app. Android asks you to allow
**"Install unknown apps"** for that app: allow it, then **Install**. If Google Play Protect warns *"unknown developer"*, tap **Install anyway**;
the app is yours and unpublished.

The app needs **no permissions** and makes **no network requests**. Turn on flight mode to prove it.

## Part 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `flet` not recognised | The venv is not active. Run `.\.venv\Scripts\Activate.ps1` |
| `Building with plugins requires symlink support` | Part 5: enable Developer Mode, reopen the terminal |
| Stuck at "Downloading Flutter" for ages | It is a large download; run with `-v` and wait. If it fails, rerun the same command |
| `Could not resolve` / `Name or service not known` | No internet, or a corporate proxy/firewall blocks `storage.googleapis.com`, `github.com`, `dl.google.com`. Try a phone hotspot |
| Licence errors / `sdkmanager` failures | Use Option B in Part 6 and answer `y` to every licence |
| `Java version 17 required` | Set `JAVA_HOME` to a JDK 17 (not 21) as in Part 6, Option B |
| Gradle `OutOfMemoryError` | `$env:GRADLE_OPTS = "-Xmx3g"` then rebuild |
| Path too long (Windows) | Move the project to a short path such as `C:\k\khapa-flet` |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | `adb uninstall za.co.khapa.khapa`, then install again |
| `INSTALL_FAILED_VERSION_DOWNGRADE` | Raise `--build-number` |
| App looks wrong after changing Flet versions | Delete the `build\` folder and rebuild |
| Want a clean slate | Delete `build\`, `%USERPROFILE%\flutter`, `%USERPROFILE%\java`, then rebuild |

If the build cannot be made to work in time, use **`flet run`** (Part 4). It runs exactly the same code. For remote judges the FNB
FAQ allows unpublished apps with remote access and login details: this app has **no logins**, so share the run instructions in `README.md`
or a `flet run --web` link.

## Part 11. macOS / Linux differences

- macOS: `brew install python@3.12`, `source .venv/bin/activate`, replace PowerShell variable syntax with `export NAME=value`. The SDK default is `~/Library/Android/sdk`.
- Linux: `sudo apt install python3.12-venv`; Flet's Linux desktop client also needs `libgtk-3-0 libmpv2` (and a display, or `xvfb`).
- Linux/macOS signing: use the same `keytool` flags; variables are identical (`export FLET_ANDROID_SIGNING_KEY_STORE=...`).
- **iOS is not covered and was not tested.** It needs macOS, Xcode, and an Apple developer account (`flet build ipa`).

## Part 12. Quick reference (after the first build)

```powershell
cd C:\path\to\khapa-flet
.\.venv\Scripts\Activate.ps1
pytest -q
flet build apk --yes --arch arm64-v8a --build-number 3
& $adb install -r (Get-ChildItem build\apk\*.apk | Select-Object -First 1).FullName   # $adb is defined in Part 9
```
