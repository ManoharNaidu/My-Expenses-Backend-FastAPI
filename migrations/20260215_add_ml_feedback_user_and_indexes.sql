-- Ensure ml_feedback can be tied to each authenticated user.
ALTER TABLE public.ml_feedback
ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES public.users(id) ON DELETE CASCADE;

-- Useful metadata for retraining pipelines and diagnostics.
ALTER TABLE public.ml_feedback
ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

-- Performance indexes for per-user training lookups.
CREATE INDEX IF NOT EXISTS idx_ml_feedback_user_id ON public.ml_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_ml_feedback_user_created_at ON public.ml_feedback(user_id, created_at DESC);

-- Helpful index for repeated training reads from confirmed transactions.
CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON public.transactions(user_id, date DESC);
