# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Munich Appointment Bot - A Telegram bot that monitors the Munich city appointment system and notifies users when appointments become available. Features multi-service subscriptions and automated booking.

**Recent Refactoring (v2.1.0)**: Reorganized codebase into clean service/command architecture with separation of concerns.

## Running the Bot

```bash
# Initial setup
cp .env.example .env
# Edit .env with TELEGRAM_BOT_TOKEN

# Install dependencies (uses uv)
uv pip install --system -r pyproject.toml

# Initialize database
python3 -c "from src.database import init_database; init_database()"

# Run the bot
python3 telegram_bot.py
```

## Architecture Overview

### Project Structure

```
/
├── telegram_bot.py              # Minimal entry point - wires everything together
├── src/
│   ├── services/                # Business logic layer
│   │   ├── appointment_checker.py  # Background checking + stats
│   │   ├── notification_service.py # User notifications
│   │   └── queue_manager.py        # Booking mode queue
│   ├── commands/                # Command handlers (one per command)
│   │   ├── start.py            # /start command
│   │   ├── stop.py             # /stop command
│   │   ├── menu.py             # /menu command
│   │   ├── subscribe.py        # /subscribe command
│   │   ├── myservices.py       # /myservices command
│   │   ├── setdates.py         # /setdates command
│   │   ├── status.py           # /status command
│   │   ├── stats.py            # /stats command
│   │   └── booking.py          # Booking conversation handler
│   ├── handlers/                # Event handlers
│   │   └── buttons.py          # Inline button callbacks
│   ├── config.py               # Pydantic Settings
│   ├── database.py             # Session management
│   ├── db_models.py            # SQLModel ORM models
│   ├── models.py               # Type-safe dataclasses
│   ├── repositories.py         # Repository pattern for DB access
│   ├── booking_api.py          # Booking API integration
│   ├── termin_tracker.py       # Munich API client (CAPTCHA, availability)
│   └── services_manager.py     # Service catalog management
├── DOCS/                        # Documentation
├── .env                         # Configuration (not in git)
└── bot_data.db                 # SQLite database
```

### Three-Layer Architecture

1. **Services Layer** (`src/services/`)
   - `appointment_checker.py` - Background task for monitoring appointments, CAPTCHA management, stats tracking
   - `notification_service.py` - Sends notifications to users with progressive time slot updates
   - `queue_manager.py` - Manages booking queue to pause notifications during interactive booking

2. **Commands Layer** (`src/commands/`)
   - One file per command for easy navigation
   - Each command is self-contained with its logic
   - `booking.py` contains the multi-step booking conversation handler

3. **Handlers Layer** (`src/handlers/`)
   - `buttons.py` - Handles all inline keyboard button callbacks
   - Includes helper functions for showing menus, service lists, etc.

4. **Core Infrastructure** (`src/`)
   - Type-safe models and dataclasses
   - Pydantic configuration with validation
   - SQLModel ORM with repository pattern
   - Session management with context managers

5. **External Integration** (`src/`)
   - Munich appointment API client
   - CAPTCHA handling and availability checks
   - Service catalog management

### Key Patterns

**Repository Pattern** - All database access goes through repositories:
```python
from src.database import get_session
from src.repositories import UserRepository

with get_session() as session:
    user_repo = UserRepository(session)
    user = user_repo.get_user(user_id)
```

**Service Layer** - Business logic is in services:
```python
from src.services.queue_manager import add_user_to_queue, is_user_in_queue

# Add user to booking queue (pauses notifications)
add_user_to_queue(user_id)

# Check if user is in queue
if is_user_in_queue(user_id):
    # Skip notification
    pass
```

**Command Organization** - Each command in its own file:
```python
# src/commands/start.py
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    # Command logic here
```

**Type Safety** - Use dataclasses for structured data:
```python
@dataclass
class ServiceInfo:
    id: int
    name: str
    max_quantity: int = 1
```

**Configuration** - Centralized with Pydantic:
```python
from src.config import get_config

config = get_config()  # Singleton
config.telegram_bot_token  # Validated on startup
```

## Adding New Commands

1. Create new file in `src/commands/` (e.g., `mycommand.py`)
2. Implement command handler function (e.g., `mycommand_command(update, context)`)
3. Import and register in `telegram_bot.py`:
```python
from src.commands.mycommand import mycommand_command
# ...
application.add_handler(CommandHandler("mycommand", mycommand_command))
```

## Background Task Architecture

`check_and_notify()` in `src/services/appointment_checker.py`:
1. Fetches all unique service/office combinations from subscriptions
2. Groups users by service AND date range
3. Refreshes CAPTCHA token every ~4.5 minutes
4. Checks Munich API for each service/office/date-range combination
5. Delegates to `notification_service.py` to notify users
6. Respects queue manager - skips users in active booking mode
7. Implements health monitoring with consecutive failure tracking

## Queue Mode Pattern

To prevent notifications from interrupting interactive flows:
```python
from src.services.queue_manager import add_user_to_queue, remove_user_from_queue

# At start of interactive flow
add_user_to_queue(user_id)

# At end of interactive flow (or on cancellation)
remove_user_from_queue(user_id)
```

The queue manager automatically:
- Tracks users with timestamps
- Times out stale sessions after 10 minutes
- Provides `is_user_in_queue()` check for notification service

## Migration History

✅ **v2.1.0 - Architecture Refactoring**:
- Reorganized into `services/`, `commands/`, `handlers/` structure
- One file per command for maintainability
- Extracted business logic to service layer
- Separated button handlers into dedicated module

✅ **v2.0.0 - Core Modernization**:
- Type-safe models and dataclasses
- Pydantic configuration with validation
- SQLModel ORM with repository pattern
- English-only interface for simplicity

**Not migrated** (intentionally kept as-is):
- `src/termin_tracker.py` - Munich API client (external integration)
- `src/services_manager.py` - Service catalog (data layer)

## Documentation Guidelines

**IMPORTANT**: All new documentation files (except CLAUDE.md and README.md) MUST be placed in the `DOCS/` folder.

When creating documentation:
- Feature documentation → `DOCS/FEATURE_NAME.md`
- Implementation notes → `DOCS/IMPLEMENTATION_NAME.md`
- Architecture decisions → `DOCS/ARCHITECTURE_TOPIC.md`

The root directory should only contain:
- `CLAUDE.md` (this file) - Instructions for Claude Code
- `README.md` - User-facing project documentation

## Coding principles
You are a Python expert specializing in modern Python 3.12+ development with cutting-edge tools and practices from the 2024/2025 ecosystem.
- Use uv for package management
- Always run ruff format and ruff check --fix after changes
- We use pyproject.toml for project configuration. All the dependencies added there.
- Use type hints and dataclasses extensively for type safety
- Follow PEP 8 and idiomatic Python practices
- Write clean, maintainable, and well-documented code
- Always ensure that Dockerfile and docker-compose files are up to date with any dependency changes
- Prioritize code readability and simplicity
- Prioritize security best practices, especially when handling user data and external API interactions