// Client del Data API de Neon, fixat al schema `fcbillar` (només lectura via
// RLS). Les variables s'inlinen en build (Vite) → al .env.local en dev i a les
// env vars de Vercel en producció.
//
// El Data API de Neon exigeix un JWT a cada petició: no té equivalent de l'anon
// key de Supabase. `PUBLIC_NEON_ANON_TOKEN` fa el mateix paper —és una credencial
// pública que viatja al navegador— amb el claim `role: anon`, i qui la tingui
// només pot llegir el que les polítiques RLS li permetin. Es verifica contra el
// JWKS de static/.well-known/, i es revoca canviant-hi la clau.
//
// Sota el capó és el mateix postgrest-js que hi havia amb supabase-js, així que
// la sintaxi de les consultes no canvia.
import { NeonPostgrestClient } from "@neondatabase/postgrest-js";
import {
  PUBLIC_NEON_ANON_TOKEN,
  PUBLIC_NEON_DATA_API_URL,
} from "$env/static/public";

if (!PUBLIC_NEON_DATA_API_URL)
  throw new Error("Falta PUBLIC_NEON_DATA_API_URL");
if (!PUBLIC_NEON_ANON_TOKEN) throw new Error("Falta PUBLIC_NEON_ANON_TOKEN");

export const db = new NeonPostgrestClient({
  dataApiUrl: PUBLIC_NEON_DATA_API_URL,
  options: {
    db: { schema: "fcbillar" },
    global: {
      fetch,
      headers: { Authorization: `Bearer ${PUBLIC_NEON_ANON_TOKEN}` },
    },
  },
});

// Estat de l'última reingesta al núvol (taula fcbillar.cloud_status, una sola fila).
// L'escriu el workflow reingest.yml via `fcbillar state report`. El PWA la llegeix
// per avisar l'admin quan cal re-login al PC (session_ok=false).
export interface CloudStatus {
  session_ok: boolean;
  last_run: string | null;
  last_error: string | null;
  n_ok: number | null;
  n_fail: number | null;
  updated_at: string | null;
}

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
  player_fcb_id: string;
  jugador: string;
  club: string | null;
  mitjana_general: number | null;
  partides: number | null;
}

// Projecció del proper rànquing (taula fcbillar.ranking_provisional). Es publica
// quan hi ha partides de competicions en curs encara no al rànquing oficial.
export interface ProvisionalRow {
  player_fcb_id: string;
  posicio_oficial: number | null;
  mitjana_oficial: number | null;
  posicio_provisional: number | null;
  mitjana_provisional: number | null;
  partides_post: number;
  // Desglossament de la finestra projectada (només per als qui s'han mogut).
  proj_won?: number | null;
  proj_lost?: number | null;
  proj_tie?: number | null;
  window_game_ids?: string[] | null; // IDs de `games` de la finestra PROJECTADA
  current_game_ids?: string[] | null; // IDs de `games` del rànquing OFICIAL vigent
}

// Partides jugades en competicions en curs encara NO al rànquing oficial
// (taula fcbillar.pending_games). Una fila per jugador i partida.
export interface PendingGameRow {
  modalitat_codi: number;
  competicio: string | null;
  font: string;
  opponent_nom: string | null;
  caramboles: number | null;
  caramboles_opp: number | null;
  entrades: number | null;
  serie: number | null;
}

export interface GameRow {
  id: string;
  data_partida: string | null;
  modalitat_codi: number | null;
  competicio: string | null;
  player1_fcb_id: string | null;
  player1_nom: string | null;
  caramboles1: number | null;
  serie_max1: number | null;
  player2_fcb_id: string | null;
  player2_nom: string | null;
  caramboles2: number | null;
  serie_max2: number | null;
  entrades: number | null;
  guanyador_fcb_id: string | null;
}

export interface LligaGroup {
  lliga_id: number;
  divisio_id: number;
  grup_id: number;
  divisio_nom: string | null;
  grup_nom: string | null;
}
export interface StandingRow {
  /** Quina edició de la lliga: identifica la temporada, que les dades no diuen. */
  lliga_id: number;
  divisio_id: number;
  grup_id: number;
  posicio: number | null;
  equip: string;
  club_fcb_id: string | null;
  pj: number | null;
  g: number | null;
  e: number | null;
  p: number | null;
  punts: number | null;
  pf: number | null;
  pc: number | null;
  /** Punts restats per sanció federativa (> 0). null = sense sanció. */
  penalitzacio?: number | null;
}

export interface CopaGroup {
  edicio_id: number;
  jornada: number;
  grup_id: number;
  grup_nom: string | null;
  jornada_nom: string | null;
  ordre: number | null;
}
export interface CopaStanding {
  edicio_id: number;
  jornada: number;
  grup_id: number;
  posicio: number | null;
  equip: string;
  punts: number | null;
  parcials: number | null;
  mitjana: number | null;
}

export interface PlayerRankRow {
  divisio_id?: number;
  jornada?: number;
  grup_id: number;
  posicio: number | null;
  player_fcb_id: string;
  jugador: string | null;
  club: string | null;
  /**
   * El mateix identificador que porta la classificació, que és el que hi lliga.
   * `club` és el NOM i no serveix per creuar-les: no sempre coincideixen, i a
   * més el nom pot canviar quan s'unifiquen dues fitxes del mateix club.
   */
  club_fcb_id?: string | null;
  partides: number | null;
  punts: number | null;
  mitjana: number | null;
}

/**
 * Un jugador inscrit per un club a una lliga, tal com ho publica la federació.
 *
 * És la font OFICIAL de qui juga la lliga amb qui, i l'ordre (`posicio`) és el
 * que la federació fixa per a tota la temporada: és el mateix que decideix a
 * quins equips del club pot jugar cadascú.
 */
export interface LligaInscrit {
  temporada: string;
  lliga_id: number;
  modalitat: string;
  club: string;
  /** El que lliga amb la classificació. El nom no serveix per creuar-les. */
  club_fcb_id: string | null;
  jugador: string;
  mitjana: number | null;
  /** Ve d'un altre club: la federació el llista als dos mentre no ho corregeixi. */
  fitxatge: boolean;
  posicio: number;
}

export interface Open {
  open_id: number;
  nom: string;
  tipus: "open" | "campionat" | null;
  temporada_id: number | null;
  temporada?: string | null;
}

// Classificació de tipus de torneig coherent entre temporades (mirall de
// fcbillar.torneig_naming.torneig_tipus). Trofeu amb nom propi → 'open'; només
// modalitat+divisió o CAMPIONAT/CATALUNYA → 'campionat'. Independent de si el nom
// porta literalment 'OPEN' (arregla Memorial Jaume Arnau, etc.). S'usa com a
// fallback quan el camp `tipus` publicat encara és null.
const OPEN_MARKERS = [
  "OPEN",
  "MEMORIAL",
  "TROFEU",
  "CIUTAT",
  "GRAN PREMI",
  "CRITERIUM",
];
export function torneigTipus(nom: string): "open" | "campionat" {
  const u = nom
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toUpperCase();
  if (u.includes("CAMPIONAT") || u.includes("CATALUNYA")) return "campionat";
  if (OPEN_MARKERS.some((m) => u.includes(m))) return "open";
  return "campionat";
}
export const tipusOf = (o: Open): "open" | "campionat" =>
  o.tipus ?? torneigTipus(o.nom);
// ---------------------------------------------------------------------------
// Opens EN DIRECTE (taula fcbillar.open_live, una fila per Open en curs).
// `payload_json` és l'estat complet raspat de la federació (mateixa forma que
// LiveOpenResponse del backend). El publisher és `fcbillar publish-live-opens`.
// ---------------------------------------------------------------------------
export interface OpenLiveStanding {
  player_name: string;
  club: string;
  punts: number;
  mitjana: number;
  pj?: number;
  caramboles?: number;
  entrades?: number;
  // Jugador que ENTRA al grup com a classificat segur d'una ronda inferior que la
  // FCB encara no hi ha col·locat oficialment. `seed_rank` = la seva posició al
  // rànquing de classificats (1 = millor, per punts→mitjana→SM); `from_group` = el
  // grup d'on ve. Vegeu cloud_sync._enrich_real_groups_with_projection.
  incoming?: boolean;
  seed_rank?: number;
  from_group?: string;
}
export interface OpenLiveMatch {
  player_a: string;
  player_b: string;
  punts_a: number;
  punts_b: number;
  caramboles_a: number;
  caramboles_b: number;
  serie_major_a: number;
  serie_major_b: number;
  entrades: number | null;
  arbitre: string | null;
  observations?: string | null;
  is_played: boolean;
}

/** Incompareixença (W.O.): la FCB la publica amb els punts del guanyador (2-0)
 *  i tota la resta a zero. `is_played` és false —no hi ha entrades— però el
 *  resultat és ferm i el guanyador passa de ronda. */
export function isWalkover(m: OpenLiveMatch): boolean {
  return (
    !m.is_played &&
    m.punts_a !== m.punts_b &&
    m.caramboles_a === 0 &&
    m.caramboles_b === 0
  );
}

/** Partida amb resultat ferm: jugada o guanyada per incompareixença. Comptar
 *  només `is_played` deixava una ronda amb W.O. eternament "en joc" i l'open
 *  encallat a aquella fase encara que ja s'hagués acabat. */
export function isDecided(m: OpenLiveMatch): boolean {
  return m.is_played || isWalkover(m);
}
// Horari projectat d'un grup (del PDF oficial d'HORARIS): dia, billar (taula) i
// l'hora de cada partida en ordre de joc (2-3 = 2n vs 3r, 1-P = 1r vs perdedor,
// 1-G = 1r vs guanyador). Present només als opens projectats amb horaris.
export interface OpenLiveGroupSchedule {
  date: string | null; // ISO YYYY-MM-DD
  billar: number | null;
  matches: { type: "2-3" | "1-P" | "1-G" | string; time: string }[];
}
export interface OpenLiveGroup {
  label: string;
  url: string;
  venue: string | null;
  schedule?: OpenLiveGroupSchedule | null;
  standings: OpenLiveStanding[];
  matches: OpenLiveMatch[];
  n_matches_played: number;
  n_matches_total: number;
}
export interface OpenLiveProvQual {
  group_label: string;
  position_in_group: number;
  player_name: string;
  club: string;
  punts: number;
  mitjana: number;
  serie_major: number;
  pj?: number;
  caramboles?: number;
  entrades?: number;
}
export interface OpenLivePhase {
  label: string;
  kind: "group" | "ko";
  url: string;
  groups: OpenLiveGroup[];
  ko_matches: OpenLiveMatch[];
  is_active: boolean;
  provisional_qualifiers: OpenLiveProvQual[];
  provisional_matches: OpenLiveMatch[];
  provisional_players: {
    name: string;
    club: string;
    mitjana: number;
    serie_major: number;
    source: string;
  }[];
  // Fase PROJECTADA dins un open real: la federació té el sorteig fet (grups del
  // PDF oficial) però encara no l'ha publicat al web en directe. Les altres fases
  // del mateix open són reals. Vegeu cloud_sync._merge_projected_phases.
  projected?: boolean;
}
export interface OpenLiveClassRow {
  position: number;
  player_name: string;
  club: string;
  round_label: string;
  mitjana: number; // mitjana de TOT l'open (caramboles/entrades de totes les partides)
  serie_major: number; // millor sèrie de tot l'open
  partides?: number; // PJ · absents als snapshots anteriors al 2026-07-27
  caramboles?: number;
  entrades?: number;
  open_points: number;
  is_provisional_position: boolean;
  rank3b?: number; // posició al rànquing de 3 bandes (per mostrar entre parèntesi)
  prize?: string; // premi especial per banda de rànquing ("Millor 61-180" / "Millor 181+")
}
export interface OpenLivePayload {
  division_id: number;
  name: string;
  phase_id: number | null;
  phases: OpenLivePhase[];
  classification: OpenLiveClassRow[];
  classification_is_provisional: boolean;
  fetched_at: string;
  player_ids?: Record<string, string>;
  // num_seq del rànquing 3B amb què s'han calculat rank3b/prize (el de la
  // convocatòria si està fixat; si no, el darrer). El selector hi ancora el valor per defecte.
  prize_num_seq?: number;
  // Open PROJECTAT (generat des del rànquing inicial abans del sorteig oficial
  // FCB, via `fcbillar project-open-ranking`). El web el mostra com un open en
  // curs però amb badge 'projecció · no oficial'. num_inscriptions/structure
  // són context (p.ex. {P:16, PP:16, PPP:1}).
  projected?: boolean;
  num_inscriptions?: number;
  structure?: Record<string, number>;
}
export interface OpenLiveRow {
  fcb_division_id: number;
  name: string;
  modality: string | null;
  payload_json: OpenLivePayload;
  captured_at: string;
  updated_at: string;
}

// Marcador EN VIU d'una partida (OCR de la retransmissió de YouTube).
// Taula fcbillar.open_live_scores; el publica el worker de Multiview.
export interface OpenLiveScore {
  video_id: string;
  fcb_division_id: number;
  club: string | null;
  title: string | null;
  phase: string | null;
  group_label: string | null;
  player_a: string | null;
  player_b: string | null;
  car_a: number | null;
  car_b: number | null;
  entrades: number | null;
  finished: boolean | null;
  captured_at: string;
}

export interface OpenClassification {
  open_id: number;
  posicio: number | null;
  player_fcb_id: string | null;
  jugador: string | null;
  club: string | null;
  partides: number | null;
  punts: number | null;
  caramboles: number | null;
  entrades: number | null;
  mitjana_general: number | null;
  mitjana_particular: number | null;
  serie_max: number | null;
}

// Calendari esportiu federatiu (taules fcbillar.calendari_*). Dues fonts, totes
// dues parsejades per `fcbillar.calendari_fed`: el PDF de la RFEB (competicions
// estatals i internacionals) i el de la FCB, del qual només se n'agafa la meitat
// catalana perquè la resta és una còpia del de la RFEB. Cap dels dos no concreta
// el dia: `setmana` és el dilluns i data_inici/data_fi el rang que la cel·la ocupa.
export interface CalendariEvent {
  font: string; // 'RFEB' | 'FCB'
  temporada: string; // '2026/2027'
  setmana: string; // ISO, dilluns
  disciplina: string; // carambola | pool | snooker
  ambit: string; // catala | nacional | internacional | mixt | tot
  grup: string; // 'Tres bandes' | 'Campionats de Catalunya' | …
  tipus: string; // equips | individual | ''
  data_inici: string;
  data_fi: string;
  titol: string;
  seu: string | null;
  dissabte: string | null; // què es juga el ds (patró LIGA NACIONAL)
  diumenge: string | null;
  col_span: number; // >1 = cel·la fusionada al PDF (Nadal, Setmana Santa)
}

export interface CalendariRevisio {
  font: string;
  temporada: string;
  sha256: string;
  versio: string | null;
  data_versio: string | null;
  url: string | null;
  n_events: number;
  n_canvis: number;
  ingested_at: string | null;
  last_checked_at: string | null;
}

export interface CalendariCanvi {
  font: string;
  temporada: string;
  sha256: string;
  ord: number;
  tipus_canvi: string; // alta | baixa | modificacio
  setmana: string;
  disciplina: string;
  ambit: string;
  grup: string | null;
  tipus: string | null;
  abans: string | null;
  despres: string | null;
}
