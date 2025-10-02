# Refactoring Migration Guide

This document explains the new architecture and how to migrate from the old code to the refactored version.

## What Changed

### Phase 1: Type Safety & Configuration ✅

**New Files:**
- `models.py` - Type-safe data models using dataclasses and Enums
- `config.py` - Pydantic-based configuration with validation

**Benefits:**
- Type hints everywhere for better IDE support
- Configuration validated on startup
- Clear error messages for misconfiguration
- No more magic strings

**Migration Example:**

**Old:**
```python
import os
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# No validation, fails at runtime
```

**New:**
```python
from config import get_config

config = get_config()  # Validates on load
bot_token = config.telegram_bot_token  # Type-safe access
```

---

### Phase 2: Database Layer ✅

**New Files:**
- `db_models.py` - SQLModel database models
- `repositories.py` - Repository pattern for database access
- `database.py` - Session management and initialization
- `alembic/` - Database migration framework

**Benefits:**
- Type-safe database operations
- No more raw SQL strings
- Testable with dependency injection
- Proper migration management
- Relationship support

**Migration Example:**

**Old:**
```python
def get_user_language(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "de"
```

**New:**
```python
from database import get_session
from repositories import UserRepository

with get_session() as session:
    user_repo = UserRepository(session)
    language = user_repo.get_user_language(user_id)
```

---

### Phase 3: i18n with Babel ✅

**New Files:**
- `i18n.py` - Modern translation system
- `babel.cfg` - Babel configuration
- `locales/` - Translation catalogs (.po files)

**Benefits:**
- Industry-standard gettext/Babel
- Type-safe translation keys
- Proper pluralization support
- Easy for translators (standard .po format)
- Translation validation

**Migration Example:**

**Old:**
```python
MESSAGES = {
    'welcome': {
        'de': 'Willkommen!',
        'en': 'Welcome!',
        'ru': 'Добро пожаловать!'
    }
}

message = MESSAGES['welcome'].get(lang, MESSAGES['welcome']['de'])
```

**New:**
```python
from i18n import _, TranslationKey
from models import Language

message = _(TranslationKey.WELCOME, Language.EN)
```

---

## Migration Steps

### Step 1: Install New Dependencies

```bash
uv pip install --system -r pyproject.toml
```

### Step 2: Initialize Database

The new system can coexist with the old database schema. To migrate:

```bash
# Initialize Alembic
uv run alembic revision --autogenerate -m "Initial migration"

# Apply migrations
uv run alembic upgrade head
```

### Step 3: Create Translation Files

```bash
# Extract translatable strings
pybabel extract -F babel.cfg -o locales/messages.pot .

# Initialize languages
pybabel init -i locales/messages.pot -d locales -l de
pybabel init -i locales/messages.pot -d locales -l en
pybabel init -i locales/messages.pot -d locales -l ru

# Compile translations
pybabel compile -d locales
```

### Step 4: Gradual Migration Strategy

You can migrate incrementally:

1. **Start using `config.py`** - Replace `os.getenv()` calls
2. **Migrate one command at a time** - Update handlers to use repositories
3. **Replace translations** - Use `i18n.py` instead of `translations.py`

**Example: Migrate `/start` command:**

```python
# Old
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = _db_funcs['get_user_language'](user_id)
    message = get_message('welcome', lang)
    await update.message.reply_text(message)

# New
from database import get_session
from repositories import UserRepository
from i18n import _, TranslationKey
from models import Language

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    with get_session() as session:
        user_repo = UserRepository(session)
        lang_code = user_repo.get_user_language(user_id)
        lang = Language(lang_code)

    message = _(TranslationKey.WELCOME, lang)
    await update.message.reply_text(message)
```

---

## New Project Structure

```
notfall_termin_abh_muenchen_bot/
├── models.py              # Type-safe data models & enums
├── config.py              # Pydantic configuration
├── db_models.py           # SQLModel database models
├── database.py            # Database session management
├── repositories.py        # Repository pattern for DB access
├── i18n.py                # Translation system
├── alembic/               # Database migrations
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
├── locales/               # Translation files
│   ├── de/
│   │   └── LC_MESSAGES/
│   │       ├── messages.po
│   │       └── messages.mo
│   ├── en/
│   └── ru/
├── babel.cfg              # Babel i18n config
├── alembic.ini            # Alembic config
│
# Old files (to be gradually migrated)
├── telegram_bot.py
├── bot_commands.py
├── ai_assistant.py
├── termin_tracker.py
├── services_manager.py
└── translations.py  # Will be replaced by i18n.py
```

---

## Testing the New Architecture

### Test Configuration

```python
from config import BotConfig

# This will validate and fail fast if config is wrong
try:
    config = BotConfig()
    print(f"✅ Config valid: {config.telegram_bot_token[:10]}...")
except Exception as e:
    print(f"❌ Config invalid: {e}")
```

### Test Database

```python
from database import init_database, get_session
from repositories import UserRepository
from models import Language

# Initialize
init_database()

# Test repository
with get_session() as session:
    user_repo = UserRepository(session)
    user_repo.create_user(12345, "test_user", Language.EN.value)
    lang = user_repo.get_user_language(12345)
    assert lang == "en"
    print("✅ Database working")
```

### Test Translations

```python
from i18n import _, TranslationKey
from models import Language

# Test translation
welcome_de = _(TranslationKey.WELCOME, Language.DE)
welcome_en = _(TranslationKey.WELCOME, Language.EN)

assert "Willkommen" in welcome_de
assert "Welcome" in welcome_en
print("✅ Translations working")
```

---

## Benefits Summary

### Before Refactoring
- ❌ No type safety
- ❌ Configuration errors found at runtime
- ❌ Raw SQL everywhere
- ❌ Hard to test
- ❌ Translation strings in code
- ❌ No migration system

### After Refactoring
- ✅ Full type safety with mypy support
- ✅ Configuration validated on startup
- ✅ Clean repository pattern
- ✅ Easy to test with dependency injection
- ✅ Professional i18n with Babel
- ✅ Database migrations with Alembic
- ✅ Better IDE autocomplete
- ✅ Easier to onboard new developers

---

## Next Steps

1. **Validate Setup**: Run tests to ensure everything works
2. **Migrate Gradually**: Start with one module at a time
3. **Update Documentation**: Keep this guide updated as you migrate
4. **Add Tests**: Write unit tests for repositories and translations

---

## Getting Help

If you encounter issues:

1. Check type errors: `mypy *.py`
2. Validate config: `python -c "from config import get_config; get_config()"`
3. Check database: `sqlite3 bot_data.db ".schema"`
4. Test translations: `python -c "from i18n import get_translator; get_translator()"`

---

## Rollback Plan

If you need to rollback:

1. Keep old files unchanged during migration
2. Use git branches for incremental changes
3. Old and new systems can coexist
4. Database is backward compatible
