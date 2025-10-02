# AI-Powered Features Documentation

## Overview

The bot now includes AI-powered natural language understanding to help users find services and get official information without navigating through categories.

## Features

### 1. `/ask` Command - Natural Language Service Discovery

Users can ask questions in natural language, and the AI will:
- Understand the intent
- Suggest relevant services
- Provide official information
- Answer common questions

#### Usage Examples

**Service Discovery:**
```
/ask Ich brauche einen Termin für meinen Aufenthaltstitel
→ AI suggests: "Notfall-Hilfe Aufenthaltstitel" services

/ask Ich bin neu in München und muss mich anmelden
→ AI suggests: "Wohnsitzanmeldung" and related services

/ask Mein Auto ummelden
→ AI suggests: Vehicle registration services
```

**Information Requests:**
```
/ask Welche Dokumente brauche ich für die Eheschließung?
→ AI provides: List of required documents + link to official info

/ask Wie funktioniert die Terminvereinbarung?
→ AI explains: Process overview + reference to 115 hotline

/ask Wann hat die Ausländerbehörde geöffnet?
→ AI provides: General opening hours info + official website link
```

### 2. AI-Enhanced Service Details

When viewing service details, the bot can optionally show:
- Brief explanation of what the service is for
- Who typically needs it
- Common required documents

**Note:** This feature requires OPENAI_API_KEY to be configured.

### 3. Dual-Mode Operation

The bot works in two modes:

#### **With AI (OPENAI_API_KEY configured):**
- Full natural language understanding
- Smart service suggestions
- Context-aware answers
- AI-enhanced service descriptions

#### **Without AI (fallback mode):**
- Keyword-based service matching
- Still functional for basic queries
- Falls back gracefully if API unavailable
- No AI-enhanced descriptions

## Configuration

### Required Environment Variables

```bash
# Optional - enables AI features
OPENAI_API_KEY=sk-...

# Optional - customize model
OPENAI_MODEL=gpt-4o-mini  # Default: gpt-4o-mini

# Optional - use alternative OpenAI-compatible API
OPENAI_API_URL=https://api.openai.com/v1/chat/completions
```

### Supported Models

- **gpt-4o-mini** (recommended) - Fast, cheap, good quality
- **gpt-4o** - Higher quality, more expensive
- **gpt-3.5-turbo** - Faster, cheaper, lower quality
- Any OpenAI-compatible API (e.g., Azure OpenAI, local models)

### Cost Considerations

Typical costs with `gpt-4o-mini`:
- Service search query: ~$0.0001 - $0.0003 per request
- Information request: ~$0.0002 - $0.0005 per request
- Enhanced service info: ~$0.0001 per service

**Estimated monthly cost for 1000 users:**
- ~1000 /ask commands/month = ~$0.20 - $0.50/month

Very affordable for most use cases.

## Architecture

### Components

1. **`ai_assistant.py`**
   - `parse_user_request()` - Intent classification + service matching
   - `get_official_information()` - Information retrieval
   - `enhance_service_info()` - Service description enhancement
   - `_fallback_keyword_matching()` - Keyword-based fallback

2. **`bot_commands.py`**
   - `ask_command()` - Main /ask handler
   - `enhanced_service_details()` - Shows AI-enhanced service info

### Flow Diagram

```
User: /ask Ich brauche einen Aufenthaltstitel
         ↓
    AI Analysis (parse_user_request)
         ↓
  ┌──────┴──────┐
  │             │
Intent:      Intent:
service      information
search       request
  │             │
  ↓             ↓
Suggest      Get official
services     info from AI
  │             │
  └──────┬──────┘
         ↓
   Show results
   + buttons
```

### Intent Classification

The AI classifies requests into:

1. **`service_search`**
   - User wants to find/book an appointment
   - Returns: List of matching service IDs
   - Shows: Buttons to subscribe to suggested services

2. **`information_request`**
   - User has a question
   - Returns: Text answer
   - Shows: Answer + links to official resources

### Service Matching Logic

**With AI:**
```python
1. Send user query + service catalog (first 50 services) to GPT
2. AI analyzes query intent and context
3. AI returns matching service IDs with explanation
4. Display services as buttons
```

**Without AI (fallback):**
```python
1. Extract keywords from user query
2. Match keywords against service names
3. Score matches by keyword frequency
4. Return top-scored services
```

## Example Conversations

### Example 1: Service Discovery

```
User: /ask Ich brauche einen neuen Personalausweis

Bot: 🎯 Passende Dienste gefunden:

📋 Personalausweis
📋 Abholung Personalausweis, Reisepass oder eID-Karte
📋 Verlust oder Diebstahl Personalausweis

💡 Tippen Sie auf einen Dienst für Details und Abonnement.

[Buttons for each service]
```

User taps "Personalausweis" →
```
Bot: Personalausweis

ℹ️ Dieser Dienst ermöglicht die Beantragung eines neuen
Personalausweises. Benötigt wird in der Regel: biometrisches
Passfoto, alter Personalausweis, Meldebestätigung.

Service ID: 1063441
Max. Anzahl: 2

Status: ⭕ Nicht abonniert

[✅ Abonnieren button]
```

### Example 2: Information Request

```
User: /ask Welche Dokumente brauche ich für die Wohnsitzanmeldung?

Bot: 🔍 Ihre Frage wird bearbeitet...

Bot: ℹ️ Information

Für die Wohnsitzanmeldung in München benötigen Sie:
- Personalausweis oder Reisepass
- Wohnungsgeberbestätigung (vom Vermieter)
- Bei Ehepartnern: Heiratsurkunde
- Bei Kindern: Geburtsurkunden

Die Anmeldung muss innerhalb von 2 Wochen nach Einzug erfolgen.

📞 Weitere Fragen? Rufen Sie die 115 an.
🌐 Oder besuchen Sie: https://stadt.muenchen.de
```

### Example 3: Vague Request

```
User: /ask Ich bin neu in München

Bot: 🎯 Passende Dienste gefunden:

Basierend auf Ihrer Anfrage könnten diese Dienste relevant sein:

📋 Wohnsitzanmeldung
📋 Wohnsitzanmeldung – Familie
📋 Meldebescheinigung

💡 Tippen Sie auf einen Dienst für Details und Abonnement.

[Buttons]
```

## Fallback Behavior

### When AI is unavailable:

1. **Keyword matching activates**
   - Extracts keywords from query
   - Matches against service names
   - Returns best matches

2. **No enhanced descriptions**
   - Service details show basic info only
   - No AI-generated explanations

3. **No information requests**
   - `/ask` only works for service search
   - Information queries return "not available"

### Fallback Keywords

Predefined mappings:
- `aufenthalt` → Residence permits
- `pass`, `ausweis` → ID documents
- `fahrzeug`, `auto` → Vehicle services
- `führerschein` → Driver's license
- `wohnung`, `umzug` → Registration
- `gewerbe`, `firma` → Business
- `heirat`, `hochzeit` → Marriage
- `notfall`, `dringend` → Emergency appointments

## Best Practices

### For Users

1. **Be specific:**
   - ✅ "Ich brauche einen Termin für meinen Aufenthaltstitel"
   - ❌ "Termin"

2. **Ask in German:**
   - AI works best with German queries
   - English might work but less reliable

3. **One question at a time:**
   - ✅ "Welche Dokumente für Personalausweis?"
   - ❌ "Dokumente für Personalausweis und was kostet das und wo..."

### For Administrators

1. **Monitor API usage:**
   - Check OpenAI dashboard for costs
   - Set up billing alerts

2. **Rate limiting:**
   - Consider adding per-user rate limits
   - Default: unlimited (trust-based)

3. **Privacy:**
   - User queries sent to OpenAI
   - No PII should be in queries
   - Consider adding disclaimer

4. **Testing:**
   - Test both AI and fallback modes
   - Verify service matching quality

## Limitations

### Current Limitations

1. **Context window:**
   - Only first 50 services sent to AI
   - Saves tokens but might miss obscure services
   - Fallback still searches all 153 services

2. **No conversation memory:**
   - Each /ask is independent
   - No follow-up question support
   - Could be added with ConversationHandler

3. **Information accuracy:**
   - AI generates answers based on training data
   - Always includes "call 115" disclaimer
   - Not a replacement for official sources

4. **Language:**
   - Optimized for German
   - English queries might work
   - Other languages untested

### Future Enhancements

- [ ] Add conversation memory for follow-ups
- [ ] Fetch live data from stadt.muenchen.de
- [ ] Support for document uploads (analyze papers)
- [ ] Multi-language support
- [ ] Voice message support (Whisper API)

## Troubleshooting

### AI not working

**Check environment:**
```bash
echo $OPENAI_API_KEY
# Should output: sk-...
```

**Test API directly:**
```python
import requests
headers = {'Authorization': f'Bearer {OPENAI_API_KEY}'}
r = requests.get('https://api.openai.com/v1/models', headers=headers)
print(r.status_code)  # Should be 200
```

**Check logs:**
```bash
docker-compose logs -f | grep "AI request"
```

### Poor service suggestions

**Possible causes:**
1. Query too vague → Ask user to be more specific
2. Service not in top 50 → Will use fallback matching
3. New/obscure service → Might not be in AI training data

**Solutions:**
- Increase services sent to AI (edit `ai_assistant.py`)
- Improve keyword fallback mappings
- Add user feedback mechanism

### High API costs

**Optimize:**
1. Use `gpt-4o-mini` instead of `gpt-4o`
2. Reduce max_tokens in prompts
3. Add rate limiting per user
4. Cache common queries

**Monitor:**
```bash
# Check OpenAI usage dashboard
https://platform.openai.com/usage
```

## Security Considerations

### Data Privacy

- User queries sent to OpenAI
- Covered by OpenAI's privacy policy
- No PII should be in service names
- Consider adding privacy disclaimer

### API Key Security

- Never commit OPENAI_API_KEY to git
- Use environment variables only
- Rotate keys periodically
- Set up OpenAI usage limits

### Prompt Injection

Current mitigations:
- System prompt clearly defines role
- JSON response format enforced
- Temperature set to 0.3 (less creative)
- User input not executed as code

Additional recommendations:
- Add input validation
- Limit query length
- Monitor for abuse patterns

## License & Attribution

- Uses OpenAI GPT models (commercial use allowed)
- Complies with OpenAI Terms of Service
- Munich service data: Public information from stadt.muenchen.de
