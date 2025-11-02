#!/usr/bin/env bash
set -euo pipefail
BASE="https://careflow-ntg3.onrender.com"
KEY="d68c16251f764a91d9b71c67ebaa242b0233202bbaf8fac1a3a4192223690456"

echo "Health:"
curl -fsS "$BASE/health" -H "x-api-key: $KEY" && echo

TODAY=${1:-"2025-11-03"}
echo "List slots for $TODAY:"
SLOTS_JSON=$(curl -fsS "$BASE/slots?date=$TODAY" -H "x-api-key: $KEY")
echo "$SLOTS_JSON"

# pick first slot
START=$(echo "$SLOTS_JSON" | sed -n 's/.*"start":"\([^"]*\)".*/\1/p' | head -n1)
END=$(echo "$SLOTS_JSON"   | sed -n 's/.*"end":"\([^"]*\)".*/\1/p'     | head -n1)
PROVIDER=$(echo "$SLOTS_JSON" | sed -n 's/.*"provider":"\([^"]*\)".*/\1/p' | head -n1)

if [ -z "${START:-}" ] || [ -z "${END:-}" ] || [ -z "${PROVIDER:-}" ]; then
  echo "No slots available for $TODAY"; exit 0
fi

echo "Booking $PROVIDER $START - $END"
BOOK_JSON=$(curl -fsS "$BASE/book" \
  -H "content-type: application/json" \
  -H "x-api-key: $KEY" \
  -d "{\"patient_ref\":\"pat-123\",\"start\":\"$START\",\"end\":\"$END\",\"provider\":\"$PROVIDER\",\"visit_type\":\"screening\"}")
echo "$BOOK_JSON"

BOOKING_ID=$(echo "$BOOK_JSON" | sed -n 's/.*"booking_id":"\([^"]*\)".*/\1/p')
if [ -z "${BOOKING_ID:-}" ]; then
  echo "Booking failed (maybe race)"; exit 1
fi

# reschedule to the next matching hour block if present
NEW_START=$(echo "$SLOTS_JSON" | sed -n 's/.*"start":"\([^"]*\)".*/\1/p' | sed -n '2p')
NEW_END=$(echo "$SLOTS_JSON"   | sed -n 's/.*"end":"\([^"]*\)".*/\1/p'   | sed -n '2p')
if [ -n "${NEW_START:-}" ] && [ -n "${NEW_END:-}" ]; then
  echo "Rescheduling $BOOKING_ID -> $NEW_START - $NEW_END"
  curl -fsS "$BASE/reschedule" \
    -H "content-type: application/json" \
    -H "x-api-key: $KEY" \
    -d "{\"booking_id\":\"$BOOKING_ID\",\"new_start\":\"$NEW_START\",\"new_end\":\"$NEW_END\"}" && echo
fi

echo "Cancel $BOOKING_ID"
curl -fsS "$BASE/cancel" \
  -H "content-type: application/json" \
  -H "x-api-key: $KEY" \
  -d "{\"booking_id\":\"$BOOKING_ID\",\"reason\":\"demo complete\"}" && echo
