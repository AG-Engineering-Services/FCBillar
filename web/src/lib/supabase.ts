// Client Supabase fixat al schema `fcbillar` (només lectura via anon + RLS).
// Les variables s'inlinen en build (Vite) → al .env.local en dev i a les env
// vars de Vercel en producció.
import { createClient } from '@supabase/supabase-js';
import { PUBLIC_SUPABASE_ANON_KEY, PUBLIC_SUPABASE_URL } from '$env/static/public';

if (!PUBLIC_SUPABASE_URL) throw new Error('Falta PUBLIC_SUPABASE_URL');
if (!PUBLIC_SUPABASE_ANON_KEY) throw new Error('Falta PUBLIC_SUPABASE_ANON_KEY');

export const supabase = createClient(PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY, {
	db: { schema: 'fcbillar' },
	auth: { persistSession: false }
});

export interface Modalitat {
	codi_fcb: number;
	nom: string;
}
export interface Snapshot {
	num_seq: number;
	any_pub: number | null;
	mes_pub: number | null;
}
export interface RankingRow {
	posicio: number | null;
	jugador: string;
	club: string | null;
	mitjana_general: number | null;
	partides: number | null;
}
