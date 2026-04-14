-- Stores per-user weekly report email preferences and send guard state.

CREATE TABLE IF NOT EXISTS public.weekly_digest_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    weekday SMALLINT NOT NULL DEFAULT 0,
    hour SMALLINT NOT NULL DEFAULT 18,
    minute SMALLINT NOT NULL DEFAULT 0,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    last_sent_week TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT weekly_digest_settings_user_unique UNIQUE (user_id),
    CONSTRAINT weekly_digest_weekday_range CHECK (weekday >= 0 AND weekday <= 6),
    CONSTRAINT weekly_digest_hour_range CHECK (hour >= 0 AND hour <= 23),
    CONSTRAINT weekly_digest_minute_range CHECK (minute >= 0 AND minute <= 59)
);

CREATE INDEX IF NOT EXISTS idx_weekly_digest_enabled
    ON public.weekly_digest_settings (enabled);
