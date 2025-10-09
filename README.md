# Munich Appointment Bot

Telegram bot that monitors Munich city appointment system and notifies users when appointments become available.

## Features

- **Multi-service subscriptions** - Track multiple appointment types simultaneously
- **Automated booking** - Book appointments directly through the bot
- **Date range filtering** - Only get notified for appointments in your preferred timeframe
- **Real-time notifications** - Get instant alerts when appointments become available

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
- `ADMIN_TELEGRAM_ID` - For health alerts

## Bot Commands

- `/start` - Register and get started
- `/menu` - Show main menu
- `/subscribe` - Browse and subscribe to services
- `/myservices` - Manage your subscriptions
- `/setdates <start> <end>` - Set date range (YYYY-MM-DD)
- `/status` - View your settings
- `/stats` - View bot statistics
- `/stop` - Unsubscribe from all

## Architecture

Built with modern Python patterns:
- **Type-safe** - Pydantic models and dataclasses throughout
- **ORM** - SQLModel with repository pattern
- **Validated config** - Fails fast on startup errors
- **Background monitoring** - Continuous appointment checking with health monitoring

See `CLAUDE.md` for detailed architecture documentation.
