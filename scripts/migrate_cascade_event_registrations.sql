-- Cleanup stray event_registrations with NULL event_id (if any)
DELETE FROM event_registrations WHERE event_id IS NULL;

-- Ensure ON DELETE CASCADE for event_id FK
DROP CONSTRAINT IF EXISTS event_registrations_event_id_fkey;
ALTER TABLE event_registrations
  ADD CONSTRAINT event_registrations_event_id_fkey
  FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE;
