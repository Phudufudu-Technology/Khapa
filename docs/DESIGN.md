# Design notes

Priorities, in the order the brief set them: **(a)** the engine ported and tested, **(b)** the guided demo working end to end in Flet,
**(c)** `BUILD_APK.md`. UI polish was the thing to cut first. It was not needed, but some polish items are listed under "Not done".

## 1. Architecture

```
Flet UI (khapa_ui)  --calls-->  Session (khapa_core.session)  --uses-->  SyncNode x4, analytics, audit, SQLite store
        ^                              |
        +------ scope notifications ---+   ("chrome", "body", "demo", "devices")
```

- `khapa_core` imports only the standard library (a test enforces it). It is independent of Flet and testable with pytest alone.
- `Session` holds all behaviour: roles, language, the internet switch, saving marks, resolving conflicts, the guided demo, persistence.
  Because of that, the *entire* seven-step demo is tested without a UI.
- `khapa_ui` builds a Flet control tree once. A `Session` change emits a scope, and the app re-renders only that region and calls `.update()` on it.
- Views are pure functions `(ctx) -> list[Control]`; taps call back into `ctx`.

### Decisions (not relitigated from the brief)

| Decision | Reason |
|---|---|
| Pure Python, standard library only | Flet cannot reliably package native-extension libraries; the prototype's engine was already dependency-free |
| Single app with a role switcher | Judges try all four roles on one device |
| Same demo, content, thresholds, copy | Faithful port. Content is *generated* from `data.js` (`tools/gen_data.py`), never retyped |
| Pin Flet 1.0.5 | Flet's packaging story changes between releases |

## 2. How faithfulness was enforced

`tools/gen_golden.js` runs the prototype's own JavaScript and records its outputs (`tests/fixtures/js_golden.json`). The Python tests must reproduce:
every level boundary, every learner's risk level, reasons, weak topics and projection, edge-case series, and the full state of all four devices at each demo step.
JavaScript details that differ from Python are handled explicitly: `Math.round` rounds halves up (Python rounds to even), JS prints `41` where Python prints `41.0`,
and a falsy `gap` falls back to its default.

## 3. Deliberate differences from the prototype

| Change | Why | Effect on the demo |
|---|---|---|
| **Canary learner** `HP-0001`, stored and synced like real data but never listed | Requested honeypot | The store has 15 learners, the UI shows 14; no statistic includes it (tested) |
| SHA-256 digest on every event | Detect corruption and tampering | None visible |
| Strict validation (unknown keys, bool-as-number, control chars, id syntax, size limits) | Untrusted input | Same valid inputs behave identically |
| Remote clock bound of 7 days | A far-future timestamp would otherwise poison a clock forever (a known limitation in the earlier ADR) | None; the demo skew is 4 minutes |
| Mark values normalised (`38.0` becomes `38`) | Equal marks must hash equally | None |
| Sync quarantines a bad event instead of stalling the cursor | One poison event must not block a school's sync | None |
| Role guard on writes; audit log; Security panel | Requested security work | Extra panel under "Show devices and security" |
| SQLite persistence | Requested | App restores state on restart; "Reset demo data" |
| Comma decimals accepted (`38,5`) | South African locale habit | Input is more forgiving |
| Guide screen copy updated | The prototype said "runs in this page" and listed an installable app as not built. Those statements would now be untrue | Wording only |
| Bottom navigation instead of a top role bar | Phone-first | Same five destinations |
| First name shown bold in teacher notes | Readability on a narrow screen | Same words |

## 4. Trade-offs weighed

| Question | Chosen | Alternative and why not |
|---|---|---|
| Events: sign or hash? | **Hash** (integrity) | Signatures prove origin but need key management; a key shipped inside the app is not secret. Documented as a limitation |
| Persist state or events? | **Events** (event-sourced) | Persisting derived state would need its own conflict logic; replay re-verifies every digest |
| One database for all judges on the web? | **Memory per session** | A shared file would let judges overwrite each other |
| `sqlite3` or a pure-Python store? | **`sqlite3`** | Standard library, ships with Python for Android, atomic writes, bound parameters. Falls back to memory if unavailable |
| Timers | **Flet task runner** | A plain `threading.Timer` silently loses UI updates in Flet 1.0 (found while testing) |
| Wide tables | **Persistent scroll host** | Rebuilding the row resets its horizontal scroll on every sync (found while testing) |
| Real LLM now? | **No** (see section 7) | Packaging and demo risk against a deadline |

## 5. Edge cases handled (each has a test)

Clock goes backwards; clock skew of minutes; far-future timestamp; malformed timestamp; counter overflow; duplicate delivery; replay with changed content;
tampered event; tampered database row; unsupported schema version; unwritable or vanished storage; restart mid-conflict; three-way concurrent edits to one mark;
sync in any order; a mark that supersedes itself; a duplicate entity id under a new event id; NaN, infinity, booleans, negative and out-of-range marks;
comma decimals and arabic-indic digits; control characters and log injection; SQL-injection text; oversize comment; non-teachers attempting writes;
a parent opening another child's record; the canary being opened; the Flet "toast is also a dialog" trap; UI handler exceptions; theme switch mid-session.

## 6. Known limitations and unknowns (be sceptical of these)

- **Causal delivery.** A quarantined event is skipped for good, so later events that depend on it are quarantined too. Acceptable here because the cloud relays in log order; a real hub needs a retry queue.
- **Digest is not authenticity.** Anyone who can write the SQLite file can recompute digests. The audit chain has the same limit and cannot detect truncation of its tail.
- **Guard coverage is partial.** Writes, opening a learner record, and the security probes go through the guard. Screens still read names and marks from the shared fixtures, as the prototype did, and the parent/learner "view as" picker is a demo convenience that deliberately bypasses per-user access.
- **Performance.** `pending_for` is O(events) and runs on every render. Fine for about 90 events; a real hub needs an index.
- **Accessibility** was designed for (labels, tooltips, 44 px targets, contrast from the prototype palette, text scaling) but **not audited** with TalkBack or VoiceOver.
- **Android specifics** (back button with an open dialog, keyboard resizing, notch insets) are untested on a device.
- **Web mode** serves the app, but a real browser session was not driven in the author's sandbox.
- Timestamps in the log use the device's local time zone.
- The CAPS scale thresholds are indicative and need checking against DBE documents before production (as the prototype already says).

## 7. Offline language model (stretch, not started)

**Goal.** Make suggestions read better (plain language at the right reading level, in the learner's language) without ever deciding who is flagged.

**Rules for any model.**
1. Flags, levels and projections stay rule-based. A model may only *rephrase* an existing rule-based tip, never create a flag or change a number.
2. The AI disclosure stays visible next to every model-written line.
3. No personal data in prompts: send topic, level and audience only, never names.
4. If the model is missing, slow, or returns something that fails a check (length, banned content, contains a number not in the input), show the rule-based tip.
5. Output is cached per (topic, level, audience, language) so the same learner always sees the same text.

**How.** Implement `LocalModelSuggester` behind the existing `Suggester` interface. Ship it **off by default** and **outside the APK** at first.

**Why not now.**
- Running a model on a phone needs native code (for example llama.cpp or ONNX Runtime), the exact packaging problem that made the standard-library-only decision.
- Model weights are large (a quantised model of roughly 0.5 to 1.5 billion parameters is hundreds of MB; these figures are estimates and nothing was benchmarked), which hurts install size and start-up on low-end phones.
- Machine-written isiZulu or Afrikaans would break this project's honesty rule unless reviewed by a human speaker.
- Nothing about the judged demo improves enough to justify the risk before the deadline.

**First experiment, if time allows.** On desktop only, with a small open-licence model, measure latency and run a fixed set of golden prompts to check that rules 1 to 4 hold. Decide on Android only after that data exists.

## 8. Not done

A signed APK or IPA; a device test; a hosted static web build of the Flet app; a screen-reader audit; richer charts (the sparkline is drawn on a canvas, not with a chart library).
