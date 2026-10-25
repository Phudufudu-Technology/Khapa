# Build the APK in the cloud (GitHub Actions): no Android toolchain needed

Use this if you cannot or do not want to install Flutter, a JDK and the Android SDK on your PC.
A free GitHub runner builds the APK for you and gives you a download link for judges.

> **Not verified.** The author could not run this workflow (the author's sandbox has no GitHub Actions and no Android/Flutter access).
> It uses the same `flet build apk` command that Flet 1.0.5 documents and that `BUILD_APK.md` explains.
> The first run may need a fix. Read the failed step's log; Part 5 lists the likely causes. Keep the local route in `BUILD_APK.md` as plan B.

| | |
|---|---|
| Cost | Free (GitHub account). Private repositories get a monthly allowance of free build minutes; public ones are free. |
| Time | First run is long (estimate 15 to 40 minutes, not measured). Later runs are faster. |
| Output | `khapa-apk` artifact (a zip containing the `.apk`), or a public Release download if you push a tag |
| Signing | Debug-signed by default. It installs fine for judging. For a release key see `BUILD_APK.md` Part 8 and add the values as GitHub *secrets* (never in the repo) |

## Part 1. Put the project on GitHub

1. Create a free account at https://github.com and click **New repository**. Name it `khapa`. **Public** lets judges download the APK without logging in
   (it also makes the source public: it contains only fictional data and no secrets; `.gitignore` blocks keystores and databases). Choose **Private** if you prefer, and share the APK another way.
2. Upload the project, **contents of the `khapa-flet` folder** (not the folder itself).

**Option A: with Git** (install with `winget install Git.Git`, then reopen the terminal):

```powershell
cd C:\path\to\khapa-flet
git init -b main
git add .
git commit -m "Khapa Flet entry"
git remote add origin https://github.com/YOUR-NAME/khapa.git
git push -u origin main
```

**Option B: in the browser:** on the new repository page click **uploading an existing file**, drag in the *contents* of the folder, then **Commit changes**.
Then check that the file `.github/workflows/build-apk.yml` exists in the repository. (The folder name starts with a dot, so some tools hide or skip it. A normal, visible copy of the same file is at `docs/build-apk.yml`.) If it is missing (hidden folders are sometimes skipped), click **Add file > Create new file**,
type `.github/workflows/build-apk.yml` as the name (typing the slashes creates the folders), paste the contents of `docs/build-apk.yml`, and commit.

## Part 2. Run the build

1. In the repository, open the **Actions** tab. If asked, click **I understand my workflows, go ahead and enable them**.
2. Click **Build Android APK** in the left list, then **Run workflow > Run workflow**.
3. Click the new run to watch it. The steps are: install, tests (must pass), `flet --version`, build, collect the APK, upload.
4. When it finishes green, scroll to **Artifacts** at the bottom of the run page and download **khapa-apk**. Unzip it to get the `.apk`.

## Part 3. A public link for judges (recommended)

**With Git:**

```powershell
git tag v0.1.0
git push origin v0.1.0
```

This starts a build and, when it finishes, attaches the APK to a **Release**. The link to give judges is:

```
https://github.com/YOUR-NAME/khapa/releases/tag/v0.1.0
```

**Without Git:** open the repository, click **Releases > Draft a new release**, type `v0.1.0` as the tag, drag the `.apk` into the files box, and **Publish release**.

Put that link on the deck's *Demo access* slide and in your Sonke submission.

## Part 4. Install and check on a phone

1. Open the Release link on the phone and download the `.apk`.
2. Allow **Install unknown apps** for the browser or Files app when asked. If Play Protect warns about an unknown developer, tap **Install anyway**.
3. Open Khapa, tap **Play the guided demo**, then try **flight mode**: the app needs no network.
4. If the phone is old and the app will not install, ask for a 32-bit build: change `--arch arm64-v8a` to `--arch armeabi-v7a` in the workflow and run it again.

## Part 5. If the build fails

| What you see | Likely cause and fix |
|---|---|
| Red X at **Tests must pass** | A test failed on the runner. Open the step and read the failing test name |
| Red X at **Build APK**, an error about Flutter, Java or Android licences | Open the log and search for the first line that says `error`. Rerun once (downloads sometimes fail). If it repeats, use `BUILD_APK.md` locally |
| `No file was found` at **Keep the APK** | The build produced no `.apk`. Look at the **Collect the APK** step's `ls` output and the **Build APK** log's last lines |
| Release step fails with a permissions error | Repository **Settings > Actions > General > Workflow permissions**: choose **Read and write permissions**, then rerun |
| The Actions tab shows no workflow | `.github/workflows/build-apk.yml` is missing or misplaced. See Part 1, Option B |

## Plan B if the APK cannot be produced in time

Submit the project zip as the "build file" with `README.md`: judges can run it with one command (`run_demo.ps1` or `run_demo.sh`) and no login. Say plainly in the submission that the APK is not included and why.
