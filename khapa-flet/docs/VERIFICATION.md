# Verification record

What was checked, how, what it proves, and what it does not. Environment for everything below: a Linux sandbox, Python 3.12.3,
Flet 1.0.5 (Flutter 3.44.8 as reported by `flet --version`), no GPU, no physical phone.

## 1. Evidence

| Claim | Evidence | Reproduce |
|---|---|---|
| The engine and analytics behave like the prototype | Prototype's own JS tests (49) pass; the Python port reproduces the JS output exactly (levels, every learner's flag and reasons, edge series, all four devices at every demo step) | `node --test` in the prototype; `pytest tests/test_analytics_parity.py` |
| The sync rules hold | 57 engine tests incl. 25 randomised multi-node runs and sync-order independence | `pytest tests/test_engine.py` |
| The tests can fail | Five deliberate bugs injected one at a time: conflicts never flagged; per-field LWW ignoring clocks; clock ignoring remote timestamps; a changed risk threshold; digests not verified. **All five made the suite fail**; the original code passed | Edit the line, run `pytest -x`, revert |
| The core is standard library only | AST check of every import in `khapa_core` | `pytest tests/test_i18n_purity.py` |
| The whole demo works without a UI | 37 session tests incl. the seven steps, restart mid-conflict, tampered DB, unwritable storage | `pytest tests/test_session_demo.py` |
| The UI builds and behaves | 27 tests on real Flet 1.0.5 control trees with a stubbed page connection | `pytest tests/test_ui.py` |
| **It runs in the real Flet client** | The real Flet 1.0.5 desktop client (Flutter) ran under Xvfb at 390x800. Screens captured: guide, teacher grid, parent (stale banner and caught up), learner, principal heat map, learner dialog, mark dialog (typed `91,5`, saved as 91.5, dialog closed, chip returned to synced), conflict dialog listing both values and who entered them, devices and audit panel, dark mode, language notice | `python tools/shoot.py OUT "click:140,446;wait:2;shot:demo"` (needs `xvfb xdotool scrot libgtk-3-0t64 libmpv2`) |
| The seven demo steps run in the real client | Clicked through all seven in the real client; banners, chip, stale banner, projection change (47.7 to 47.8) and end card observed | Screenshots in `docs/screenshots/` |
| Web mode serves | `flet run --web --port 8551` returned HTTP 200 | `flet run --web src/main.py` |
| `flet build apk` accepts this project | The command parsed `pyproject.toml` and began, then stopped at the Flutter download because the sandbox is offline | `flet build apk --yes` |

Totals: **381 tests**. Run `pytest -q`.

## 2. Bugs this process found (and fixed)

| Found by | Bug |
|---|---|
| Engine tests | A NaN mark raised `ValueError` while hashing instead of a clean rejection |
| Real client | Header wrapped badly because a spacer used `expand` inside a wrapping row |
| Real client | Timer callbacks (auto-sync, highlight fade) ran outside Flet's page context, so their updates were silently dropped. Fixed by scheduling through `page.run_task` |
| Real client | Every sync reset the marks grid's horizontal scroll. Fixed with persistent scroll hosts |
| UI tests | After saving, `pop_dialog()` closed the "Saved" toast (also a dialog) and left the mark dialog open. Fixed by closing each dialog explicitly |
| Real client | A "0/6" character counter on the mark field. Removed |

## 3. Caveats about the screenshots

Under software rendering in a virtual display the Flutter client may not repaint until it receives input, so a screenshot taken straight after a scripted change
can show a stale frame. The runner nudges the pointer first. Several early captures were stale and were discarded; conclusions above rest on captures that were
confirmed with real mouse clicks. The scripted runner (`tools/scenario.py`) cannot reliably drive dialogs, so dialogs were verified with real clicks.
These are properties of the test rig, not of the app, but they mean the screenshots are evidence of rendering, not a substitute for a device test.

## 4. Not verified

- Android APK build, install and run; any physical phone
- iOS
- Windows and macOS desktop windows (Linux only)
- A real browser session against `flet run --web`; behaviour with several simultaneous judges
- Screen-reader and accessibility tooling
- Performance and battery on a low-end phone
- Any offline language model (not built)

## 5. Static analysis and dependency audit (24 October 2026)

| Check | Result | Reproduce |
|---|---|---|
| `bandit` on `src/` (2,573 lines, 21 files) | 0 high, 0 medium, **5 low**. All five are `B110 try/except/pass`: deliberate best-effort fallbacks (UI scroll, toast, language preference, persistence) | `pip install bandit; bandit -r src` |
| `pip-audit` on `requirements.txt` (`flet[all]==1.0.5` and its resolved dependencies) | **No known vulnerabilities found** at the time of the run. This reflects the public advisory data that day, not a guarantee | `pip install pip-audit; pip-audit -r requirements.txt` |

Not run: fuzzing, a penetration test, dynamic analysis, a secrets scanner, or an independent code review.

## 6. How to re-verify quickly on your own machine

```
pip install -r requirements-dev.txt
pytest -q                          # expect 381 passed
flet --version                     # expect Flet 1.0.5 / Flutter 3.44.8
flet run src/main.py               # play the guided demo
```
