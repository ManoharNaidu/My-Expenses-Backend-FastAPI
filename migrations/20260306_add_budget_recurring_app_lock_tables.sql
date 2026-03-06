-- Creates missing tables required by:
-- 1) Budget Goal feature
-- 2) Recurring Transactions feature
-- 3) App Lock feature

-- ------------------------------
-- budget_goals
-- ------------------------------
CREATE TABLE IF NOT EXISTS public.budget_goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    monthly_limit NUMERIC(14, 2) NOT NULL DEFAULT 0,
    alerts_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT budget_goals_user_unique UNIQUE (user_id)
);

-- ------------------------------
-- recurring_transactions
-- ------------------------------
CREATE TABLE IF NOT EXISTS public.recurring_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    amount NUMERIC(14, 2) NOT NULL,
    type TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    start_date DATE NOT NULL,
    day_of_month INTEGER NOT NULL CHECK (day_of_month >= 1 AND day_of_month <= 28),
    end_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------
-- app_locks
-- ------------------------------
CREATE TABLE IF NOT EXISTS public.app_locks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    use_biometric BOOLEAN NOT NULL DEFAULT FALSE,
    pin_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT app_locks_user_unique UNIQUE (user_id)
);

CREATE INDEX IF NOT EXISTS idx_budget_goals_user_id
    ON public.budget_goals (user_id);

CREATE INDEX IF NOT EXISTS idx_recurring_transactions_user_id
    ON public.recurring_transactions (user_id);

CREATE INDEX IF NOT EXISTS idx_recurring_transactions_user_active
    ON public.recurring_transactions (user_id, is_active);

CREATE INDEX IF NOT EXISTS idx_app_locks_user_id
    ON public.app_locks (user_id);
