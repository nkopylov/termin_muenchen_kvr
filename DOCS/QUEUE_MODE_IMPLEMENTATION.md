# Queue Mode Implementation - UX Fix

## Problem
Users in interactive booking conversations were receiving appointment notifications, breaking the UX flow and causing confusion.

## Solution: Queue Mode
When a user enters the booking conversation, notifications are **paused** for that specific user. Notifications resume automatically when booking completes, is cancelled, or times out.

## Implementation Details

### 1. Global State Tracking
**File:** `telegram_bot.py:49`
```python
# Track users currently in booking conversation (to pause notifications)
active_booking_users = {}  # {user_id: timestamp}
```

### 2. Notification Filtering
**File:** `telegram_bot.py:433-442`
- Before sending notifications, check if user is in `active_booking_users`
- Skip notification if user is in booking mode
- Auto-timeout stale sessions after 10 minutes

### 3. Entry Point - Start Booking
**File:** `booking_handler.py:39-44`
- When user clicks booking button, add to `active_booking_users`
- Timestamp stored for timeout tracking

### 4. Exit Points - Clear Booking State
User is removed from `active_booking_users` in these scenarios:

| Exit Point | Location | Trigger |
|------------|----------|---------|
| Booking completed | `confirm_booking()` | Success or failure |
| User cancelled | `confirm_booking()` | Cancel button clicked |
| User cancelled | `time_selected()` | Cancel at time selection |
| User cancelled | `cancel_booking_conversation()` | Command issued during booking |
| Invalid data | `start_booking()` | Bad callback data |
| Token expired | `start_booking()` | Captcha token missing |
| No slots | `start_booking()` | No time slots available |
| No appointments | `start_booking()` | Empty appointments list |
| Timeout | `check_and_notify()` | 10 minutes inactive |

## Behavior

### Normal Flow
```
User clicks "Book Appointment"
  → Added to active_booking_users
  → Notifications PAUSED for this user
  → User completes booking steps
  → Removed from active_booking_users
  → Notifications RESUMED
```

### Timeout Protection
```
User starts booking but abandons it
  → After 10 minutes: automatically removed from active list
  → Notifications resume automatically
```

### Other Users Unaffected
```
User A enters booking mode
  → User A notifications paused
  → User B, C, D continue receiving notifications normally
```

## Testing Checklist

- [ ] Start booking → Complete successfully → Verify notifications resume
- [ ] Start booking → Cancel at time selection → Verify notifications resume
- [ ] Start booking → Cancel at confirmation → Verify notifications resume
- [ ] Start booking → Issue /command → Verify notifications resume
- [ ] Start booking → Wait 10+ minutes → Verify auto-timeout works
- [ ] Multiple users booking simultaneously → Verify no cross-interference

## Logging

All state changes are logged with pattern:
```
User {user_id} entered booking mode - notifications paused
User {user_id} exited booking mode - notifications resumed
Skipping notification for user {user_id} - booking in progress
```

## Configuration

Timeout duration: **10 minutes** (600 seconds)
- Location: `telegram_bot.py:437`
- Adjustable via constant if needed
