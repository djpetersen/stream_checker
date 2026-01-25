# Deep Code Review - Additional Issues Found

## Critical Logic Errors

### 1. Ad Detection Logic Error
**File:** `stream_checker/core/ad_detection.py`
**Issue:** When metadata is None, we still update `last_title` and `last_genre` with previous values, but we should only update when metadata exists
**Line:** 105-106
**Impact:** Incorrect ad break tracking

### 2. Missing None Check in SSL Certificate
**File:** `stream_checker/core/connectivity.py`
**Issue:** `hostname` could be None, causing socket connection to fail
**Line:** 141
**Impact:** Potential AttributeError

### 3. Window Size Edge Case
**File:** `stream_checker/core/audio_analysis.py`
**Issue:** If `sample_rate` is 0 or very small, `window_size` could be 0, causing division by zero
**Line:** 247
**Impact:** Runtime errors

### 4. Bare Exception Handlers
**Files:** 
- `player_test.py:253` - bare `except:`
- `connectivity.py:408` - bare `except Exception:`
**Impact:** Hides bugs, makes debugging difficult

## Security Issues

### 5. Subprocess Calls
**Status:** ✅ Safe - All subprocess calls use lists, not shell=True
**Files:** `player_test.py`, `audio_analysis.py`

### 6. SQL Injection
**Status:** ✅ Safe - All queries use parameterized statements

### 7. Path Traversal
**Status:** ✅ Safe - URL validation prevents path traversal

## Thread Safety Issues

### 8. PlayerTester Shared State
**File:** `stream_checker/core/player_test.py`
**Issue:** Instance variables (`_playback_errors`, `_buffering_events`, etc.) accessed from callbacks without locks
**Impact:** Race conditions in multi-threaded scenarios (though VLC callbacks are single-threaded)

## Edge Cases

### 9. Empty Response Handling
**File:** `stream_checker/core/connectivity.py`
**Issue:** No check if `response.text` is None in HLS check
**Line:** 468

### 10. Division by Zero in Silence Detection
**File:** `stream_checker/core/audio_analysis.py`
**Issue:** Already handled, but could be more explicit

### 11. Missing Validation for Config Values
**File:** `stream_checker/utils/config.py`
**Issue:** No validation that config values are within expected ranges

## Performance Issues

### 12. Multiple Requests to Same URL
**File:** `stream_checker/core/connectivity.py`
**Issue:** Multiple separate requests to the same URL (HEAD, GET for params, GET for metadata, GET for ICY)
**Impact:** Unnecessary network overhead

### 13. No Connection Pooling
**Issue:** Each request creates a new connection
**Impact:** Slower performance, more resource usage

## Code Quality

### 14. Magic Numbers
**Files:** Multiple
**Issue:** Hard-coded values (timeouts, thresholds, sizes)
**Impact:** Hard to configure

### 15. Missing Type Hints
**Files:** Some callback methods
**Issue:** Missing return type hints
