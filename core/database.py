from core.config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_ROLE_KEY
from supabase import create_client

# Regular client (using anon key)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Admin client (using service role key) - BE CAREFUL with this, it bypasses RLS!
supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
