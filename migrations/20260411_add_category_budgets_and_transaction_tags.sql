-- Adds category-level budgets and transaction tags support

ALTER TABLE IF EXISTS public.transactions
ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE IF EXISTS public.users
ADD COLUMN IF NOT EXISTS persona TEXT;

CREATE TABLE IF NOT EXISTS public.category_budgets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    monthly_limit NUMERIC(14, 2) NOT NULL DEFAULT 0,
    alerts_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT category_budgets_user_category_unique UNIQUE (user_id, category)
);

CREATE INDEX IF NOT EXISTS idx_category_budgets_user_id
    ON public.category_budgets (user_id);
