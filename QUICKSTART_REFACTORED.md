# Quick Start: Refactored Architecture

## ✅ What's Been Done

Phases 1-3 of the refactoring are **complete**:
- ✅ Type-safe models, enums, and dataclasses
- ✅ Pydantic configuration with validation
- ✅ SQLModel ORM with repository pattern
- ✅ Alembic database migrations
- ✅ Babel/gettext i18n framework

## 🚀 Getting Started

### 1. Install Dependencies

```bash
uv pip install --system -r pyproject.toml
```

This installs:
- `pydantic` & `pydantic-settings` - Configuration
- `sqlmodel` - ORM
- `alembic` - Migrations
- `babel` & `python-i18n` - Internationalization

### 2. Test the New Modules

```bash
# Test configuration
python3 -c "from config import get_config; c = get_config(); print(f'✅ Config loaded: {c.telegram_bot_token[:10]}...')"

# Test database models
python3 -c "from database import init_database; init_database(); print('✅ Database initialized')"

# Test i18n
python3 -c "from i18n import get_translator; get_translator(); print('✅ i18n initialized')"
```

### 3. Run the Bot (Old Code Still Works!)

The refactored modules **coexist** with the old code:

```bash
# Old bot still runs as before
python3 telegram_bot.py

# OR with uv
uv run telegram_bot.py
```

## 📝 Next Steps: Migration Options

### Option A: Start Using New Modules Immediately

Update one command handler to use the new architecture:

```python
# Example: Update /myservices command
from database import get_session
from repositories import UserRepository, SubscriptionRepository
from i18n import _, TranslationKey
from models import Language

async def myservices_command(update, context):
    user_id = update.effective_user.id

    # Use new repository pattern
    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        lang_code = user_repo.get_user_language(user_id)
        lang = Language(lang_code)
        subs = sub_repo.get_user_subscriptions(user_id)

    # Use new i18n system
    if not subs:
        msg = _(TranslationKey.NO_SUBSCRIPTIONS, lang)
        await update.message.reply_text(msg)
        return
    # ...
```

### Option B: Keep Old Code, Learn New Architecture

Study the new modules to understand the patterns:

1. **Type Safety** (`models.py`):
   ```python
   from models import Language, Intent, ServiceInfo

   # Type-safe enums
   lang = Language.EN  # IDE autocomplete!

   # Type-safe dataclasses
   service = ServiceInfo(id=123, name="Test", max_quantity=1)
   ```

2. **Configuration** (`config.py`):
   ```python
   from config import get_config

   config = get_config()  # Validates on load!
   print(config.telegram_bot_token)
   print(config.has_openai)  # Property method
   ```

3. **Database** (`repositories.py`):
   ```python
   from database import get_session
   from repositories import UserRepository

   with get_session() as session:
       repo = UserRepository(session)

       # Type-safe methods
       user = repo.get_user(12345)
       lang = repo.get_user_language(12345)
       repo.set_user_language(12345, "en")
   ```

4. **i18n** (`i18n.py`):
   ```python
   from i18n import _, TranslationKey
   from models import Language

   # Type-safe translation keys
   msg = _(TranslationKey.WELCOME, Language.EN)

   # With formatting
   msg = _(
       TranslationKey.TOTAL_SUBSCRIPTIONS,
       Language.DE,
       count=5
   )
   ```

## 🔍 Understanding the New Architecture

### File Structure

```
New Modules (Refactored):
├── models.py          # Dataclasses, Enums (Language, Intent)
├── config.py          # Pydantic Settings
├── db_models.py       # SQLModel ORM models
├── database.py        # Session management
├── repositories.py    # Repository pattern
├── i18n.py            # Babel/gettext translations
├── alembic/           # Database migrations
└── locales/           # .po translation files

Old Modules (Still Active):
├── telegram_bot.py    # Main bot
├── bot_commands.py    # Command handlers
├── ai_assistant.py    # OpenAI integration
├── termin_tracker.py  # Munich API client
├── services_manager.py # Service catalog
└── translations.py    # Old translation dict
```

### Key Concepts

1. **Repository Pattern**: Separates database access from business logic
   - Easy to test (mock repositories)
   - Type-safe operations
   - Automatic session management

2. **Type Safety**: Enums and dataclasses prevent typos
   - `Language.EN` instead of `"en"`
   - `TranslationKey.WELCOME` instead of `"welcome"`
   - IDE autocomplete everywhere

3. **Configuration**: Validated on startup
   - Fails fast with clear errors
   - Type-safe access
   - Environment variable support

4. **i18n**: Professional translation workflow
   - Standard .po files (works with Poedit, Weblate)
   - Pluralization support
   - Type-safe keys

## 🎯 Recommended Migration Path

### Week 1: Familiarization
- Read the new code
- Run tests
- Understand patterns

### Week 2: Configuration
- Replace all `os.getenv()` with `config.get_config()`
- Validate configuration on startup

### Week 3: Database
- Start using repositories in new code
- Keep old `_db_funcs` for existing code
- Write tests for repositories

### Week 4: i18n
- Create translation .po files
- Migrate one command at a time
- Test in all three languages

### Week 5: Cleanup
- Remove old `translations.py`
- Remove direct `_db_funcs` usage
- Full type checking with mypy

## 📚 Documentation

- `REFACTORING_SUMMARY.md` - High-level overview
- `REFACTORING_GUIDE.md` - Detailed migration guide
- Inline code comments - Docstrings everywhere

## 🆘 Troubleshooting

### "Module not found"
```bash
# Make sure dependencies are installed
uv pip install --system -r pyproject.toml
```

### "Config validation error"
```bash
# Check your .env file
cat .env

# Test config explicitly
python3 -c "from config import BotConfig; BotConfig()"
```

### "Database session error"
```python
# Always use context manager
with get_session() as session:
    repo = UserRepository(session)
    # Do work here
# Session auto-closes
```

## ✨ Benefits You're Getting

1. **Type Safety**: Catch errors before runtime
2. **Better IDE**: Full autocomplete
3. **Testability**: Easy to write unit tests
4. **Professional i18n**: Standard tools for translators
5. **Database Migrations**: No more manual SQL
6. **Clear Architecture**: Easy to onboard new developers

## 🎉 You're Ready!

The infrastructure is in place. You can now:
- ✅ Start using the new modules
- ✅ Keep old code working
- ✅ Migrate incrementally
- ✅ Write tests
- ✅ Add new features with better patterns

**The old bot still works exactly as before** - take your time migrating!
