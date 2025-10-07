# Office Selection Feature

## Problem
When users subscribed to services, the bot automatically selected the first office returned by the API, which was often incorrect. For example:
- Service: "Fahrzeug abmelden" (Vehicle deregistration)
- Bot selected: Office 10218 (Urban Planning) ❌
- Correct office: Office 102101 (KfZ Zulassungsstelle) ✅

Result: Users received no notifications even when appointments were available at the correct office.

## Solution
Added office selection step during subscription process.

## New Flow

### Before:
1. User clicks "Subscribe" on a service
2. Bot automatically picks first office from API
3. Subscription created with wrong office
4. No notifications received

### After:
1. User clicks "Subscribe" on a service
2. **Bot shows list of available offices (up to 20)**
3. **User selects the correct office**
4. Subscription created with selected office
5. Notifications work correctly

## Implementation Changes

### Modified Files:

**bot_commands.py:**

1. **Updated callback handler** (line ~479):
   - `addsub:` now calls `show_office_selection()` instead of immediately subscribing
   - Added new `selectoffice:` handler for office selection

2. **New function**: `show_office_selection()`
   - Fetches all offices for the service
   - Displays up to 20 offices as buttons
   - Shows office names with IDs
   - Includes back button

3. **Enhanced** `show_myservices()`:
   - Now displays office ID for each subscription
   - Format: `📍 Office ID: 10218`

### Code Example:

```python
async def show_office_selection(query, service_id: int, user_id: int):
    """Show office selection for a service subscription"""
    offices = get_offices_for_service(service_id)

    # Build keyboard with offices
    keyboard = []
    for office in offices[:20]:
        keyboard.append([InlineKeyboardButton(
            f"📍 {office['name']}",
            callback_data=f"selectoffice:{service_id}:{office['id']}"
        )])
```

## User Experience

**Step 1 - Service Details:**
```
Fahrzeug abmelden

Service ID: 1064305

Status: ⭕ Nicht abonniert

[✅ Abonnieren]
[◀️ Zurück] [🏠 Kategorien]
```

**Step 2 - Office Selection (NEW):**
```
Fahrzeug abmelden

📍 Bitte wählen Sie eine Behörde:
(96 verfügbar)

[📍 Sozialberatung]
[📍 Referat für Stadtplanung und Bauordnung]
[📍 KfZ Zulassungsstelle]  ← User clicks this
[📍 KfZ Zulassungsstelle]
...

⚠️ Nur die ersten 20 von 96 Behörden werden angezeigt.

[◀️ Zurück]
```

**Step 3 - Confirmation:**
```
✅ Abonniert!
```

## Viewing Current Subscriptions

Use `/myservices` to see all subscriptions with office IDs:

```
📋 Meine Abonnements:

📝 Fahrzeug abmelden
Service ID: 1064305
Abonniert: 2025-10-07
   📍 Office ID: 102101  ← Now visible!

...
```

## How to Fix Existing Subscriptions

If you have existing subscriptions with wrong offices:

1. Use `/myservices` to see your current subscriptions and office IDs
2. Unsubscribe from services with wrong offices (click 🗑)
3. Subscribe again using the new flow
4. Select the correct office this time

## For Your Case

Your subscriptions are currently:
- Service 1064305 (Fahrzeug abmelden): Office 10218 ❌

You should:
1. `/myservices` → Click 🗑 on "Fahrzeug abmelden"
2. `/subscribe` → Find "Fahrzeug abmelden" again
3. Select office like "KfZ Zulassungsstelle" (102101 or similar)
4. Appointments will now be detected!

## Technical Notes

- Offices are fetched from: `https://www48.muenchen.de/buergeransicht/api/citizen/offices-and-services/?serviceId=X`
- Currently shows max 20 offices (could add pagination later)
- Office selection is mandatory - no default selection
- Database schema unchanged - office_id field was already present
