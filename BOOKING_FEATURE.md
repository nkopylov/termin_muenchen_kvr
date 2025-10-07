# Appointment Booking Feature

## Overview
Added automated appointment booking functionality directly through the Telegram bot.

## How It Works

### 1. User Flow
When appointments are found:
1. Bot sends notification with available dates
2. User clicks on "📅 Buchen: [DATE]" button for their preferred date
3. Bot shows available time slots for that date
4. User selects a time slot
5. User enters their full name
6. User enters their email address
7. User confirms the booking
8. Bot automatically books the appointment through the Munich API
9. User receives confirmation and must click the link in their email to finalize

### 2. Technical Implementation

#### Files Added:
- `booking_api.py` - API functions for the 3-step booking process
  - `reserve_appointment()` - Reserve a slot
  - `update_appointment()` - Add user information
  - `preconfirm_appointment()` - Finalize booking (requires email confirmation)
  - `book_appointment_complete()` - Complete flow wrapper

- `booking_handler.py` - Telegram conversation handler
  - Manages multi-step conversation flow
  - Collects user information
  - Handles errors and cancellations
  - Conversation states: SELECTING_TIME → ASKING_NAME → ASKING_EMAIL → CONFIRMING

#### Files Modified:
- `telegram_bot.py`
  - Added inline keyboard buttons to notifications
  - Registered booking conversation handler
  - Store captcha token in bot_data for booking flow

### 3. Booking Process (API)

The Munich appointment system uses a 3-step process:

**Step 1: Reserve**
```
POST /api/citizen/reserve-appointment/
{
  "timestamp": 1760455200,
  "serviceCount": [1],
  "officeId": 10461,
  "serviceId": [10339028],
  "captchaToken": "..."
}
→ Returns: processId, authKey, timestamp, scope
```

**Step 2: Update**
```
POST /api/citizen/update-appointment/
{
  "processId": ...,
  "authKey": ...,
  "familyName": "User Name",
  "email": "user@example.com",
  ...
}
```

**Step 3: Preconfirm**
```
POST /api/citizen/preconfirm-appointment/
{
  "processId": ...,
  "authKey": ...,
  "familyName": "User Name",
  "email": "user@example.com",
  "status": "preconfirmed",
  ...
}
→ Sends confirmation email to user
```

### 4. User Experience

**Notification with Booking Buttons:**
```
🎉 TERMIN VERFÜGBAR! 🎉

Notfalltermin Ausländerbehörde

Verfügbare Termine:
📅 2025-10-13
  🕐 09:00, 09:15, 09:30, 10:00, 10:15
...

[📅 Buchen: 2025-10-13]
[📅 Buchen: 2025-10-14]
...
[🔗 Manuell auf Website buchen]
```

**Booking Conversation:**
```
1. User clicks "📅 Buchen: 2025-10-13"
   → Bot shows: "Available time slots: [09:00] [09:15] [09:30]..."

2. User clicks "🕐 09:00"
   → Bot asks: "Please enter your full name:"

3. User types: "Max Mustermann"
   → Bot asks: "Please enter your email address:"

4. User types: "max@example.com"
   → Bot shows confirmation with [✅ Confirm Booking] button

5. User clicks "✅ Confirm Booking"
   → Bot books appointment and shows success message
```

**Success Message:**
```
🎉 Booking Successful! 🎉

📋 Booking ID: 180871
🕐 Time: 09:00 on Monday, October 13, 2025
👤 Name: Max Mustermann
📧 Email: max@example.com

⚠️ IMPORTANT - Next Steps:

1. Check your email inbox at max@example.com
2. Look for a confirmation email from Munich Ausländerbehörde
3. Click the confirmation link in that email
4. Your appointment will only be finalized after email confirmation
```

### 5. Error Handling

- **Slot taken**: If someone else books the slot during the process, user is notified
- **Captcha expired**: User is asked to start over from the notification
- **API errors**: User receives clear error message
- **Cancellation**: User can cancel at any point by clicking "❌ Cancel" or sending any command

### 6. Security & Validation

- Email format validation
- Name length validation
- Captcha token expiry handling (5 minutes)
- All API communication uses HTTPS
- No sensitive data stored in database

### 7. Limitations

- User must confirm appointment via email (Munich system requirement)
- Captcha token expires after 5 minutes
- No phone number or custom fields (not required for this service)
- Booking only works for Ausländerbehörde emergency appointments

## Testing

To test the booking feature:
1. Wait for appointment notification
2. Click on a booking button
3. Follow the conversation flow
4. Check that all steps complete successfully
5. Verify confirmation email is received

## Future Improvements

- Add booking history to database
- Allow users to save their details for faster booking
- Support multiple appointment types
- Add booking notifications to admin
- Implement retry logic for failed bookings
