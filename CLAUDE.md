# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Munich Appointment Bot - A Telegram bot that monitors the Munich city appointment system and notifies users when appointments become available. Users create **watches** (one service; one office or any office; a time such as "as soon as possible" or "before 15.11"), get one live alert message per watch, and can book in the chat.

The watches design (data model, alert lifecycle, callback data, screens) is in `DOCS/WATCHES_DESIGN.md`.

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
├── telegram_bot.py              # Entry point: builds the Application, registers handlers, post_init
├── src/
│   ├── commands/                # Command and callback handlers (one file per command or screen)
│   │   ├── start.py            # /start, onboarding after the first language choice
│   │   ├── find.py             # /find (+ /menu, /subscribe): popular, browse, office and time steps (f1:)
│   │   ├── watches.py          # /watches (+ /myservices, /status, /setdates): My watches (w1:)
│   │   ├── settings.py         # /settings: language, saved booking details, delete data (s1:)
│   │   ├── help.py             # /help
│   │   ├── language.py         # /language, language picker callbacks, language gate
│   │   ├── stop.py             # /stop confirmation, delete_user_data
│   │   ├── stats.py            # /stats (admin)
│   │   └── booking.py          # Booking ConversationHandler (b1:) and orphan booking buttons
│   ├── handlers/                # Cross-cutting update handlers
│   │   ├── presence.py         # Group -3: resumes blocked pauses, delivers the reply keyboard once
│   │   ├── interaction_tracker.py # Group -2: marks taps on live alerts and queued messages
│   │   ├── menu_keyboard.py    # Reply keyboard taps (Find, My watches, Settings, Help)
│   │   ├── text_input.py       # Plain text: typed date answer or service search
│   │   ├── fallback_callbacks.py # Callbacks without a scheme prefix to their screens; catch-all
│   │   ├── language_picker.py  # Bilingual language picker
│   │   └── errors.py           # Application error handler
│   ├── services/                # Business logic with side effects
│   │   ├── appointment_checker.py # Background checker loop, run_check_cycle, stats
│   │   ├── alert_lifecycle.py  # apply_alert, end_watch_by_checker, expired booking cleanup
│   │   ├── immediate_check.py  # Check right after a watch is created or changed
│   │   ├── service_search.py   # Typed service search with synonyms
│   │   ├── announcement.py     # One-time announcement of the reply-keyboard menu at startup
│   │   ├── captcha_token.py    # Shared captcha token cache
│   │   ├── queue_manager.py    # is_user_in_queue: the user has an active booking session
│   │   ├── locks.py            # Named asyncio locks per event loop
│   │   └── analytics_service.py # Umami analytics
│   ├── watches/                 # Watch logic (mostly pure)
│   │   ├── when.py             # Time presets, date parsing, search windows
│   │   ├── slots.py            # Slot identity, snapshots, calendar filtering
│   │   ├── alert_decision.py   # Pure push/edit/defer decision for a live alert
│   │   ├── alert_view.py       # Alert rendering (text, buttons, hash)
│   │   ├── alert_ops.py        # Per-watch lock, close_live_alert, pending retires
│   │   ├── availability.py     # City calendar queries for watches (token + retry)
│   │   └── labels.py           # Service, office, time and date labels
│   ├── ui/                      # Telegram helpers
│   │   ├── telegram_safe.py    # send/edit/delete/answer that never raise Telegram errors
│   │   ├── screens.py          # show_screen: one nav message per user, edited in place
│   │   ├── callbacks.py        # Callback data builders, parser, handler patterns
│   │   ├── keyboard.py         # Persistent reply keyboard
│   │   ├── commands_menu.py    # Telegram command lists per language
│   │   └── background.py       # run_for_user: slow work outside the update queue
│   ├── i18n/                    # Bot text in English and Russian, t() and user language (see DOCS/I18N.md)
│   ├── config.py               # Pydantic Settings
│   ├── database.py             # Engine, sessions, migrations (PRAGMA user_version)
│   ├── db_models.py            # SQLModel ORM models
│   ├── repositories.py         # Repository pattern for DB access (WatchRepository, ...)
│   ├── booking_api.py          # Booking API integration
│   ├── munich_api_client.py    # HTTP client for the city API (status and error codes)
│   ├── termin_tracker.py       # Munich API client (CAPTCHA, availability)
│   └── services_manager.py     # Service catalog management
├── tests/                       # pytest; tests/fakes.py has FakeBot, fake updates and contexts
├── DOCS/                        # Documentation
├── .env                         # Configuration (not committed)
└── bot_data.db                 # SQLite database
```

### Layers

1. **Commands and handlers** (`src/commands/`, `src/handlers/`) - one file per command or screen. Handlers
   answer the callback first and move slow work (captcha + HTTP) into `run_for_user` background tasks.
2. **Services** (`src/services/`) - checker loop, alert lifecycle, immediate checks, search, announcement.
3. **Watch logic** (`src/watches/`) - time specs, snapshots, alert decisions and rendering, mostly pure.
4. **UI helpers** (`src/ui/`) - safe Telegram calls, nav screens, callback data, keyboards.
5. **Core infrastructure** (`src/`) - Pydantic configuration, SQLModel ORM with repositories, sessions.
6. **External integration** (`src/`) - Munich appointment API client, CAPTCHA, service catalog.

### Key Patterns

**Repository Pattern** - All database access goes through repositories:
```python
from src.database import get_session
from src.repositories import WatchRepository

with get_session() as session:
    watches = WatchRepository(session)
    rec = watches.get_for_user(watch_id, user_id)  # immutable WatchRecord
```

**Live alert writes hold the watch lock** - every change of a watch's live alert happens under
`alert_lock(watch_id)`, after re-reading the watch:
```python
from src.watches.alert_ops import alert_lock, close_live_alert

async with alert_lock(watch_id):
    ...  # re-read, change status, close_live_alert(...)
```

**Safe Telegram calls** - `src/ui/telegram_safe.py` returns an `EditOutcome` instead of raising. Navigation
screens go through `show_screen`, so only one nav message per user keeps its buttons.

**Configuration** - Centralized with Pydantic:
```python
from src.config import get_config

config = get_config()  # Singleton
config.telegram_bot_token  # Validated on startup
```

**Text** - all user-facing text goes through `t(key, lang)`; see `DOCS/I18N.md`.

## Adding New Commands

1. Create new file in `src/commands/` (e.g., `mycommand.py`)
2. Implement command handler function (e.g., `mycommand_command(update, context)`)
3. Add it to `COMMANDS` in `telegram_bot.py` (registered in group 1, private chats only):
```python
from src.commands.mycommand import mycommand_command
# ...
COMMANDS = (
    # ...
    ("mycommand", mycommand_command),
)
```
4. To list it in Telegram's command menu, add it to `BOT_COMMANDS` in `src/ui/commands_menu.py` and a
   `commands.<name>` text to both catalogs.

## Background Task Architecture

`check_and_notify()` in `src/services/appointment_checker.py` loops over `run_check_cycle(bot, today, now)`:
1. Finalizes queued messages (`process_pending_retires`), refreshes the catalog every 6 h, deletes expired
   booking sessions
2. Ends watches past their deadline or whose office is no longer public (silent "ended" message)
3. Groups active watches by service: one calendar query per service per cycle (captcha token fetched right
   before each call, retried once on a token error, per-office fallback on a combination error)
4. Builds and records a snapshot per watch
5. `apply_alert` decides per watch: push a new alert, edit the live one in place, or defer while the user is
   booking or tapped the alert in the last 10 minutes
6. Removes the buttons of replaced alerts after all pushes of the cycle
7. Health monitoring with consecutive failure tracking

## Booking Sessions

A user with an unexpired booking session gets no alert changes (`is_user_in_queue` in
`src/services/queue_manager.py`, read-only). Sessions live in the DB (`booking_sessions`): the checker deletes
expired ones every cycle, and `post_init` deletes all of them on startup.

## Migration History

✅ **Watches**:
- Watches replace subscriptions and the global date range (DB migration 2 converts them)
- Find flow with search, persistent reply keyboard, My watches, Settings
- One live alert per watch, edited in place; booking from the alert

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

## Foundational rules
- Doing it right is better than doing it fast. You are not in a rush. NEVER skip steps or take shortcuts.
- Tedious, systematic work is often the correct solution. Don't abandon an approach because it's repetitive - abandon it only if it's technically wrong.

## Our relationship
- Don't glaze me. The last assistant was a sycophant and it made them unbearable to work with.
- YOU MUST speak up immediately when you don't know something or we're in over our heads
- YOU MUST call out bad ideas, unreasonable expectations, and mistakes - I depend on this
- NEVER be agreeable just to be nice - I NEED your HONEST technical judgment
- NEVER write the phrase "You're absolutely right!"  You are not a sycophant. We're working together because I value your opinion.
- YOU MUST ALWAYS STOP and ask for clarification rather than making assumptions.
- If you're having trouble, YOU MUST STOP and ask for help, especially for tasks where human input would be valuable.
- When you disagree with my approach, YOU MUST push back. Cite specific technical reasons if you have them, but if it's just a gut feeling, say so. 
- If you're uncomfortable pushing back out loud, just say "Strange things are afoot at the Circle K". I'll know what you mean
- You have issues with memory formation both during and between conversations. Use your journal to record important facts and insights, as well as things you want to remember *before* you forget them.
- You search your journal when you trying to remember or figure stuff out.
- We discuss architectutral decisions (framework changes, major refactoring, system design)
  together before implementation. Routine fixes and clear implementations don't need
  discussion.


## Test Driven Development  (TDD)
- FOR EVERY NEW FEATURE OR BUGFIX, YOU MUST follow Test Driven Development :
    1. Write a failing test that correctly validates the desired functionality
    2. Run the test to confirm it fails as expected
    3. Write ONLY enough code to make the failing test pass
    4. Run the test to confirm success
    5. Refactor if needed while keeping tests green

## Code Comments
 - NEVER add comments explaining that something is "improved", "better", "new", "enhanced", or referencing what it used to be
 - NEVER add instructional comments telling developers what to do ("copy this pattern", "use this instead")
 - Comments should explain WHAT the code does or WHY it exists, not how it's better than something else
 - If you're refactoring, remove old comments - don't add new ones explaining the refactoring
 - YOU MUST NEVER remove code comments unless you can PROVE they are actively false. Comments are important documentation and must be preserved.
 - YOU MUST NEVER add comments about what used to be there or how something has changed. 
 - YOU MUST NEVER refer to temporal context in comments (like "recently refactored" "moved") or code. Comments should be evergreen and describe the code as it is. If you name something "new" or "enhanced" or "improved", you've probably made a mistake and MUST STOP and ask me what to do.
 - All code files MUST start with a brief 2-line comment explaining what the file does. Each line MUST start with "ABOUTME: " to make them easily greppable.

  Examples:
  // BAD: This uses Zod for validation instead of manual checking
  // BAD: Refactored from the old validation system
  // BAD: Wrapper around MCP tool protocol
  // GOOD: Executes tools with validated arguments

  If you catch yourself writing "new", "old", "legacy", "wrapper", "unified", or implementation details in names or comments, STOP and find a better name that describes the thing's
  actual purpose.
  
## Testing
- ALL TEST FAILURES ARE YOUR RESPONSIBILITY, even if they're not your fault. The Broken Windows theory is real.
- Never delete a test because it's failing. Instead, raise the issue
- Tests MUST comprehensively cover ALL functionality. 
- YOU MUST NEVER write tests that "test" mocked behavior. If you notice tests that test mocked behavior instead of real logic, you MUST stop and warn about them.
- YOU MUST NEVER implement mocks in end to end tests. We always use real data and real APIs.
- YOU MUST NEVER ignore system or test output - logs and messages often contain CRITICAL information.
- Test output MUST BE PRISTINE TO PASS. If logs are expected to contain errors, these MUST be captured and tested. If a test is intentionally triggering an error, we *must* capture and validate that the error output is as we expect