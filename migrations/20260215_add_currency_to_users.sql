-- Adds user currency preference and keeps existing rows valid.
ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS currency TEXT;

-- Optional backfill to avoid NULL for existing users.
UPDATE public.users
SET currency = 'AUD'
WHERE currency IS NULL;
