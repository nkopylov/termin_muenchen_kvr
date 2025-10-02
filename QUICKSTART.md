# München Termin Bot - Quick Start Guide

## Multi-Service Subscription Bot

This bot allows users to subscribe to 153 different Munich appointment services through an intuitive button-based interface.

## Setup

### 1. Environment Variables

Create a `.env` file:

```bash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
ADMIN_TELEGRAM_ID=your_telegram_user_id  # Optional: for health alerts
DB_FILE=/app/data/bot_data.db  # For Docker, or bot_data.db for local
```

### 2. Local Development

```bash
# Install dependencies with uv
uv sync

# Run the bot
python telegram_bot.py
```

### 3. Docker Deployment

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## User Interface Flow

### 1. Start Bot
User runs `/start` → receives welcome message with available commands

### 2. Subscribe to Services
```
/subscribe → Category Selection (button grid)
            ↓
         Category Selected → Service List (paginated)
            ↓
         Service Selected → Service Details + Subscribe Button
            ↓
         Subscribe → Confirmation
```

**Example:**
1. `/subscribe`
2. Tap "Ausländerbehörde 🌍 (10)"
3. See list of 10 immigration services
4. Tap "Notfall-Hilfe Aufenthaltstitel – Beschäftigte, Angehörige"
5. Tap "✅ Abonnieren"
6. Done! Bot will notify when appointments are available

### 3. Manage Subscriptions

```bash
/myservices    # View all active subscriptions (with unsubscribe buttons)
/setdates      # Change date range: /setdates 2025-10-02 2026-04-02
/stats         # Bot statistics
/stop          # Cancel all subscriptions
```

## Service Categories

- **Ausländerbehörde 🌍** (10 services) - Residence permits, emergency appointments
- **Ausweis & Pass 🆔** (9 services) - ID cards, passports
- **Fahrzeug 🚗** (33 services) - Vehicle registration
- **Führerschein 🪪** (11 services) - Driver's licenses
- **Wohnsitz 🏠** (4 services) - Address registration
- **Gewerbe 💼** (17 services) - Business registration
- **Familie 👨‍👩‍👧** (6 services) - Family services
- **Rente & Soziales 🏥** (16 services) - Pension, social services
- **Parken 🅿️** (12 services) - Parking permits
- **Sonstiges 📋** (35 services) - Other services

## Features

✅ **Multi-Service Support** - Subscribe to multiple services simultaneously
✅ **Smart Notifications** - Only notified about services you subscribed to
✅ **Custom Date Ranges** - Set preferred appointment dates for each user
✅ **Button Interface** - Easy navigation with inline keyboards
✅ **Automatic Captcha** - Solves proof-of-work captchas automatically
✅ **Persistent Storage** - SQLite database with Docker volume support
✅ **Health Monitoring** - Admin alerts for consecutive failures

## Database Schema

### Users Table
- Stores user info and default date range

### Service Subscriptions Table
- Maps users to their subscribed services
- `UNIQUE(user_id, service_id, office_id)` prevents duplicates

### Appointment Logs Table
- Records when appointments were found
- Includes service_id and office_id for analytics

## Architecture

```
telegram_bot.py          # Main bot logic, check_and_notify loop
bot_commands.py          # Command handlers with button interface
services_manager.py      # Service catalog and categorization
termin_tracker.py        # Munich API interaction, captcha solving
```

## How It Works

1. **Background Loop** (`check_and_notify`):
   - Every 2 minutes, refreshes captcha token
   - Gets all service subscriptions grouped by service/office
   - For each service: checks all user date ranges
   - Sends targeted notifications to subscribed users

2. **Captcha Handling**:
   - Automatically solves SHA-256 proof-of-work challenges
   - Token valid for ~5 minutes, refreshed as needed

3. **User Experience**:
   - Browse 153 services organized in 10 categories
   - Max 10 services shown per page (pagination)
   - Service names truncated if > 50 chars for readability
   - Direct booking links included in notifications

## API Endpoints

- Services: `https://www48.muenchen.de/buergeransicht/api/citizen/services`
- Offices: `https://www48.muenchen.de/buergeransicht/api/citizen/offices`
- Available Days: `https://www48.muenchen.de/buergeransicht/api/citizen/available-days-by-office/`

## Customization

### Change Check Interval
Edit `telegram_bot.py`:
```python
CHECK_INTERVAL = 120  # seconds (default: 2 minutes)
```

### Add More Categories
Edit `services_manager.py` `CATEGORY_KEYWORDS` dict

### Modify Button Layout
Edit `bot_commands.py` keyboard creation functions

## Troubleshooting

### Bot not responding to buttons
- Check CallbackQueryHandler is registered
- Verify bot_commands.py is imported correctly

### No notifications
- Check if users have active subscriptions: `/myservices`
- Review logs for API errors or captcha failures

### Database errors
- Ensure `data/` directory exists and is writable
- Check DB_FILE environment variable

## Getting Your Telegram ID

1. Start a chat with [@userinfobot](https://t.me/userinfobot)
2. Send any message
3. Bot replies with your user ID

Use this for `ADMIN_TELEGRAM_ID` in `.env`

## Support

Check logs:
```bash
# Docker
docker-compose logs -f

# Local
# Logs printed to console
```

Statistics:
```
/stats in Telegram
```

## License

Private use only.
