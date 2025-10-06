"""
Munich Appointment Bot - Main application
Refactored to use modern architecture with repositories and type safety
"""
import time
import asyncio
import logging
import json
from datetime import datetime, timedelta
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# New architecture imports
from config import get_config
from database import init_database, get_session
from repositories import UserRepository, SubscriptionRepository, AppointmentLogRepository
from models import Language

# Old modules (to be migrated)
from termin_tracker import get_fresh_captcha_token, get_available_days, get_available_slots
from services_manager import get_service_info
import bot_commands

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global stats
stats = {
    'total_checks': 0,
    'successful_checks': 0,
    'failed_checks': 0,
    'appointments_found_count': 0,
    'last_check_time': None,
    'last_success_time': None,
    'bot_start_time': None
}

# Store the captcha token and its expiry time
captcha_token = None
token_expires_at = 0


def get_user_date_range(user_id: int) -> tuple[str | None, str | None]:
    """
    Get user's date range preference

    Args:
        user_id: Telegram user ID

    Returns:
        Tuple of (start_date, end_date) or (None, None)
    """
    with get_session() as session:
        user_repo = UserRepository(session)
        user = user_repo.get_user(user_id)

        if not user:
            return None, None

        start_date = user.start_date
        end_date = user.end_date

        # Default to next 60 days if not set
        if not start_date:
            start_date = datetime.now().strftime('%Y-%m-%d')
        if not end_date:
            end_date = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d')

        return start_date, end_date


def format_available_appointments(data) -> str:
    """Format available appointments data for display"""
    if not data:
        return ""

    result = ""

    # Handle Munich API format with time slots
    if isinstance(data, dict) and 'slots_by_date' in data:
        slots_by_date = data['slots_by_date']
        available_days = data.get('availableDays', [])

        if slots_by_date:
            # Show dates with time slots
            for date, times in list(slots_by_date.items())[:5]:
                if times:
                    # Show first 5 time slots
                    time_str = ', '.join(times[:5])
                    result += f"📅 {date}: {time_str}\n"
                else:
                    # Date available but no time slots fetched
                    result += f"📅 {date}\n"

            # Show remaining days count
            remaining = len(available_days) - len(slots_by_date)
            if remaining > 0:
                result += f"... und {remaining} weitere Tage\n"

        return result.strip()

    # Handle Munich API format without slots: {'availableDays': [{'time': '2025-10-13', 'providerIDs': '10461'}]}
    if isinstance(data, dict) and 'availableDays' in data:
        available_days = data['availableDays']
        if available_days:
            for day in available_days[:5]:
                date = day.get('time', 'Unknown date')
                result += f"📅 {date}\n"
            if len(available_days) > 5:
                result += f"... und {len(available_days) - 5} weitere Tage\n"
        return result.strip()

    # Legacy format handling
    if isinstance(data, dict):
        for date, times in data.items():
            if times:
                # Handle times as list of strings or list of dicts
                if isinstance(times, list):
                    time_strs = []
                    for t in times[:3]:
                        if isinstance(t, dict):
                            # Extract time from dict (e.g., {'time': '09:00', ...})
                            time_strs.append(str(t.get('time', t.get('slot', str(t)))))
                        else:
                            time_strs.append(str(t))
                    result += f"📅 {date}: {', '.join(time_strs)}\n"
                else:
                    result += f"📅 {date}: {times}\n"
    elif isinstance(data, list):
        for item in data[:5]:
            if isinstance(item, dict) and 'date' in item:
                result += f"📅 {item['date']}\n"
            elif isinstance(item, str):
                result += f"📅 {item}\n"

    return result.strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - delegates to bot_commands"""
    await bot_commands.start(update, context)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop command"""
    user_id = update.effective_user.id

    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        # Delete all subscriptions
        count = sub_repo.delete_all_user_subscriptions(user_id)

        # Delete user
        user_repo.delete_user(user_id)

    await update.message.reply_text(
        f"👋 Sie wurden abgemeldet und {count} Abonnement(s) wurden entfernt.\n\n"
        "Verwenden Sie /start, um sich erneut anzumelden."
    )
    logger.info(f"User {user_id} unsubscribed and removed {count} subscriptions")


async def setdates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setdates command to set date range"""
    user_id = update.effective_user.id

    if len(context.args) != 2:
        await update.message.reply_text(
            "📅 <b>Datumsbereich festlegen</b>\n\n"
            "Verwendung: <code>/setdates YYYY-MM-DD YYYY-MM-DD</code>\n\n"
            "Beispiel:\n"
            "<code>/setdates 2025-10-01 2025-10-31</code>\n\n"
            "Damit legen Sie fest, in welchem Zeitraum nach Terminen gesucht werden soll.",
            parse_mode='HTML'
        )
        return

    start_date = context.args[0]
    end_date = context.args[1]

    # Basic validation
    try:
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        await update.message.reply_text(
            "❌ Ungültiges Datumsformat. Bitte verwenden Sie YYYY-MM-DD\n\n"
            "Beispiel: <code>/setdates 2025-10-01 2025-10-31</code>",
            parse_mode='HTML'
        )
        return

    with get_session() as session:
        user_repo = UserRepository(session)
        user_repo.set_date_range(user_id, start_date, end_date)

    await update.message.reply_text(
        f"✅ Datumsbereich aktualisiert!\n\n"
        f"Von: <b>{start_date}</b>\n"
        f"Bis: <b>{end_date}</b>\n\n"
        f"Der Bot sucht nun nach Terminen in diesem Zeitraum.",
        parse_mode='HTML'
    )
    logger.info(f"User {user_id} set date range: {start_date} to {end_date}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot status"""
    user_id = update.effective_user.id

    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        user = user_repo.get_user(user_id)
        if not user:
            await update.message.reply_text(
                "❌ Sie sind nicht registriert.\n\nVerwenden Sie /start, um sich anzumelden."
            )
            return

        subs = sub_repo.get_user_subscriptions(user_id)
        total_users = len(user_repo.get_all_users())
        user_language = user.language
        num_subs = len(subs)

    start_date, end_date = get_user_date_range(user_id)

    message = (
        "📊 <b>Ihr Status</b>\n\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"📋 Abonnements: <b>{num_subs}</b>\n"
        f"📅 Datumsbereich: {start_date} bis {end_date}\n"
        f"🌐 Sprache: {user_language}\n\n"
        f"👥 Gesamt Benutzer: <b>{total_users}</b>\n\n"
        f"⏱ Prüfintervall: {get_config().check_interval} Sekunden"
    )

    await update.message.reply_text(message, parse_mode='HTML')


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot statistics"""
    config = get_config()

    uptime = "N/A"
    if stats['bot_start_time']:
        uptime_seconds = (datetime.now() - stats['bot_start_time']).total_seconds()
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        uptime = f"{hours}h {minutes}m"

    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        total_users = len(user_repo.get_all_users())
        service_subs = sub_repo.get_all_service_subscriptions()
        total_services = len(service_subs)

    success_rate = 0
    if stats['total_checks'] > 0:
        success_rate = (stats['successful_checks'] / stats['total_checks']) * 100

    message = (
        "📈 <b>Bot Statistiken</b>\n\n"
        f"⏱ Uptime: {uptime}\n"
        f"👥 Benutzer: {total_users}\n"
        f"📋 Unique Service-Abos: {total_services}\n\n"
        f"🔍 Prüfungen gesamt: {stats['total_checks']}\n"
        f"✅ Erfolgreich: {stats['successful_checks']}\n"
        f"❌ Fehlgeschlagen: {stats['failed_checks']}\n"
        f"📊 Erfolgsquote: {success_rate:.1f}%\n\n"
        f"🎯 Termine gefunden: {stats['appointments_found_count']}\n"
    )

    if stats['last_check_time']:
        message += f"\n⏰ Letzte Prüfung: {stats['last_check_time'].strftime('%H:%M:%S')}"
    if stats['last_success_time']:
        message += f"\n✅ Letzter Erfolg: {stats['last_success_time'].strftime('%H:%M:%S')}"

    await update.message.reply_text(message, parse_mode='HTML')


async def send_health_alert(application: Application, message: str):
    """Send health alert to admin"""
    config = get_config()

    if config.admin_telegram_id:
        try:
            await application.bot.send_message(
                chat_id=config.admin_telegram_id,
                text=f"🚨 <b>Health Alert</b> 🚨\n\n{message}",
                parse_mode='HTML'
            )
            logger.info("Health alert sent to admin")
        except Exception as e:
            logger.error(f"Failed to send health alert: {e}")


async def check_and_notify(application: Application) -> None:
    """Background task to check for appointments and notify subscribers"""
    global captcha_token, token_expires_at

    config = get_config()
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 5

    while True:
        try:
            stats['last_check_time'] = datetime.now()
            stats['total_checks'] += 1

            # Get all service subscriptions using repository
            with get_session() as session:
                sub_repo = SubscriptionRepository(session)
                service_subs = sub_repo.get_all_service_subscriptions()

            if not service_subs:
                logger.info("No service subscriptions, skipping check")
                await asyncio.sleep(config.check_interval)
                continue

            # Refresh token if needed
            if time.time() >= token_expires_at:
                logger.info("Getting fresh captcha token...")
                captcha_token = get_fresh_captcha_token()
                if not captcha_token:
                    logger.error("Failed to get captcha token")
                    stats['failed_checks'] += 1
                    consecutive_failures += 1

                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        await send_health_alert(
                            application,
                            f"Bot has failed {consecutive_failures} consecutive checks!\n"
                            f"Last error: Failed to get captcha token"
                        )

                    await asyncio.sleep(config.check_interval)
                    continue
                token_expires_at = time.time() + 280  # ~4.5 minutes
                logger.info("Got fresh token")

            # Check each unique service/office combination
            for service_office_key, user_ids in service_subs.items():
                service_id, office_id = service_office_key.split('_')
                service_id = int(service_id)
                office_id = int(office_id)

                # Get date ranges for users subscribed to this service
                date_ranges = {}
                for user_id in user_ids:
                    start_date, end_date = get_user_date_range(user_id)
                    if start_date and end_date:
                        key = f"{start_date}_{end_date}"
                        if key not in date_ranges:
                            date_ranges[key] = []
                        date_ranges[key].append(user_id)

                # Check each unique date range for this service
                for date_key, date_user_ids in date_ranges.items():
                    start_date, end_date = date_key.split('_')

                    # Get service name for logging
                    service_info = get_service_info(service_id)
                    service_name = service_info['name'] if service_info else f"Service {service_id}"

                    logger.info(f"Checking {service_name} (ID:{service_id}, Office:{office_id}) from {start_date} to {end_date} for {len(date_user_ids)} users")
                    data = get_available_days(start_date, end_date, captcha_token, str(office_id), str(service_id))

                    # Check if appointments are available
                    appointments_found = False
                    slots_by_date = {}  # Will store {date: [time slots]}

                    if isinstance(data, dict):
                        if "errorCode" in data:
                            logger.warning(f"API error: {data['errorCode']} - {data.get('errorMessage', '')}")
                            stats['failed_checks'] += 1
                            consecutive_failures += 1
                        elif data and len(data) > 0:
                            # Extract available days from response
                            available_days = data.get('availableDays', [])
                            if available_days:
                                appointments_found = True
                    elif isinstance(data, list) and len(data) > 0:
                        appointments_found = True

                    if appointments_found:
                        logger.info(f"✅ Appointments found for {service_name}! Notifying {len(date_user_ids)} users")
                        logger.info(f"📋 Full API response: {data}")
                        stats['successful_checks'] += 1
                        stats['last_success_time'] = datetime.now()
                        stats['appointments_found_count'] += 1
                        consecutive_failures = 0

                        # Log the appointment with repository
                        with get_session() as session:
                            log_repo = AppointmentLogRepository(session)
                            log_repo.log_appointment(service_id, office_id, data)

                        # Build booking URL
                        booking_url = config.get_booking_url_for_service(service_id, office_id)

                        # STEP 1: Send immediate notification with dates only
                        available_days = data.get('availableDays', [])
                        initial_dates = '\n'.join([f"📅 {day.get('time')}" for day in available_days[:5]])
                        if len(available_days) > 5:
                            initial_dates += f"\n... und {len(available_days) - 5} weitere Tage"

                        initial_message = (
                            "🎉 <b>TERMIN VERFÜGBAR!</b> 🎉\n\n"
                            f"<b>{service_name}</b>\n\n"
                            f"Verfügbare Termine:\n{initial_dates}\n\n"
                            f"🔗 <a href='{booking_url}'>Jetzt Termin buchen!</a>\n\n"
                            "⏳ Zeiten werden geladen..."
                        )

                        # Send initial messages and store message IDs for updating
                        message_ids = {}
                        for user_id in date_user_ids:
                            try:
                                sent_msg = await application.bot.send_message(
                                    chat_id=user_id,
                                    text=initial_message,
                                    parse_mode='HTML',
                                    disable_web_page_preview=False
                                )
                                message_ids[user_id] = sent_msg.message_id
                                logger.info(f"Sent initial notification to user {user_id}")
                            except Exception as e:
                                logger.error(f"Failed to send initial notification to user {user_id}: {e}")

                        # STEP 2: Fetch time slots and update messages progressively
                        from datetime import datetime
                        for day_info in available_days[:5]:
                            date = day_info.get('time')
                            if date:
                                slots_data = get_available_slots(date, str(office_id), str(service_id), captcha_token)
                                if slots_data and isinstance(slots_data, dict):
                                    # New API format: {"offices": [{"officeId": X, "appointments": [timestamps]}]}
                                    offices = slots_data.get('offices', [])
                                    if offices:
                                        # Get appointments from first office (we only query one)
                                        appointments_timestamps = offices[0].get('appointments', [])
                                        if appointments_timestamps:
                                            # Convert Unix timestamps to HH:MM format (show first 5)
                                            times = []
                                            for ts in appointments_timestamps[:5]:
                                                dt = datetime.fromtimestamp(ts)
                                                times.append(dt.strftime('%H:%M'))
                                            slots_by_date[date] = times
                                        else:
                                            slots_by_date[date] = []
                                    else:
                                        slots_by_date[date] = []
                                else:
                                    # Fallback: just show the date without times
                                    slots_by_date[date] = []

                        # Update data to include slots
                        data['slots_by_date'] = slots_by_date
                        logger.info(f"📋 Slots by date: {slots_by_date}")

                        # STEP 3: Update all messages with final time slot information
                        appointments_detail = format_available_appointments(data)

                        final_message = (
                            "🎉 <b>TERMIN VERFÜGBAR!</b> 🎉\n\n"
                            f"<b>{service_name}</b>\n\n"
                        )

                        if appointments_detail:
                            final_message += f"Verfügbare Termine:\n{appointments_detail}\n\n"
                        else:
                            final_message += f"Verfügbare Termine:\n{initial_dates}\n\n"

                        final_message += (
                            f"🔗 <a href='{booking_url}'>Jetzt Termin buchen!</a>\n\n"
                            "⚡ Schnell handeln - Termine werden schnell vergeben!"
                        )

                        # Update all messages with time slots
                        for user_id, msg_id in message_ids.items():
                            try:
                                await application.bot.edit_message_text(
                                    chat_id=user_id,
                                    message_id=msg_id,
                                    text=final_message,
                                    parse_mode='HTML',
                                    disable_web_page_preview=False
                                )
                                logger.info(f"Updated message for user {user_id} with time slots")
                            except Exception as e:
                                logger.error(f"Failed to update message for user {user_id}: {e}")
                    else:
                        logger.info(f"No appointments available for {service_name} ({start_date} to {end_date})")
                        stats['successful_checks'] += 1
                        stats['last_success_time'] = datetime.now()
                        consecutive_failures = 0

        except Exception as e:
            logger.error(f"Error in check_and_notify: {e}")
            stats['failed_checks'] += 1
            consecutive_failures += 1

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                await send_health_alert(
                    application,
                    f"Bot has failed {consecutive_failures} consecutive checks!\n"
                    f"Last error: {str(e)}"
                )

        await asyncio.sleep(config.check_interval)


async def post_init(application: Application) -> None:
    """Post-initialization callback"""
    stats['bot_start_time'] = datetime.now()

    # Set bot commands for menu
    commands = [
        BotCommand("start", "Start the bot and register"),
        BotCommand("menu", "Show main menu"),
        BotCommand("subscribe", "Subscribe to services"),
        BotCommand("myservices", "View your subscriptions"),
        BotCommand("ask", "AI-powered service search"),
        BotCommand("language", "Change language"),
        BotCommand("setdates", "Set date range filter"),
        BotCommand("status", "Show your status"),
        BotCommand("stats", "Show bot statistics"),
        BotCommand("stop", "Cancel all subscriptions"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered")

    # Load initial stats
    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        users = user_repo.get_all_users()
        service_subs = sub_repo.get_all_service_subscriptions()

        logger.info(f"Bot started! Multi-service subscription enabled.")
        logger.info(f"Loaded {len(users)} users with {len(service_subs)} unique service subscriptions")

    # Start background task
    asyncio.create_task(check_and_notify(application))


def main() -> None:
    """Main function to run the bot"""
    # Load configuration
    config = get_config()

    # Initialize database
    logger.info("Initializing database...")
    init_database()

    # Create application
    application = Application.builder().token(config.telegram_bot_token).post_init(post_init).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("setdates", setdates))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("stats", stats_command))

    # Import and register bot_commands handlers
    application.add_handler(CommandHandler("menu", bot_commands.menu_command))
    application.add_handler(CommandHandler("subscribe", bot_commands.subscribe_command))
    application.add_handler(CommandHandler("myservices", bot_commands.myservices_command))
    application.add_handler(CommandHandler("language", bot_commands.language_command))
    application.add_handler(CommandHandler("ask", bot_commands.ask_command))

    # Register callback query handler
    application.add_handler(CallbackQueryHandler(bot_commands.button_callback))

    # Run the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
