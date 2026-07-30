/**
 * Configuració d'accés a l'API pública de billiard-bible.com.
 *
 * La clau anon és la clau pública de Supabase que la seva pròpia web
 * incrusta al client (és de només lectura, protegida per RLS al seu costat).
 * Aquesta app només consulta dades; no en modifica cap.
 */

export const BB_URL = 'https://szaxmylzfarikbqdufcm.supabase.co';

export const BB_ANON_KEY =
	'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN6YXhteWx6ZmFyaWticWR1ZmNtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MDQ3NjQ5MDMsImV4cCI6MjAyMDM0MDkwM30.M-c-6X0GC5_miNgQJvXsmH6shqmeZwd2jrnTtYCQ6g0';

/** Id màxim per fixar la instantània de paginació (frozen snapshot). */
export const BB_MAX_ID = 2_000_000_000;
