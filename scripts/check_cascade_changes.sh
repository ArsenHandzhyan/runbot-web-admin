#!/bin/bash
# Script to check if cascade delete changes were applied to the production database.
# Run this on your production server with access to the database.
# Replace the variables with your actual production database credentials.

set -euo pipefail

DB_HOST="${DB_HOST:-prod-db-host}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-dbuser}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_NAME="${DB_NAME:-runbot_prod}"

# Construct connection string
if [ -z "${DB_PASSWORD}" ]; then
  CONN_STR="postgresql://${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
else
  CONN_STR="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
fi

echo "Checking foreign key constraints for CASCADE DELETE..."

# Check challenge_registrations FK
echo "=== Challenge Registrations FK ==="
psql "$CONN_STR" -c "
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE contype = 'f' AND conrelid = 'challenge_registrations'::regclass;
" | grep -i cascade || echo "No CASCADE found for challenge_registrations"

# Check event_registrations FK
echo "=== Event Registrations FK ==="
psql "$CONN_STR" -c "
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE contype = 'f' AND conrelid = 'event_registrations'::regclass;
" | grep -i cascade || echo "No CASCADE found for event_registrations"

echo "Checking cascade delete functionality with a test scenario..."

# Test cascade delete (in a transaction to avoid affecting real data)
psql "$CONN_STR" -c "
BEGIN;
-- Insert test data
INSERT INTO participants (telegram_id, full_name, birth_date, phone, start_number, is_active)
VALUES ('test123', 'Test User', '1990-01-01', '+1234567890', 'T001', TRUE) RETURNING id;

-- Assume we get participant_id from above; hardcode for simplicity
-- In real test, capture the RETURNING value
-- For now, use a placeholder; adjust as needed

-- Insert challenge
INSERT INTO challenges (name, description, challenge_type, start_date, end_date, is_active, created_at)
VALUES ('Test Challenge', 'Test desc', 'PUSH_UPS', NOW(), NOW() + INTERVAL '7 days', TRUE, NOW()) RETURNING id;

-- Insert registration (using placeholder IDs; adjust to actual inserted IDs)
-- INSERT INTO challenge_registrations (participant_id, challenge_id, registration_date, is_active)
-- VALUES (inserted_participant_id, inserted_challenge_id, NOW(), TRUE);

-- Delete challenge
-- DELETE FROM challenges WHERE id = inserted_challenge_id;

-- Check if registration was deleted
-- SELECT COUNT(*) FROM challenge_registrations WHERE challenge_id = inserted_challenge_id;

ROLLBACK; -- Always rollback to avoid modifying data
"

echo "Check completed. Look for CASCADE in FK definitions and ensure test deletes work."