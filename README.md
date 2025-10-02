# Munich Appointment Bot

Telegram bot that monitors Munich city appointment system and notifies users when appointments become available.

## Features

- **Multi-service subscriptions** - Track multiple appointment types simultaneously
- **AI-powered search** - Natural language service matching with `/ask` command
- **Multi-language** - Support for German, English, and Russian
- **Date range filtering** - Only get notified for appointments in your preferred timeframe

## Quick Start

```bash
# Setup
cp .env.example .env
# Edit .env with your TELEGRAM_BOT_TOKEN

# Install dependencies
uv pip install --system -r pyproject.toml

# Initialize database
python3 -c "from database import init_database; init_database()"

# Run
python3 telegram_bot.py
```

## Configuration

Required:
- `TELEGRAM_BOT_TOKEN` - Get from @BotFather

Optional:
- `OPENAI_API_KEY` - For AI-powered `/ask` command
- `ADMIN_TELEGRAM_ID` - For health alerts

## Bot Commands

- `/start` - Register and select language
- `/subscribe` - Browse and subscribe to services
- `/ask <query>` - AI-powered natural language search
- `/myservices` - Manage your subscriptions
- `/setdates <start> <end>` - Set date range (YYYY-MM-DD)
- `/language` - Change language
- `/status` - View your settings
- `/stop` - Unsubscribe from all

## Architecture

Built with modern Python patterns:
- **Type-safe** - Pydantic models and enums throughout
- **ORM** - SQLModel with repository pattern
- **i18n** - Babel/gettext for translations
- **Validated config** - Fails fast on startup errors

See `CLAUDE.md` for detailed architecture documentation.
