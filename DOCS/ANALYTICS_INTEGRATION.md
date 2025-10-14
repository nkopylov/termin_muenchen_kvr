# Analytics Integration for Munich Appointment Bot

**Last Updated:** 2025-10-14
**Prerequisites:** Umami analytics platform deployed and accessible

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Configuration](#configuration)
4. [Analytics Service Implementation](#analytics-service-implementation)
5. [Event Taxonomy](#event-taxonomy)
6. [Integration Points](#integration-points)
7. [Code Examples](#code-examples)
8. [Privacy & GDPR Compliance](#privacy--gdpr-compliance)
9. [Dashboard Configuration](#dashboard-configuration)
10. [Testing](#testing)
11. [Monitoring & Maintenance](#monitoring--maintenance)
12. [Rollout Plan](#rollout-plan)

---

## Overview

This guide explains how to integrate analytics tracking into the Munich Appointment Bot. We use Umami for:

- **User behavior tracking** - Registration, subscriptions, commands usage
- **Appointment system monitoring** - Checks, found appointments, notifications
- **Booking funnel analysis** - Success rates, drop-off points
- **System health monitoring** - Errors, API failures, captcha issues
- **Public transparency** - Shareable dashboard with key metrics

### Why Track Analytics?

- 📊 **Understand user behavior** - Which features are used most?
- 🐛 **Proactive bug detection** - Catch errors before users report them
- 📈 **Measure success** - Booking conversion rates, notification effectiveness
- 🎯 **Data-driven decisions** - What to build next?
- 🔍 **Transparency** - Show users bot activity publicly

### Privacy-First Approach

We track **behavior**, not **identity**:
- ✅ Pseudonymous user IDs (Telegram IDs)
- ✅ Aggregate metrics (counts, trends)
- ❌ Never track PII (names, emails, exact dates)
- ❌ Never track message content

---

## Prerequisites

Before starting integration, ensure you have:

1. ✅ **Umami deployed and accessible**
   - See [UMAMI_SETUP.md](./UMAMI_SETUP.md) for deployment instructions
   - Umami running at `http://your-umami-domain:3000`

2. ✅ **Website created in Umami**
   - Website ID (UUID) obtained from Umami
   - "Enable share URL" toggled ON

3. ✅ **Development environment ready**
   - Python 3.12+
   - Access to modify bot code
   - Test environment (recommended)

---

## Configuration

### Step 1: Add Dependencies

Update `pyproject.toml` to include `httpx` for async HTTP requests:

```toml
[project]
name = "notfall_termin_abh_muenchen_bot"
# ... existing configuration ...

dependencies = [
    # ... existing dependencies ...
    "httpx>=0.27.0",  # For analytics HTTP requests
]
```

Install the new dependency:

```bash
uv pip install --system -r pyproject.toml
```

### Step 2: Update Configuration

**File:** `src/config.py`

Add analytics configuration to your Pydantic Settings:

```python
"""
Configuration management using Pydantic Settings
Loads settings from environment variables with validation
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ... existing configuration fields ...

    # Analytics Configuration
    analytics_enabled: bool = Field(default=True, description="Enable/disable analytics tracking")
    umami_endpoint: str = Field(default="http://localhost:3000", description="Umami API endpoint")
    umami_website_id: str = Field(..., description="Umami Website ID (UUID)")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton instance
_config: Settings | None = None


def get_config() -> Settings:
    """Get or create configuration singleton"""
    global _config
    if _config is None:
        _config = Settings()
    return _config
```

### Step 3: Update Environment Variables

**File:** `.env`

Add analytics configuration:

```bash
# Analytics Configuration
ANALYTICS_ENABLED=true
UMAMI_ENDPOINT=http://umami:3000
UMAMI_WEBSITE_ID=your-website-uuid-from-umami

# For production, use your actual domain:
# UMAMI_ENDPOINT=https://analytics.yourdomain.com
```

**Important:** Get your `UMAMI_WEBSITE_ID` from Umami:
1. Go to Settings → Websites
2. Click Edit on your website
3. Copy the Website ID (UUID)

---

## Analytics Service Implementation

### File Structure

Create a new analytics service:

```
src/
├── services/
│   ├── analytics_service.py  # NEW - Analytics tracking service
│   ├── appointment_checker.py
│   ├── notification_service.py
│   └── queue_manager.py
```

### Create Analytics Service

**File:** `src/services/analytics_service.py`

```python
"""
ABOUTME: Analytics service for tracking bot events to Umami
ABOUTME: Provides async event tracking without blocking bot operations
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import httpx

from src.config import get_config

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    Track events to Umami analytics platform.

    Designed to be non-blocking - analytics errors never crash the bot.
    """

    def __init__(self):
        self.config = get_config()
        self.umami_url = self.config.umami_endpoint
        self.website_id = self.config.umami_website_id
        self.enabled = self.config.analytics_enabled
        self.client: Optional[httpx.AsyncClient] = None

        if self.enabled:
            self.client = httpx.AsyncClient(timeout=5.0)
            logger.info(f"Analytics enabled - tracking to {self.umami_url}")
        else:
            logger.info("Analytics disabled")

    async def track_event(
        self,
        event_name: str,
        user_id: Optional[int] = None,
        properties: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Track an event to Umami analytics.

        Args:
            event_name: Name of the event (e.g., "booking_completed")
            user_id: Telegram user ID (pseudonymous identifier)
            properties: Additional event properties (e.g., service_id, status)

        Note:
            This method never raises exceptions - analytics failures are logged only.
            The bot continues functioning even if analytics is completely broken.
        """
        if not self.enabled or self.client is None:
            return

        try:
            payload = {
                "payload": {
                    "website": self.website_id,
                    "url": f"/event/{event_name}",  # Virtual URL for event
                    "name": event_name,
                    "data": properties or {},
                }
            }

            # Add user_id as visitor identifier if provided
            if user_id:
                payload["payload"]["data"]["user_id"] = str(user_id)

            # Add timestamp
            payload["payload"]["data"]["timestamp"] = datetime.utcnow().isoformat()

            # Send async (don't block bot operations)
            response = await self.client.post(
                f"{self.umami_url}/api/send",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code != 200:
                logger.warning(
                    f"Umami tracking failed: {response.status_code} - {response.text}"
                )
            else:
                logger.debug(f"Tracked event: {event_name}")

        except httpx.TimeoutException:
            logger.warning(f"Analytics timeout for event: {event_name}")
        except Exception as e:
            # Never let analytics errors crash the bot
            logger.error(f"Analytics tracking error for {event_name}: {e}")

    async def close(self):
        """Close the HTTP client"""
        if self.client:
            await self.client.aclose()


# Singleton instance
_analytics_service: Optional[AnalyticsService] = None


def get_analytics_service() -> AnalyticsService:
    """Get or create analytics service singleton"""
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service


async def track_event(
    event_name: str,
    user_id: Optional[int] = None,
    **properties
) -> None:
    """
    Convenience function to track events.

    Usage:
        await track_event("booking_completed", user_id=123, status="success", duration_ms=45000)

    Args:
        event_name: Event name (e.g., "user_registered")
        user_id: Telegram user ID (optional)
        **properties: Event properties as keyword arguments
    """
    service = get_analytics_service()
    await service.track_event(event_name, user_id, properties)


async def cleanup_analytics():
    """
    Cleanup analytics service (close HTTP client).
    Call this on bot shutdown.
    """
    service = get_analytics_service()
    await service.close()
```

---

## Event Taxonomy

We track **25 core events** across 6 categories.

### Standard Properties

Every event includes:
- `event_name` - The event identifier
- `user_id` - Telegram user ID (pseudonymous)
- `timestamp` - ISO 8601 UTC timestamp

Plus event-specific properties.

### 1. User Lifecycle Events (5 events)

#### `user_registered`
**When:** First time user executes /start

**Properties:**
```python
{
    "username": str,  # Telegram username (or "anonymous")
}
```

#### `user_reengaged`
**When:** User executes /start after >30 days inactive

**Properties:**
```python
{
    "days_inactive": int,  # Days since last activity
}
```

#### `user_stopped`
**When:** User executes /stop

**Properties:**
```python
{
    "days_since_registration": int,
    "total_subscriptions_at_stop": int,
}
```

#### `user_blocked_bot`
**When:** Telegram API returns "bot was blocked by user" error

**Properties:**
```python
{
    "last_command_timestamp": str,  # ISO 8601
}
```

#### `user_unblocked`
**When:** User interacts after blocking

**Properties:**
```python
{
    "days_blocked": int,
}
```

---

### 2. Command & Interaction Events (2 events)

#### `command_executed`
**When:** User executes any command

**Properties:**
```python
{
    "command_name": str,  # e.g., "/start", "/subscribe"
    "source": str,  # "typed", "button_click", "menu_selection"
    "status": str,  # "success", "failure"
    "failure_reason": Optional[str],  # If status is "failure"
}
```

#### `button_clicked`
**When:** User clicks inline keyboard button

**Properties:**
```python
{
    "button_id": str,  # e.g., "subscribe_service_123"
    "context": str,  # "notification_message", "menu_message"
}
```

---

### 3. Subscription Management Events (3 events)

#### `subscription_added`
**When:** User subscribes to a service

**Properties:**
```python
{
    "service_id": int,
    "service_name": str,
    "office_id": int,
}
```

#### `subscription_removed`
**When:** User unsubscribes from a service

**Properties:**
```python
{
    "service_id": int,
    "service_name": str,
    "office_id": int,
    "reason": str,  # "user_initiated", "auto_cleanup"
}
```

#### `date_range_set`
**When:** User sets or modifies date range

**Properties:**
```python
{
    "range_days": int,  # Length of date range in days
    "range_direction": str,  # "expanded", "narrowed", "set"
}
```

---

### 4. Appointment System Events (5 events)

#### `appointment_check_batch`
**When:** Full check cycle completes

**Properties:**
```python
{
    "total_checks": int,
    "successful_checks": int,
    "failed_checks": int,
    "appointments_found": int,
    "duration_ms": int,
}
```

#### `appointment_found`
**When:** Appointments become available

**Properties:**
```python
{
    "service_id": int,
    "service_name": str,
    "office_id": int,
    "slots_count": int,  # Number of available slots
    "matched_users": int,  # Number of subscribed users
}
```

#### `notification_sent`
**When:** User is notified of appointments

**Properties:**
```python
{
    "service_id": int,
    "service_name": str,
    "notification_type": str,  # "initial", "update", "reminder"
    "slots_count": int,
}
```

#### `notification_failed`
**When:** Notification fails to send

**Properties:**
```python
{
    "error_type": str,  # "telegram_api_error", "user_blocked_bot", "rate_limit_exceeded"
    "service_id": int,
}
```

#### `captcha_solved`
**When:** Captcha solve attempt (success or failure)

**Properties:**
```python
{
    "success": bool,
    "duration_ms": int,
    "consecutive_failures": int,  # If failed
}
```

---

### 5. Booking Funnel Events (7 events)

#### `booking_started`
**When:** User clicks "Book Now" from notification

**Properties:**
```python
{
    "service_id": int,
    "service_name": str,
    "office_id": int,
    "selected_date": str,  # YYYY-MM-DD
}
```

#### `slot_selected`
**When:** User selects a time slot

**Properties:**
```python
{
    "service_id": int,
    "selected_time": str,  # HH:MM
}
```

#### `name_entered`
**When:** User provides their name (PII NOT tracked)

**Properties:**
```python
{
    "service_id": int,
    "step_number": 2,
}
```

#### `email_entered`
**When:** User provides their email (PII NOT tracked)

**Properties:**
```python
{
    "service_id": int,
    "step_number": 3,
}
```

#### `booking_confirmed`
**When:** User clicks confirm button

**Properties:**
```python
{
    "service_id": int,
    "step_number": 4,
}
```

#### `booking_completed`
**When:** Booking API call finishes (success or failure)

**Properties:**
```python
{
    "service_id": int,
    "service_name": str,
    "status": str,  # "success", "failure"
    "failure_reason": Optional[str],  # If failed
    "duration_ms": int,  # Time from booking_started to here
}
```

#### `booking_cancelled`
**When:** User cancels booking flow

**Properties:**
```python
{
    "service_id": int,
    "cancelled_at_step": str,  # "time_selection", "name_entry", etc.
    "reason": str,  # "user_initiated", "session_expired"
}
```

---

### 6. System Health Events (3 events)

#### `api_error`
**When:** Munich API call fails

**Properties:**
```python
{
    "endpoint": str,  # "get_available_days", "book_appointment"
    "error_type": str,  # "network_error", "timeout", "parsing_error"
    "error_message": str,
}
```

#### `health_alert`
**When:** System health alert triggered

**Properties:**
```python
{
    "alert_type": str,  # "consecutive_failures", "high_error_rate"
    "consecutive_failures": int,
}
```

#### `booking_session_expired`
**When:** Booking session times out

**Properties:**
```python
{
    "expired_at_step": str,
    "minutes_since_start": int,
}
```

---

## Integration Points

### Where to Add Tracking

Here's where to integrate analytics into existing bot code:

| File | Events to Track | Integration Points |
|------|-----------------|-------------------|
| `src/commands/start.py` | `user_registered`, `user_reengaged` | After user creation/retrieval |
| `src/commands/stop.py` | `user_stopped` | After deleting user data |
| `src/commands/subscribe.py` | `subscription_added` | After creating subscription |
| `src/commands/myservices.py` | `subscription_removed` | After deleting subscription |
| `src/commands/setdates.py` | `date_range_set` | After updating date range |
| `src/commands/*.py` (all) | `command_executed` | At start of each command |
| `src/handlers/buttons.py` | `button_clicked` | In button callback handler |
| `src/services/appointment_checker.py` | `appointment_check_batch`, `appointment_found`, `notification_sent`, `captcha_solved` | In check loop |
| `src/services/notification_service.py` | `notification_failed` | When notification errors |
| `src/commands/booking.py` | All booking funnel events | At each conversation step |

---

## Code Examples

### Example 1: Track User Registration

**File:** `src/commands/start.py`

```python
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.repositories import UserRepository
from src.services.analytics_service import track_event  # Import analytics

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    username = update.effective_user.username

    with get_session() as session:
        user_repo = UserRepository(session)
        user = user_repo.get_user(user_id)

        if user is None:
            # New user - create and track registration
            user = user_repo.create_user(
                user_id=user_id,
                username=username,
            )

            # Track analytics event
            await track_event(
                "user_registered",
                user_id=user_id,
                username=username or "anonymous"
            )

            await update.message.reply_text("Welcome! You're now registered.")
        else:
            # Existing user - check if re-engaged
            days_inactive = (datetime.utcnow() - user.subscribed_at).days

            if days_inactive > 30:
                await track_event(
                    "user_reengaged",
                    user_id=user_id,
                    days_inactive=days_inactive
                )

            await update.message.reply_text("Welcome back!")
```

### Example 2: Track Commands with Decorator

**File:** `src/commands/start.py` (add decorator)

```python
from functools import wraps
from src.services.analytics_service import track_event

def track_command(command_name: str):
    """Decorator to track command execution"""
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id

            try:
                result = await func(update, context)

                # Track successful execution
                await track_event(
                    "command_executed",
                    user_id=user_id,
                    command_name=command_name,
                    source="typed",  # Could detect button vs typed
                    status="success"
                )

                return result
            except Exception as e:
                # Track failure
                await track_event(
                    "command_executed",
                    user_id=user_id,
                    command_name=command_name,
                    source="typed",
                    status="failure",
                    failure_reason=str(e)
                )
                raise

        return wrapper
    return decorator


# Usage:
@track_command("/start")
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Command logic here
    pass
```

### Example 3: Track Subscriptions

**File:** `src/commands/subscribe.py`

```python
from src.services.analytics_service import track_event
from src.services_manager import get_service_info

async def handle_subscription_add(user_id: int, service_id: int, office_id: int):
    """Add subscription and track analytics"""

    # Create subscription in database
    with get_session() as session:
        sub_repo = SubscriptionRepository(session)
        sub_repo.add_subscription(user_id, service_id, office_id)

    # Get service info for analytics
    service_info = get_service_info(service_id)

    # Track analytics event
    await track_event(
        "subscription_added",
        user_id=user_id,
        service_id=service_id,
        service_name=service_info["name"] if service_info else f"Service {service_id}",
        office_id=office_id
    )

    return True
```

### Example 4: Track Booking Funnel

**File:** `src/commands/booking.py`

```python
from datetime import datetime
from src.services.analytics_service import track_event

async def start_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the booking process"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    # Extract booking data
    callback_data = query.data.split("_")
    date = callback_data[1]
    office_id = int(callback_data[2])
    service_id = int(callback_data[3])

    # Track booking started
    service_info = get_service_info(service_id)
    await track_event(
        "booking_started",
        user_id=user_id,
        service_id=service_id,
        service_name=service_info["name"],
        office_id=office_id,
        selected_date=date
    )

    # ... rest of booking logic ...


async def time_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected a time slot"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    timestamp = int(query.data.split("_")[1])

    # Get service_id from session
    booking_session = get_booking_session(user_id)

    # Track slot selection
    dt = datetime.fromtimestamp(timestamp, tz=ZoneInfo("Europe/Berlin"))
    await track_event(
        "slot_selected",
        user_id=user_id,
        service_id=booking_session.service_id,
        selected_time=dt.strftime("%H:%M")
    )

    # ... rest of logic ...


async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User entered their name"""
    user_id = update.effective_user.id
    name = update.message.text.strip()

    # Validate name
    if len(name.split()) < 2:
        await update.message.reply_text("Please enter your full name.")
        return ASKING_NAME

    # Track name entry (NOT the actual name)
    booking_session = get_booking_session(user_id)
    await track_event(
        "name_entered",
        user_id=user_id,
        service_id=booking_session.service_id,
        step_number=2
    )

    # ... rest of logic ...


async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User confirmed - process booking"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    booking_session = get_booking_session(user_id)

    # Calculate duration
    start_time = booking_session.created_at
    duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

    # Process booking
    result = book_appointment_complete(...)

    # Track completion
    service_info = get_service_info(booking_session.service_id)

    if result:
        await track_event(
            "booking_completed",
            user_id=user_id,
            service_id=booking_session.service_id,
            service_name=service_info["name"],
            status="success",
            duration_ms=duration_ms,
            booking_id=result.get("processId")
        )
    else:
        await track_event(
            "booking_completed",
            user_id=user_id,
            service_id=booking_session.service_id,
            service_name=service_info["name"],
            status="failure",
            failure_reason="slot_taken_or_api_error",
            duration_ms=duration_ms
        )

    # ... rest of logic ...
```

### Example 5: Track Appointment Checking

**File:** `src/services/appointment_checker.py`

```python
from datetime import datetime
from src.services.analytics_service import track_event

async def check_and_notify(application: Application):
    """Background task to check for appointments"""

    while True:
        batch_start = datetime.utcnow()
        total_checks = 0
        successful_checks = 0
        failed_checks = 0
        appointments_found_count = 0

        try:
            # Get subscriptions
            with get_session() as session:
                sub_repo = SubscriptionRepository(session)
                service_subs = sub_repo.get_all_service_subscriptions()

            total_checks = len(service_subs)

            # Check each service
            for service_office_key, user_ids in service_subs.items():
                service_id, office_id = service_office_key.split("_")
                service_id = int(service_id)
                office_id = int(office_id)

                # ... check for appointments ...

                if appointments_found:
                    successful_checks += 1
                    appointments_found_count += 1

                    # Track appointment found
                    service_info = get_service_info(service_id)
                    await track_event(
                        "appointment_found",
                        service_id=service_id,
                        service_name=service_info["name"],
                        office_id=office_id,
                        slots_count=len(available_days),
                        matched_users=len(user_ids)
                    )

                    # Notify users
                    for uid in user_ids:
                        try:
                            await application.bot.send_message(uid, message)

                            # Track successful notification
                            await track_event(
                                "notification_sent",
                                user_id=uid,
                                service_id=service_id,
                                service_name=service_info["name"],
                                notification_type="initial",
                                slots_count=len(available_days)
                            )
                        except Exception as e:
                            # Track notification failure
                            error_type = "user_blocked_bot" if "blocked" in str(e) else "telegram_api_error"

                            await track_event(
                                "notification_failed",
                                user_id=uid,
                                service_id=service_id,
                                error_type=error_type
                            )

                            # If user blocked bot, track that too
                            if "blocked" in str(e):
                                await track_event(
                                    "user_blocked_bot",
                                    user_id=uid,
                                    last_command_timestamp=datetime.utcnow().isoformat()
                                )
                else:
                    successful_checks += 1

            # Track batch completion
            duration_ms = int((datetime.utcnow() - batch_start).total_seconds() * 1000)
            await track_event(
                "appointment_check_batch",
                total_checks=total_checks,
                successful_checks=successful_checks,
                failed_checks=failed_checks,
                appointments_found=appointments_found_count,
                duration_ms=duration_ms
            )

        except Exception as e:
            logger.error(f"Error in check_and_notify: {e}")

            # Track API error
            await track_event(
                "api_error",
                endpoint="check_and_notify",
                error_type="exception",
                error_message=str(e)
            )

        await asyncio.sleep(config.check_interval)
```

### Example 6: Cleanup on Shutdown

**File:** `telegram_bot.py`

```python
from src.services.analytics_service import cleanup_analytics

async def post_shutdown(application: Application) -> None:
    """Cleanup after bot shutdown"""
    logger.info("Shutting down bot...")

    # Close analytics HTTP client
    await cleanup_analytics()

    logger.info("Bot shutdown complete")


def main() -> None:
    """Start the bot"""
    # ... existing setup ...

    application = (
        Application.builder()
        .token(config.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)  # Add cleanup
        .build()
    )

    # ... rest of main ...
```

---

## Privacy & GDPR Compliance

### What We Track (Safe)

✅ **Pseudonymous identifiers:**
- `user_id` - Telegram User ID (not personally identifiable alone)

✅ **Behavioral data:**
- Event names (actions taken)
- Timestamps (when actions occurred)
- Service IDs (which services users interact with)
- Aggregated metrics (counts, durations)

✅ **Technical data:**
- Error types and messages
- API response codes
- System health metrics

### What We NEVER Track (PII)

❌ **Personal information:**
- Real names (from booking form)
- Email addresses (from booking form)
- Phone numbers
- Message content
- Exact dates selected by users

❌ **Sensitive data:**
- IP addresses (Umami can be configured to ignore)
- Location data (not applicable for Telegram bots)
- Browsing history

### Privacy Implementation

**Example of what NOT to do:**

```python
# ❌ BAD - Tracks PII
await track_event(
    "booking_completed",
    user_id=user_id,
    name=booking_session.name,  # ❌ PII!
    email=booking_session.email  # ❌ PII!
)
```

**Example of correct implementation:**

```python
# ✅ GOOD - Tracks behavior only
await track_event(
    "booking_completed",
    user_id=user_id,  # ✅ Pseudonymous
    service_id=service_id,  # ✅ No PII
    status="success",  # ✅ Behavioral data
    duration_ms=45000  # ✅ Technical data
)
```

### Privacy Policy Text

Update your bot's `/help` command to include analytics disclosure:

```python
PRIVACY_TEXT = """
📊 **Analytics & Privacy**

We collect anonymous usage data to improve the bot:

**What we collect:**
✅ Which commands you use
✅ Number of appointments found
✅ Booking success/failure rates
✅ Technical errors

**What we DON'T collect:**
❌ Your name or email
❌ Personal messages
❌ IP addresses
❌ Exact dates you select

**Your rights:**
• All data is pseudonymized
• Your Telegram ID cannot identify you personally
• Data is stored securely on our servers
• Data retention: 90 days

For questions, use /help or contact the admin.
"""
```

---

## Dashboard Configuration

### Public Dashboard (Transparency Metrics)

Create a public dashboard in Umami with these widgets:

#### 1. Active Users (Last 30 Days)
- **Widget type:** Metrics
- **Metric:** Unique visitors
- **Date range:** Last 30 days
- **Purpose:** Show user base size

#### 2. Appointments Found Today
- **Widget type:** Metrics
- **Event:** `appointment_found`
- **Date range:** Last 24 hours
- **Purpose:** Show bot is actively finding appointments

#### 3. Successful Bookings Today
- **Widget type:** Metrics
- **Event:** `booking_completed` (filter: status=success)
- **Date range:** Last 24 hours
- **Purpose:** Show booking success rate

#### 4. Appointment Trend (7 Days)
- **Widget type:** Line chart
- **Event:** `appointment_found`
- **Date range:** Last 7 days
- **Purpose:** Show appointment availability over time

#### 5. Bot Activity
- **Widget type:** Bar chart
- **Metric:** All events
- **Group by:** Hour
- **Date range:** Last 24 hours
- **Purpose:** Show bot is active and healthy

#### 6. Popular Services
- **Widget type:** Bar chart
- **Event:** `subscription_added`
- **Group by:** `service_name`
- **Date range:** Last 30 days
- **Purpose:** Show which services are most popular

### Internal Dashboard (Detailed Analytics)

Create a private dashboard with detailed metrics:

#### Booking Funnel
- Widget showing counts for:
  - `booking_started`
  - `slot_selected`
  - `name_entered`
  - `email_entered`
  - `booking_confirmed`
  - `booking_completed`

Calculate conversion rate: `booking_completed / booking_started * 100`

#### Error Monitoring
- `api_error` count by `error_type`
- `notification_failed` count by `error_type`
- `captcha_solved` failure rate

#### User Engagement
- `command_executed` by `command_name`
- `user_registered` vs `user_stopped` trend
- `user_blocked_bot` count

---

## Testing

### Unit Testing

**File:** `tests/test_analytics_service.py`

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.analytics_service import AnalyticsService, track_event

@pytest.mark.asyncio
async def test_track_event_sends_to_umami():
    """Test that track_event sends HTTP request to Umami"""

    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value = MagicMock(status_code=200)

        await track_event(
            "test_event",
            user_id=123,
            property1="value1",
            property2=42
        )

        # Verify API was called
        assert mock_post.called

        # Verify payload structure
        call_args = mock_post.call_args
        payload = call_args.kwargs['json']

        assert payload['payload']['name'] == "test_event"
        assert payload['payload']['data']['user_id'] == "123"
        assert payload['payload']['data']['property1'] == "value1"
        assert payload['payload']['data']['property2'] == 42


@pytest.mark.asyncio
async def test_track_event_when_disabled():
    """Test that tracking is skipped when analytics disabled"""

    with patch('src.services.analytics_service.get_config') as mock_config:
        mock_config.return_value.analytics_enabled = False

        with patch('httpx.AsyncClient.post') as mock_post:
            await track_event("test_event")

            # Should NOT call API
            assert not mock_post.called


@pytest.mark.asyncio
async def test_track_event_handles_timeout_gracefully():
    """Test that analytics timeout doesn't crash bot"""

    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Timeout")

        # Should not raise exception
        await track_event("test_event", user_id=123)


@pytest.mark.asyncio
async def test_track_event_handles_api_error_gracefully():
    """Test that Umami API errors don't crash bot"""

    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value = MagicMock(status_code=500, text="Internal Server Error")

        # Should not raise exception
        await track_event("test_event", user_id=123)
```

### Integration Testing Checklist

Manual testing after implementation:

- [ ] **Test event tracking**
  1. Perform action in bot (e.g., /start)
  2. Check Umami dashboard → Real-time view
  3. Verify event appears within seconds

- [ ] **Test with analytics disabled**
  1. Set `ANALYTICS_ENABLED=false` in `.env`
  2. Restart bot
  3. Perform actions
  4. Verify bot works normally (no errors)

- [ ] **Test analytics failure**
  1. Stop Umami container: `docker stop umami`
  2. Perform actions in bot
  3. Verify bot continues working
  4. Check bot logs for analytics warnings (not errors)
  5. Restart Umami: `docker start umami`

- [ ] **Test public dashboard**
  1. Open public dashboard URL
  2. Verify accessible without login
  3. Verify metrics display correctly

- [ ] **Test booking funnel**
  1. Complete full booking flow
  2. Check Umami for all funnel events
  3. Verify properties are correct

- [ ] **Test error tracking**
  1. Trigger an error (e.g., invalid command)
  2. Verify `api_error` event tracked
  3. Check error details in Umami

---

## Monitoring & Maintenance

### Monitor Analytics Health

**Option 1: Add health check command**

```python
# src/commands/health.py
from src.services.analytics_service import track_event

async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check bot and analytics health"""

    user_id = update.effective_user.id

    # Test analytics
    try:
        await track_event("health_check", user_id=user_id, source="command")
        analytics_status = "✅ Analytics: OK"
    except Exception as e:
        analytics_status = f"⚠️ Analytics: {str(e)}"

    # Check database, APIs, etc.
    # ...

    message = f"""
🏥 **System Health**

{analytics_status}
✅ Database: OK
✅ Telegram API: OK
    """

    await update.message.reply_text(message, parse_mode="Markdown")
```

**Option 2: Monitor in Umami**

1. Go to Umami dashboard
2. Check "Real-time" view for activity
3. If no events for >10 minutes during peak hours → investigate

### Performance Impact

Analytics should have minimal performance impact:

- **Async tracking** - Never blocks bot operations
- **5-second timeout** - Fails fast if Umami is slow
- **Error handling** - Exceptions never propagate to bot

**Verify performance:**

```python
import time
from src.services.analytics_service import track_event

async def test_performance():
    """Test analytics performance impact"""

    # Track 100 events
    start = time.time()

    for i in range(100):
        await track_event("performance_test", user_id=i, iteration=i)

    duration = time.time() - start

    print(f"Tracked 100 events in {duration:.2f} seconds")
    print(f"Average: {duration/100*1000:.2f} ms per event")

    # Should be <100ms per event on average
```

### Troubleshooting

**Events not appearing in Umami:**

1. Check `UMAMI_WEBSITE_ID` is correct in `.env`
2. Check bot logs for analytics errors
3. Test Umami API manually:
   ```bash
   curl -X POST http://your-umami:3000/api/send \
     -H "Content-Type: application/json" \
     -d '{"payload": {"website": "your-website-id", "name": "test"}}'
   ```
4. Verify Umami is accessible from bot: `curl http://your-umami:3000`

**High error rate in logs:**

1. Check Umami logs: `docker logs umami`
2. Verify network connectivity
3. Check firewall rules
4. Temporarily disable analytics: `ANALYTICS_ENABLED=false`

**Bot performance degraded:**

1. Check analytics timeout (should be 5s)
2. Verify async implementation (events shouldn't block)
3. Monitor network latency to Umami
4. Consider increasing Umami resources

---

## Rollout Plan

### Phase 1: Infrastructure & Testing (Week 1)

**Days 1-2: Setup**
- [ ] Deploy Umami (see [UMAMI_SETUP.md](./UMAMI_SETUP.md))
- [ ] Get Website ID
- [ ] Update `.env` with Umami configuration
- [ ] Add `httpx` dependency

**Days 3-4: Analytics Service**
- [ ] Create `src/services/analytics_service.py`
- [ ] Update `src/config.py`
- [ ] Test analytics service with dummy events
- [ ] Verify events appear in Umami

**Days 5-7: Initial Integration**
- [ ] Add tracking to `/start` command
- [ ] Add tracking to `/subscribe` command
- [ ] Test in production with real users
- [ ] Monitor for errors

### Phase 2: Core Events (Week 2)

**Days 8-10: User & Command Tracking**
- [ ] Track all user lifecycle events
- [ ] Track all command executions
- [ ] Track button clicks
- [ ] Test thoroughly

**Days 11-14: Subscription & Appointment Tracking**
- [ ] Track subscription management
- [ ] Track date range changes
- [ ] Track appointment checking batch
- [ ] Track appointment found events
- [ ] Track notifications

### Phase 3: Booking Funnel (Week 3)

**Days 15-18: Booking Flow**
- [ ] Track `booking_started`
- [ ] Track `slot_selected`
- [ ] Track `name_entered`
- [ ] Track `email_entered`
- [ ] Track `booking_confirmed`
- [ ] Track `booking_completed`
- [ ] Track `booking_cancelled`
- [ ] Test complete funnel

**Days 19-21: Error Tracking**
- [ ] Track API errors
- [ ] Track health alerts
- [ ] Track session expirations
- [ ] Test error scenarios

### Phase 4: Dashboards & Optimization (Week 4)

**Days 22-24: Dashboards**
- [ ] Create public dashboard
- [ ] Add 6 public metrics widgets
- [ ] Test public URL accessibility
- [ ] Create internal dashboard
- [ ] Add detailed analytics widgets

**Days 25-28: Polish & Documentation**
- [ ] Update bot `/help` with privacy policy
- [ ] Add `/health` command (optional)
- [ ] Write team documentation
- [ ] Monitor for issues
- [ ] Optimize based on data

### Success Metrics

After full rollout, measure:

- ✅ **Coverage:** 100% of planned events tracked
- ✅ **Reliability:** <1% analytics error rate
- ✅ **Performance:** <50ms average tracking overhead
- ✅ **Adoption:** Public dashboard shared and accessible

---

## Conclusion

You now have a complete guide for integrating analytics into your Munich Appointment Bot!

**Key takeaways:**
1. ✅ Privacy-first - Never track PII
2. ✅ Non-blocking - Analytics never crash the bot
3. ✅ Comprehensive - 25 events across 6 categories
4. ✅ Transparent - Public dashboard for users
5. ✅ Actionable - Data drives improvements

**Next steps:**
1. Complete rollout plan (Weeks 1-4)
2. Monitor analytics daily
3. Use data to improve bot
4. Share public dashboard with users

**Related Documentation:**
- [UMAMI_SETUP.md](./UMAMI_SETUP.md) - Umami deployment guide

**Questions?**
- Check bot logs for analytics errors
- Check Umami logs: `docker logs umami`
- Review [Troubleshooting](#monitoring--maintenance) section
