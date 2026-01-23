-- Clean up any stray challenge_registrations rows with NULL challenge_id
DELETE FROM challenge_registrations WHERE challenge_id IS NULL;

-- Ensure the foreign key from challenge_registrations.challenge_id to challenges.id
-- uses ON DELETE CASCADE so deleting a Challenge cascades to its registrations
ALTER TABLE challenge_registrations
  DROP CONSTRAINT IF EXISTS challenge_registrations_challenge_id_fkey;
ALTER TABLE challenge_registrations
  ADD CONSTRAINT challenge_registrations_challenge_id_fkey
  FOREIGN KEY (challenge_id) REFERENCES challenges(id) ON DELETE CASCADE;
