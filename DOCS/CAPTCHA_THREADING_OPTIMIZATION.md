# CAPTCHA Threading Optimization

## Overview

This document describes the optimization implemented to move CPU-intensive CAPTCHA solving operations to a background thread pool, preventing blocking of the main async event loop.

## Problem

The Munich appointment system uses a proof-of-work CAPTCHA challenge that requires:
1. Fetching a challenge from the server
2. **Solving the challenge** (CPU-intensive: iterating through millions of SHA-256 hashes)
3. Verifying the solution with the server

The solving step can take several seconds and was blocking the entire event loop, preventing the bot from:
- Processing user commands
- Sending notifications
- Handling callbacks

## Solution

Moved CAPTCHA solving to a dedicated thread pool using Python's `concurrent.futures.ThreadPoolExecutor`.

### Implementation Details

**File:** `src/termin_tracker.py`

#### Thread Pool Configuration
```python
_captcha_executor = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="captcha-solver"
)
```

- **max_workers=2:** Allows 2 concurrent CAPTCHA solving operations
- **thread_name_prefix:** Makes thread debugging easier in logs

#### Converted to Async-Only

The `get_fresh_captcha_token()` function is now async-only:
- Runs all CAPTCHA operations in the thread pool via `loop.run_in_executor()`
- Returns JWT token
- Doesn't block the event loop during CPU-intensive solving
- Synchronous version removed (not needed anywhere in codebase)

## Usage

**Before (blocking):**
```python
captcha_token = get_fresh_captcha_token()  # Blocked event loop for 2-5 seconds (sync)
```

**After (non-blocking):**
```python
captcha_token = await get_fresh_captcha_token()  # Runs in background thread (async)
```

## Impact

### Performance Benefits

1. **Event Loop Responsiveness:**
   - Bot remains responsive during CAPTCHA solving
   - User commands processed immediately
   - Notifications not delayed

2. **Concurrent Operations:**
   - Bot can handle user interactions while solving CAPTCHA
   - Multiple CAPTCHA operations can run simultaneously (up to 2)

3. **Typical CAPTCHA Solving Time:**
   - Usually 1-5 seconds depending on challenge difficulty
   - Previously blocked all bot operations during this time
   - Now runs in background without blocking

### Resource Usage

- **Threads:** 2 dedicated threads in the pool
- **Memory:** Minimal overhead per thread (~1-2 MB)
- **CPU:** Same CPU usage, just isolated from event loop

## Logging

New log messages indicate threading:
```
INFO - Getting fresh captcha token (async in thread pool)...
INFO - Solving captcha in background thread...
INFO - Got fresh token (solved in background thread)
```

## Files Modified

1. **src/termin_tracker.py**
   - Added `ThreadPoolExecutor` import and initialization
   - Added `get_fresh_captcha_token_async()` function
   - Documented the synchronous version

2. **src/services/appointment_checker.py**
   - Changed import to use `get_fresh_captcha_token_async`
   - Updated function call to use `await`
   - Updated log messages

## Testing Checklist

- [x] CAPTCHA solving works correctly in thread pool
- [x] Bot remains responsive during CAPTCHA operations
- [x] User commands processed while CAPTCHA solving
- [x] Token refresh happens without blocking
- [x] No race conditions or thread safety issues
- [x] Proper error handling in async context

## Thread Safety Notes

- **Thread Pool:** Managed by Python's `concurrent.futures`, thread-safe by design
- **HTTP Requests:** Munich API client uses `requests` library (thread-safe)
- **SHA-256 Hashing:** `hashlib` is thread-safe
- **No Shared State:** Each CAPTCHA operation is independent

## Future Enhancements

Possible improvements for the future:

1. **Dynamic Thread Pool Size:** Adjust based on load
2. **Priority Queue:** Prioritize user-initiated CAPTCHA requests
3. **Pre-solving:** Start solving next CAPTCHA before current token expires
4. **Metrics:** Track CAPTCHA solving times and success rates

## Rollback Plan

If issues arise:
1. Change import back to `get_fresh_captcha_token` in `appointment_checker.py`
2. Remove `await` keyword
3. Revert changes to `termin_tracker.py`

No database changes, no config changes required.

---

**Date:** October 9, 2025
**Version:** 2.2.1 (Threading Optimization)
**Performance:** Event loop no longer blocked during CAPTCHA solving
**Tested:** ✅ All checks passed
