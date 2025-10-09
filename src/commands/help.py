"""
/help command - Comprehensive help documentation
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show comprehensive help information"""
    help_text = (
        "📚 <b>Help & Documentation</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>🚀 GETTING STARTED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ <b>Register:</b> Use /start to create your account\n"
        "2️⃣ <b>Set Date Range:</b> Use /setdates to choose when you're available\n"
        "3️⃣ <b>Subscribe:</b> Use /subscribe to select services to monitor\n"
        "4️⃣ <b>Wait:</b> You'll get instant notifications when appointments open up!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>📝 COMMANDS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>/start</b> - Register and see welcome message\n"
        "<b>/menu</b> - Show main menu with quick actions\n"
        "<b>/subscribe</b> - Subscribe to appointment services\n"
        "<b>/myservices</b> - View and manage your subscriptions\n"
        "<b>/setdates</b> - Set your preferred date range\n"
        "<b>/status</b> - Check your account status and stats\n"
        "<b>/stop</b> - Unsubscribe from all services and delete data\n"
        "<b>/help</b> - Show this help message\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>💡 KEY CONCEPTS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Subscribe vs Book:</b>\n"
        "• <b>Subscribe</b> = Monitor a service for availability\n"
        "• <b>Book</b> = Reserve a specific appointment slot\n\n"
        "<b>Date Range:</b>\n"
        "Set the time period when you're available for appointments. "
        "The bot only searches within your date range.\n\n"
        "<b>Multiple Subscriptions:</b>\n"
        "You can subscribe to multiple services and offices. "
        "The bot monitors all of them simultaneously.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>🔧 TROUBLESHOOTING</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Not getting notifications?</b>\n"
        "• Check your subscriptions with /myservices\n"
        "• Verify your date range with /status\n"
        "• Ensure your Telegram notifications are enabled\n\n"
        "<b>Booking fails?</b>\n"
        "• Appointments fill up fast - try booking immediately\n"
        "• Your session may have timed out (15 min limit)\n"
        "• Try booking another available slot\n\n"
        "<b>Can't find my service?</b>\n"
        "• Browse by category in /subscribe\n"
        "• Check if the service name has changed\n"
        "• Some services may not be available for online booking\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>❓ TIPS & BEST PRACTICES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ Set a realistic date range (e.g., next 3 months)\n"
        "✅ Subscribe to multiple offices for better availability\n"
        "✅ Book immediately when you receive a notification\n"
        "✅ Check your email and confirm within 24 hours\n"
        "✅ Use /status regularly to monitor bot activity\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        help_text, reply_markup=reply_markup, parse_mode="HTML"
    )
