# Munich Citizen Appointment API

Base URL: `https://www48.muenchen.de/buergeransicht/api/citizen`

Backend is it@M's open-source ZMS (`zmscitizenapi` in https://github.com/it-at-m/eappointment).
The route list with request/response docs lives in `zmscitizenapi/routing.php`; the reference client is
`zmscitizenview/src/api/ZMSAppointmentAPI.ts`. Verified against release `2.25.00-muc49`.

## Endpoints used by the bot

| Endpoint | Method | Purpose |
|---|---|---|
| `offices-and-services/` | GET | `{offices, services, relations}`. Service catalog and service→office mapping |
| `captcha-challenge/` | GET | ALTCHA proof-of-work challenge |
| `captcha-verify/` | POST | `{payload}` → `{meta.success, data.valid, token}` (JWT) |
| `available-calendar/` | GET | Bookable days plus time slots for one day |
| `reserve-appointment/` | POST | Hold a slot → `{processId, authKey, timestamp, scope, ...}` |
| `update-appointment/` | POST | Attach name/email/phone to the reserved process |
| `preconfirm-appointment/` | POST | Triggers the confirmation email |

`/services`, `available-days-by-office/` and `available-appointments-by-office/` no longer exist.

## Captcha (ALTCHA v2)

Challenge: `{"parameters": {algorithm, nonce, salt, cost, keyLength, keyPrefix, expiresAt, ...}, "signature"}`.

Find the smallest `counter` where
`key = HASH^cost(salt_bytes + nonce_bytes + uint32_be(counter))[:keyLength]` starts with `keyPrefix` (hex).
With `SHA-256`, `cost=1000` and `keyPrefix="00"`, that takes ~256 tries (tens of ms).

Verify body: `{"payload": base64(json({"challenge": {parameters, signature}, "solution": {counter, derivedKey, time}}))}`.

The token is only required for offices that have captcha enabled (e.g. Ausländerbehörde); without it,
those offices return `400 captchaMissing`.

## available-calendar

Query: `startDate`, `endDate`, `officeIds`, `serviceIds`, `serviceCounts` (CSV), `captchaToken`,
optional `slotsStartDate`/`slotsEndDate`.

```json
{
  "startDate": "2026-10-22", "endDate": "2027-04-22",
  "slotsStartDate": "2026-12-03", "slotsEndDate": "2026-12-03",
  "prevBookableDate": null, "nextBookableDate": null,
  "availableDays": [
    {"date": "2026-12-03", "providerIDs": "102523,102526",
     "offices": [{"officeId": "102523", "appointments": [1796292600]}]}
  ]
}
```

- No availability returns `200` with an empty `availableDays` list.
- The server fills `appointments` for a single day only: the first bookable day by default, or the day passed as
  `slotsStartDate = slotsEndDate`. Wider slot windows are narrowed to one day.
- `officeId` values are strings.

## Booking

- `reserve-appointment/`: `{timestamp, serviceCount: [1], officeId, serviceId: [id], captchaToken}`
- `update-appointment/`: server reads `processId, authKey, familyName, email, telephone, customTextfield, customTextfield2`
- `preconfirm-appointment/`: server reads `processId, authKey`

Additional fields are ignored by the server.
