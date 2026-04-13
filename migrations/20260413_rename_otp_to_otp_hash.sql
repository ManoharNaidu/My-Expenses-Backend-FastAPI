-- =============================================================================
-- Migration: Rename otp to otp_hash in verification tables
-- Applied: 2026-04-13
-- Ensures consistency between code and database schema.
-- =============================================================================

DO $$
BEGIN
    -- Rename column in email_verification if it exists
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'email_verification' AND column_name = 'otp'
    ) THEN
        ALTER TABLE public.email_verification RENAME COLUMN otp TO otp_hash;
    END IF;

    -- Rename column in password_reset if it exists
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'password_reset' AND column_name = 'otp'
    ) THEN
        ALTER TABLE public.password_reset RENAME COLUMN otp TO otp_hash;
    END IF;
END $$;
