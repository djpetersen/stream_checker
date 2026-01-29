# Audio Analysis Blanks: DB Analysis & Code-Path Report

**Source:** Most recent 100 test runs from `~/.stream_checker/stream_checker.db`  
**Script:** `tests/analyze_100_stream_audio_blanks.py`

---

## 1. Summary Table (streams with blank/missing/not-tested audio)

Run the script to regenerate the full table:

```bash
python tests/analyze_100_stream_audio_blanks.py
```

**Schema of the table:**

| Column | Description |
|--------|-------------|
| **Stream ID** | `stream_id` from `test_runs` |
| **URL** | Stream URL (from `streams.url` or `results.stream_url`), truncated |
| **Blank fields** | Which audio fields are missing/blank: e.g. `audio_analysis missing`, `error set: Failed to load audio data`, `phase<3 (audio not run)` |
| **Phase** | Stored phase (1–4) for that row |
| **Timestamp** | `test_runs.timestamp` |
| **Stored error** | `results.audio_analysis.error` if set |

**Observed blank-pattern counts (from last run):**

| Pattern | Count | Description |
|---------|-------|-------------|
| `all_present` | 52 | Audio analysis present and populated (excluded from “blanks” table) |
| `error_failed_to_load_audio_data` | 26 | Phase 3 ran; download succeeded but ffmpeg raw load failed |
| `error_failed_to_download_audio_sample` | 19 | Phase 3 ran; all ffmpeg download strategies failed |
| `no_audio_analysis_section` | 3 | Row has phase ≥3 but `results` has no `audio_analysis` key |

---

## 2. Top blank patterns: code paths and causes

### Pattern 1: `error_failed_to_load_audio_data` (26)

- **DB evidence:** `results.audio_analysis` exists, `results.audio_analysis.error == "Failed to load audio data"`. Phase = 3 or 4. Sub-fields `silence_detection` / `error_detection` / `audio_quality` are the initial defaults (e.g. `silence_percentage: 0`, quality `None`), not filled by analysis.
- **Code path that writes these fields:**
  - **`stream_checker/core/audio_analysis.py`**
    - **Lines 86–90:** When `_load_audio_raw(audio_file)` returns `(None, 0, 0)`, the code sets `result["error"] = "Failed to load audio data"` and returns the same `result` dict that was initialized at 44–63 (defaults only). No call to `_detect_silence` / `_analyze_quality` / `_detect_errors`, so those sub-fields stay default.
    - **Lines 272–357 (`_load_audio_raw`):** Returns `None, 0, 0` when: `success` is False (301–307), `returncode != 0` (309–312), no stdout / empty raw data (316–318), zero samples (321–324), reshape/exception paths (331, 341, 357).
  - **`stream_checker.py` lines 571, 578:** `result["audio_analysis"] = audio_result` and `db.add_test_run(test_run_id, stream_id, 3, result)` persist that structure.
- **Likely cause:** ffmpeg decode of the downloaded file to raw PCM failed (timeout, non-zero exit, empty stdout, or exception). The result is an **explicit error string** but **implicit “blank” sub-fields** (defaults), which UIs can treat as missing data unless they check `error`.

---

### Pattern 2: `error_failed_to_download_audio_sample` (19)

- **DB evidence:** `results.audio_analysis` exists, `results.audio_analysis.error == "Failed to download audio sample"`. Phase = 3 or 4. Same default sub-fields as above.
- **Code path that writes these fields:**
  - **`stream_checker/core/audio_analysis.py`**
    - **Lines 73–76:** When `_download_audio_sample(url)` returns `None`, the code sets `result["error"] = "Failed to download audio sample"` and returns the initial `result` (44–63). No download file ⇒ no `_load_audio_raw` or analysis.
    - **Lines 172–270 (`_download_audio_sample`):** Returns `None` when: ffmpeg not found (177–178), all strategies fail (264–266), or exception (267–268). Each strategy uses `run_subprocess_safe` (224–228); non-zero return or empty file causes “continue” and eventually `return None`.
  - **`stream_checker.py` 571, 578:** Same write path as above.
- **Likely cause:** All ffmpeg download strategies failed (e.g. connection/timeout, codec, or server errors). Again, **error is explicit**, sub-fields are **implicit blanks** (initial defaults).

---

### Pattern 3: `no_audio_analysis_section` (3)

- **DB evidence:** Row has `phase` = 4 (and in one case stream `d6347874ccd4b656`, URL `https://test-streams.mux.dev/...`). `results` JSON has **no** `audio_analysis` key. So the DB row is phase 4 but the stored payload never had Phase 3 audio results.
- **Code path that writes the phase-4 row:**
  - **`stream_checker-web/api/app.py`**
    - **Lines 356–367:** If `tests.get("ad_detection")` and `phase >= 4`, ad detection runs and then `db.add_test_run(test_run_id, stream_id, 4, result)` is called with the **current in-memory `result`**. There is no merge of prior phase results from the DB; `result` only contains what was run in this request.
    - **Lines 327–335:** `audio_analysis` is added to `result` only when `tests.get("audio_analysis") and phase >= 3`. If the client requested phase 4 but did **not** request `audio_analysis`, Phase 3 is skipped and `result` never gets `audio_analysis`.
  - **CLI equivalent:** `stream_checker.py` runs phases in order (496–618). If the user ran with `--phase 4` only (or a wrapper that only runs phase 4), Phase 3 would not run and `result` would have no `audio_analysis` when Phase 4 is saved (613–614).
- **Likely cause:** **Phase skipped:** either (a) Web UI request with phase ≥ 4 and “audio analysis” unchecked, or (b) CLI/API run that only executed phase 4. The write transaction **is** committed (models.py 282); the “blank” is that the **in-memory result** for that run never included Phase 3, so `audio_analysis` is absent by design for that request, not due to schema or commit failure.

---

### Pattern 4 & 5: (Only 3 blank patterns in this dataset)

There were no other recurring blank patterns in the sample. If future data shows:

- **`error_other`** (exception in `analyze()`): Written at **`audio_analysis.py` lines 96–99:** `result["error"] = str(e)` and return; same default sub-fields.
- **Phase &lt; 3:** Rows with phase 1 or 2 only; `audio_analysis` is not run, so missing by design. Written by **`stream_checker.py`** phase 1/2 branches and **`models.py`** `add_test_run` (279–281 or 265–268).

---

## 3. Root-cause summary (evidence-based)

| Pattern | Primary cause | Where it happens |
|---------|----------------|------------------|
| `error_failed_to_load_audio_data` | ffmpeg raw decode failed (timeout / exit code / empty data / exception) | `audio_analysis.py` `_load_audio_raw` → early return; `analyze()` sets `error` and returns defaults (86–90) |
| `error_failed_to_download_audio_sample` | All ffmpeg download strategies failed | `audio_analysis.py` `_download_audio_sample` returns None; `analyze()` sets `error` and returns defaults (73–76) |
| `no_audio_analysis_section` | Phase 3 not run for that request (audio_analysis unchecked or --phase 4 only) | API/CLI never add `audio_analysis` to `result` before `add_test_run(..., 4, result)` (API app.py 356–367; CLI 613–614) |

No evidence for: schema mismatch (same JSON shape used everywhere), or write transaction not committed (commit at models.py 282).

---

## 4. Minimum changes: blanks → explicit error state

Goal: Ensure every “blank” or failed audio run is represented as an **explicit error state** with **consistent fields**, so UIs and reports can treat them uniformly (e.g. “error” + reason, no ambiguity with “missing”).

### 4.1 Audio analyzer: always set a canonical error and status

**File:** `stream_checker/core/audio_analysis.py`

- After initializing `result` (44–63), add a single **`status`** field, e.g. `"status": "ok"` or `"status": "error"`.
- On **any** early return or exception:
  - Set `result["status"] = "error"`.
  - Ensure `result["error"]` is set (already done for "Failed to download..." and "Failed to load..."; for exceptions at 96–99 it’s already set).
  - Optionally set **explicit placeholders** for sub-fields so consumers don’t have to infer “blank”:
    - e.g. `result["silence_detection"] = {"status": "skipped", "reason": result["error"]}` and similarly for `error_detection` and `audio_quality` (or a single `result["skipped_reason"]"] = result["error"]` and keep one place that documents “if status==error, these are not populated”).
- On **success**, set `result["status"] = "ok"` before return (e.g. after line 95).
- **Minimal version:** At least set `result["status"] = "error"` on every early return and in the `except` block (97–99), and `result["status"] = "ok"` on the success path. That gives a single, consistent field to distinguish “ran and succeeded” vs “error / not actually analyzed.”

### 4.2 API: always attach an audio_analysis object for phase ≥ 3

**File:** `stream_checker-web/api/app.py`

- When `phase >= 3` (or when ad detection runs and phase >= 4), ensure `result` **always** contains an `audio_analysis` key for that run:
  - If `tests.get("audio_analysis")` is True: keep current behavior (run Phase 3, set `result["audio_analysis"] = audio_result`).
  - If `tests.get("audio_analysis")` is False but we’re saving phase 4: set  
    `result["audio_analysis"] = {"status": "skipped", "reason": "audio_analysis not requested"}`  
    before `db.add_test_run(..., 4, result)` (around 367). Then every phase-4 row has a defined `audio_analysis` shape; “blank” becomes an explicit “skipped” state.
- Optional: When Phase 3 throws (339–334), the existing `result["audio_analysis"] = {"status": "error", "error": ...}` already provides an explicit error; ensure it matches the same `status` + `error` convention as the analyzer.

### 4.3 CLI: same idea for phase-only runs

**File:** `stream_checker.py`

- When `4 in phases_to_run` but `3 not in phases_to_run`, before running Phase 4 (e.g. before 586), set  
  `result["audio_analysis"] = {"status": "skipped", "reason": "phase 3 not run"}`  
  so the saved phase-4 payload always has an `audio_analysis` key when phase 4 is run without phase 3.

### 4.4 DB / models

- No schema change required. `results` is a JSON blob; adding `status` and optional `skipped_reason` inside `audio_analysis` is backward compatible. Existing rows without `status` can be treated as “legacy” and interpreted as “error” if `error` is set, “ok” if `error` is absent and sub-fields are present.

### 4.5 Summary of minimal edits

1. **audio_analysis.py:** Set `result["status"] = "ok"` on success and `result["status"] = "error"` (and keep `result["error"]`) on every failure path; optionally add explicit placeholder sub-fields for error/skip cases.
2. **api/app.py:** When saving phase 4 without running Phase 3, set `result["audio_analysis"] = {"status": "skipped", "reason": "..."}`.
3. **stream_checker.py:** When running phase 4 only, set `result["audio_analysis"] = {"status": "skipped", "reason": "phase 3 not run"}` before Phase 4.

This yields consistent, explicit states: `ok`, `error`, or `skipped`, with no reliance on “missing key” or “default-looking” sub-fields to infer failure.
