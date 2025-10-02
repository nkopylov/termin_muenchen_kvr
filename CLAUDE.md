# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Munich Appointment Bot - A Telegram bot that monitors the Munich city appointment system and notifies users when appointments become available. Features AI-powered service matching, multi-language support (DE/EN/RU), and multi-service subscriptions.

**Recent Migration**: The codebase was recently refactored (v2.0.0) from raw SQL and string-based translations to a modern architecture with type safety, ORM, and professional i18n.

## Running the Bot

```bash
# Initial setup
cp .env.example .env
# Edit .env with TELEGRAM_BOT_TOKEN, optionally OPENAI_API_KEY

# Install dependencies (uses uv)
uv pip install --system -r pyproject.toml

# Initialize database
python3 -c "from database import init_database; init_database()"

# Run the bot
python3 telegram_bot.py
```

## Architecture Overview

### Three-Layer Architecture

1. **Core Infrastructure** (refactored v2.0)
   - `models.py` - Type-safe enums (`Language`, `Intent`) and dataclasses (`AIResponse`, `ServiceInfo`)
   - `config.py` - Pydantic Settings with validation (fails fast on startup)
   - `db_models.py` - SQLModel ORM models (User, ServiceSubscription, AppointmentLog)
   - `database.py` - Session management with context managers
   - `repositories.py` - Repository pattern for database access

2. **Application Layer**
   - `telegram_bot.py` - Main bot application, background checking loop
   - `bot_commands.py` - Command handlers (`/start`, `/subscribe`, `/ask`, etc.)
   - `ai_assistant.py` - OpenAI integration for natural language service matching

3. **External Integration**
   - `termin_tracker.py` - Munich appointment API client (CAPTCHA handling, availability checks)
   - `services_manager.py` - Service catalog management and categorization

### Key Patterns

**Repository Pattern** - All database access goes through repositories:
```python
with get_session() as session:
    user_repo = UserRepository(session)
    user = user_repo.get_user(user_id)
```

**Type Safety** - Use enums instead of strings:
```python
lang = Language.DE  # not "de"
result = parse_user_request(query, user_language=lang)  # returns AIResponse dataclass
```

**i18n** - Babel/gettext with type-safe keys:
```python
from i18n import _, TranslationKey
message = _(TranslationKey.WELCOME, Language.DE)
```

**Configuration** - Centralized with Pydantic:
```python
config = get_config()  # Singleton
config.telegram_bot_token  # Validated on startup
```

## Database Migrations

```bash
# Create migration after changing db_models.py
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head
```

## Translation Management

### Adding New Translation Keys

1. Add to `i18n.py`:
   ```python
   class TranslationKey(str, Enum):
       NEW_KEY = "new_key"
   ```

2. Add to all `.po` files in `locales/{de,en,ru}/LC_MESSAGES/messages.po`:
   ```
   msgid "new_key"
   msgstr "Translated text"
   ```

3. Recompile:
   ```bash
   msgfmt locales/de/LC_MESSAGES/messages.po -o locales/de/LC_MESSAGES/messages.mo
   msgfmt locales/en/LC_MESSAGES/messages.po -o locales/en/LC_MESSAGES/messages.mo
   msgfmt locales/ru/LC_MESSAGES/messages.po -o locales/ru/LC_MESSAGES/messages.mo
   ```

## OpenAI Integration Quirks

**Model Compatibility**: The codebase supports both standard OpenAI models (gpt-4o, gpt-4o-mini) and newer gpt-5-* models, which have different parameter requirements:

- **gpt-5-* models**:
  - Do NOT support `response_format: json_object`
  - Do NOT support custom `temperature` (only default of 1.0)
  - Require `max_completion_tokens` instead of `max_tokens`

The code handles this automatically:
```python
# response_format only added for non-gpt-5 models
if not config.openai_model.startswith('gpt-5'):
    payload['response_format'] = {'type': 'json_object'}
```

## Background Task Architecture

`check_and_notify()` in `telegram_bot.py` runs continuously:
1. Fetches all unique service/office combinations from subscriptions
2. Groups users by service AND date range
3. Refreshes CAPTCHA token every ~4.5 minutes
4. Checks Munich API for each service/office/date-range combination
5. Notifies all subscribed users when appointments found
6. Implements health monitoring with consecutive failure tracking

## Important File Locations

- **Backups**: `telegram_bot.py.old`, `bot_commands.py.old` contain pre-migration code
- **Legacy**: `translations.py` is kept as fallback but no longer used
- **Compiled translations**: `locales/*/LC_MESSAGES/messages.mo` (do not edit directly)
- **Translation sources**: `locales/*/LC_MESSAGES/messages.po` (edit these)

## Migration Status

✅ **Completed** (v2.0.0):
- Type-safe models and enums
- Pydantic configuration with validation
- SQLModel ORM with repository pattern
- Babel/gettext i18n (DE/EN/RU)
- All core files migrated: `telegram_bot.py`, `bot_commands.py`, `ai_assistant.py`

**Not migrated** (intentionally kept as-is):
- `termin_tracker.py` - Munich API client (external integration)
- `services_manager.py` - Service catalog (data layer)

## Debugging AI Features

When debugging OpenAI integration issues, check logs for:
- `Request payload` - Shows exact JSON sent to API
- `Response body` - Shows error details from OpenAI
- `Finish reason` - Why the model stopped ("stop", "length", "content_filter")
- `AI raw response` - Actual content returned before parsing

Empty responses often indicate `finish_reason: length` (increase `max_completion_tokens`).
