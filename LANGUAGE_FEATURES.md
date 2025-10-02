# Multi-Language Support Documentation

## Overview

The bot now supports **three languages**:
- 🇩🇪 **German (Deutsch)** - Default
- 🇬🇧 **English**
- 🇷🇺 **Russian (Русский)**

## Features

### 1. Language Selection on First Start

When a user runs `/start` for the first time, they see:

```
🌐 Choose your language / Wählen Sie Ihre Sprache / Выберите язык

[🇩🇪 Deutsch] [🇬🇧 English]
     [🇷🇺 Русский]
```

After selecting, they see the welcome message in their chosen language.

### 2. Change Language Anytime

Users can change language with:
```
/language
```

This shows the same language selection menu.

### 3. AI Translation for Information Responses

When using `/ask` for information requests, the bot adds **translate buttons**:

**Example:**
```
User: /ask Welche Dokumente brauche ich für die Eheschließung?

Bot: ℹ️ Information

Für die Eheschließung benötigen Sie...
[Long answer in German]

📞 Weitere Fragen? Rufen Sie die 115 an.

[🇬🇧 Translate to English]
[🇷🇺 Translate to Russian]
```

**User taps "Translate to English":**
```
Bot: [Edits message]

ℹ️ Information

For marriage registration you need...
[Translated answer in English]

📞 More questions? Call 115.

⚠️ Automatic translation - may contain errors

[🇩🇪 Translate to Deutsch]
[🇷🇺 Translate to Russian]
```

### 4. Persistent Language Preference

User's language choice is **saved in the database** and used for:
- Welcome messages
- Bot responses
- Button labels (future enhancement)
- Error messages (future enhancement)

## Implementation Details

### Database Schema

```sql
ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'de';
```

**New Functions:**
- `get_user_language(user_id)` - Get user's preferred language
- `set_user_language(user_id, language)` - Set user's language

### Translation System

**File:** `translations.py`

**Components:**
1. **Static Messages** - Pre-translated common bot messages
2. **AI Translation** - OpenAI API for dynamic content
3. **Language Management** - Helper functions

### Static vs Dynamic Translation

**Static (Pre-translated):**
- Welcome messages
- Command descriptions
- Button labels
- Common phrases

**Dynamic (AI-translated on demand):**
- Official information responses
- Service descriptions (when AI-enhanced)
- User-specific content

### Translation Flow

```
1. User requests info in German
2. Bot responds with German info + translate buttons
3. User taps "Translate to English"
4. Bot calls OpenAI API to translate
5. Bot edits message with English + disclaimer
6. Shows buttons for DE/RU translation
```

## Configuration

### Environment Variables

**Same as AI features:**
```bash
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

**Cost per translation:**
- ~$0.0002 - $0.0005 per translation
- Very affordable for occasional use

### Fallback Behavior

**Without OPENAI_API_KEY:**
- Language selection still works
- Static messages in user's language
- Translate buttons **not shown**
- Bot defaults to German for dynamic content

## Usage Examples

### Example 1: New User

```
User: /start

Bot: 🌐 Choose your language / Wählen Sie Ihre Sprache / Выберите язык
[Language buttons]

User: *taps 🇷🇺 Русский*

Bot: ✅ Язык изменен на Русский

🎯 Мюнхенский бот записи

Добро пожаловать! Я уведомлю вас, когда появятся свободные записи.

Команды:
🤖 /ask - AI-ассистент...
[Full welcome in Russian]
```

### Example 2: Changing Language

```
User (current language: German): /language

Bot: 🌐 Choose your language / Wählen Sie Ihre Sprache / Выберите язык
[Language buttons]

User: *taps 🇬🇧 English*

Bot: ✅ Language changed to English

🎯 Munich Appointment Bot

Welcome! I'll notify you when appointments become available.
[Full welcome in English]
```

### Example 3: Translating Information

```
User (language: English): /ask What documents do I need for marriage registration?

Bot: ℹ️ Information

For marriage registration in Munich you need:
- Valid passport or ID
- Birth certificate
- Proof of residence
...

📞 More questions? Call 115.
🌐 Visit: https://stadt.muenchen.de

[🇩🇪 Translate to Deutsch]
[🇷🇺 Translate to Russian]

User: *taps Translate to Russian*

Bot: [Message updates]

ℹ️ Информация

Для регистрации брака в Мюнхене вам понадобятся:
- Действительный паспорт или удостоверение личности
- Свидетельство о рождении
- Подтверждение места жительства
...

📞 Дополнительные вопросы? Позвоните 115.
🌐 Посетите: https://stadt.muenchen.de

⚠️ Автоматический перевод - может содержать ошибки

[🇩🇪 Translate to Deutsch]
[🇬🇧 Translate to English]
```

## Current Limitations

### What's Translated

✅ **Static content:**
- Welcome messages
- Command descriptions
- Status messages
- Button labels

✅ **Dynamic content (with AI):**
- Information responses from `/ask`
- On-demand translation via buttons

### What's NOT Translated Yet

❌ **Service names** - Always in German (official names)
❌ **Category names** - Currently in German
❌ **Appointment notifications** - Need to add language support
❌ **Error messages** - Most still in German

### Future Enhancements

- [ ] Translate service/category names
- [ ] Multi-language appointment notifications
- [ ] Translate error messages
- [ ] Add more languages (Turkish, Arabic, etc.)
- [ ] Cache common translations to reduce API calls
- [ ] User can set preferred language for notifications

## Translation Quality

### Disclaimer

All AI translations include:
```
⚠️ Automatic translation - may contain errors
```

**In each language:**
- 🇩🇪 "Automatische Übersetzung - kann Fehler enthalten"
- 🇬🇧 "Automatic translation - may contain errors"
- 🇷🇺 "Автоматический перевод - может содержать ошибки"

### Tips for Better Translations

**AI is trained to:**
1. Preserve HTML formatting
2. Keep technical terms in original language when appropriate
3. Maintain URLs and links exactly
4. Use formal language for official communications

**Best practices:**
- Original German text should be clear and well-formatted
- Avoid complex nested HTML
- Keep sentences reasonably short
- Use standard terminology

## Database Migration

**For existing users:**

The database will automatically add the `language` column with default value `'de'` (German).

**To manually add the column:**
```sql
ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'de';
```

**No data loss** - existing users will default to German and can change via `/language`.

## API Usage Tracking

### Translation Costs

Typical translation with `gpt-4o-mini`:

| Content Type | Tokens | Cost |
|--------------|--------|------|
| Short answer (100 words) | ~200 | $0.0001 |
| Medium answer (300 words) | ~600 | $0.0003 |
| Long answer (500 words) | ~1000 | $0.0005 |

### Expected Usage

**Conservative estimate for 1000 users:**
- 10% use /ask for information: 100 users
- 50% translate responses: 50 translations
- Average cost per translation: $0.0003
- **Monthly cost: ~$0.015** (1.5 cents)

**Very affordable!**

### Monitoring

Check OpenAI dashboard:
```
https://platform.openai.com/usage
```

Filter by model: `gpt-4o-mini`

## Privacy & Security

### Data Sent to OpenAI

**What's sent:**
- Text to be translated
- Source and target language
- System prompt (translation instructions)

**What's NOT sent:**
- User IDs
- Personal information
- Conversation history
- Database content

### GDPR Compliance

Translation feature is **GDPR-compliant** when:
1. User initiates translation (explicit action)
2. Only message content is sent
3. No personal identifiers included
4. OpenAI complies with GDPR

**Recommendation:** Add privacy notice in `/start` message mentioning AI usage.

## Troubleshooting

### Translations not appearing

**Check:**
1. Is `OPENAI_API_KEY` set in `.env`?
2. Is API key valid?
3. Check logs for API errors

**Test:**
```bash
# In terminal
echo $OPENAI_API_KEY
# Should output: sk-...

# Test bot
/ask Welche Dokumente brauche ich?
# Should show translate buttons
```

### Translation button does nothing

**Possible causes:**
1. API key invalid/expired
2. OpenAI API down
3. Network issues

**Check logs:**
```bash
docker-compose logs -f | grep "Translation"
```

### Translations have formatting issues

**Common issues:**
- HTML tags broken: Check original message formatting
- Links broken: Ensure URLs are properly formatted
- Encoding issues: Use UTF-8 encoding

**Solutions:**
- Simplify HTML in original messages
- Test with `gpt-4o` for better quality (costs more)
- Add more specific instructions to translation prompt

## Testing

### Test Language Selection

```
1. /start (new user) → Should show language selection
2. Select Russian → Welcome in Russian
3. /language → Show selection again
4. Select English → Welcome in English
5. /start → Welcome in English (remembered)
```

### Test Translation

```
1. Set language to German
2. /ask Welche Dokumente brauche ich für die Wohnsitzanmeldung?
3. Should see German answer + EN/RU translate buttons
4. Tap "Translate to English"
5. Should see English translation + DE/RU buttons
6. Tap "Translate to Russian"
7. Should see Russian translation + DE/EN buttons
```

### Test Persistence

```
1. Select language Russian
2. Restart bot: docker-compose restart
3. /start → Should still be in Russian
4. Check database:
   SELECT user_id, language FROM users;
```

## Advanced Configuration

### Add More Languages

**Edit `translations.py`:**

```python
LANGUAGES = {
    'de': {'name': 'Deutsch', 'flag': '🇩🇪'},
    'en': {'name': 'English', 'flag': '🇬🇧'},
    'ru': {'name': 'Русский', 'flag': '🇷🇺'},
    'tr': {'name': 'Türkçe', 'flag': '🇹🇷'},  # Add Turkish
    'ar': {'name': 'العربية', 'flag': '🇸🇦'}   # Add Arabic
}
```

**Add static translations:**

```python
MESSAGES = {
    'welcome': {
        'de': '...',
        'en': '...',
        'ru': '...',
        'tr': 'Hoş geldiniz!...',
        'ar': 'مرحبا!...'
    }
}
```

**Update language selection buttons in `bot_commands.py`.**

### Customize Translation Prompt

**Edit `translations.py` → `translate_text()` function:**

```python
system_prompt = f"""You are a professional translator specializing in legal and bureaucratic German.
Translate from {source_name} to {target_name}.

Special instructions:
- Keep official terms in German: "Aufenthaltstitel", "Meldebescheinigung"
- Use formal "Sie" form in German
- Preserve HTML formatting: <b>, <i>, <code>, <a>
- Keep URLs unchanged

Translate this official information:"""
```

## Support

### Common User Questions

**Q: How do I change the language?**
A: Type `/language` and select your preferred language.

**Q: Can I get notifications in my language?**
A: Currently notifications are in German. Multi-language notifications coming soon!

**Q: Is the translation accurate?**
A: AI translations are generally good but may have minor errors. Always verify important information with official sources (call 115).

**Q: Which languages are supported?**
A: Currently: German, English, and Russian. More languages can be added upon request.

## Summary

✨ **Key Benefits:**
- Users can choose their preferred language
- Easy language switching with `/language`
- AI-powered translation for information responses
- Translation disclaimer for transparency
- Low cost (<$0.01/month for typical usage)
- Fully integrated with existing bot features

🚀 **Ready to use** - works right now with minimal configuration!
