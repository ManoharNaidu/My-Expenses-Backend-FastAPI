-- =============================================================================
-- Security hardening migration
-- Applied: 2026-03-16
-- =============================================================================

-- 1. JWT revocation support
--    Bump token_version on a user to invalidate all their issued tokens.
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;

-- 2. OTP hashed storage
--    OTPs are now stored as SHA-256 hex digests (64 chars).
--    Existing plaintext OTPs are invalidated by marking them used.
ALTER TABLE public.email_verification
  ALTER COLUMN otp TYPE TEXT,
  ALTER COLUMN otp SET NOT NULL;

ALTER TABLE public.password_reset
  ALTER COLUMN otp TYPE TEXT,
  ALTER COLUMN otp SET NOT NULL;

UPDATE public.email_verification SET used = TRUE WHERE used = FALSE;
UPDATE public.password_reset      SET used = TRUE WHERE used = FALSE;
