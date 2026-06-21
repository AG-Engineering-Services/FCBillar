// TypeScript types mirroring src/fcb_opens/api/schemas.py.
// Keep in sync with the backend schemas when they change.

export interface HealthResponse {
	status: string;
	version: string;
}

export interface StatsResponse {
	monthly_rankings: number;
	opens: number;
	players: number;
	latest_month_id: number | null;
	latest_open_name: string | null;
}

export interface MonthlyRankingSummary {
	month_id: number;
	fetched_at: string;
	entry_count: number;
}

export interface MonthlyRankingRow {
	position: number;
	player_id: number;
	player_name: string;
	current_club: string | null;
	average: number;
	matches_scored: number;
	matches_max: number;
	is_definitive: boolean;
}

export interface MonthlyRankingDetail {
	month_id: number;
	fetched_at: string;
	entries: MonthlyRankingRow[];
}

export interface OpensRankingRow {
	rank: number;
	player_id: number;
	display_name: string;
	club: string | null;
	total_points: number;
	max_single_open: number;
	opens_played: number;
	breakdown: OpenBreakdown[];
}

export interface OpenBreakdown {
	open_id: number;
	fcb_division_id: number;
	name: string;
	season: string;
	points: number | null;
}

export interface OpensRankingResponse {
	window_size: number;
	opens_in_window: number;
	entries: OpensRankingRow[];
}

export interface OpenSummary {
	id: number;
	fcb_division_id: number;
	fcb_classification_id: number | null;
	name: string;
	season: string;
	player_count: number;
}

export interface OpenClassificationRow {
	position: number;
	player_id: number;
	player_name: string;
	club: string | null;
	matches_played: number;
	match_points: number;
	caramboles: number;
	entries: number;
	general_average: number;
	particular_average: number;
	best_series: number;
	open_points: number;
}

export interface OpenDetail {
	id: number;
	fcb_division_id: number;
	fcb_classification_id: number | null;
	name: string;
	season: string;
	classification: OpenClassificationRow[];
}

export interface PlayerOpenResult {
	open_id: number;
	open_name: string;
	position: number;
	general_average: number;
	open_points: number;
}

export type ClubSource = 'manual' | 'opens' | 'lliga' | 'opens_old' | 'none';

export interface PlayerClubSources {
	opens_club: string | null;
	opens_old_club: string | null;
	lliga_club: string | null;
	manual_club: string | null;
	resolved_club: string | null;
	source: ClubSource;
}

export interface PlayerRankingHistoryEntry {
	month_id: number;
	fetched_at: string;
	position: number;
	average: number;
	matches_scored: number;
	matches_max: number;
	is_definitive: boolean;
	club: string | null;
}

export interface PlayerProfile {
	id: number;
	display_name: string;
	normalized_name: string;
	current_club: string | null;
	club_sources: PlayerClubSources;
	latest_monthly_ranking: MonthlyRankingRow | null;
	total_opens_points: number;
	opens_history: PlayerOpenResult[];
	ranking_history: PlayerRankingHistoryEntry[];
}

export interface PlayerListEntry {
	id: number;
	display_name: string;
	normalized_name: string;
	club_sources: PlayerClubSources;
	opens_played: number;
	lliga_partides: number;
}

export interface SetManualClubRequest {
	manual_club: string | null;
}

export interface ClubOption {
	name: string;
	sources: string[]; // any of 'opens' | 'lliga' | 'monthly_ranking' | 'manual' | 'players_current'
	occurrences: number;
}

export interface InscriptionInput {
	player_name: string;
	club?: string;
	opens_points?: number | null;
	fcb_ranking_position?: number | null;
	fcb_ranking_is_definitive?: boolean | null;
	fcb_ranking_average?: number | null;
}

export interface EnrichedInscription {
	player_name: string;
	club: string;
	opens_points: number;
	fcb_ranking_position: number | null;
	fcb_ranking_is_definitive: boolean;
	fcb_ranking_average: number;
	matched: boolean;
}

export interface GroupSlotResponse {
	label: string;
	inscription_position: number | null;
	placeholder_rank: number | null;
	placeholder_phase: string | null;
	player_name: string | null;
	club: string | null;
}

export interface GroupResponse {
	label: string;
	slots: GroupSlotResponse[];
}

export interface PhaseResponse {
	name: string;
	groups: GroupResponse[];
}

export interface TournamentResponse {
	num_inscriptions: number;
	phases: Record<string, PhaseResponse>;
}

export interface AnomalyResponse {
	code: string;
	severity: 'error' | 'warning' | 'info';
	message: string;
	affected_players: string[];
}

export interface GeneratorRequest {
	inscriptions: InscriptionInput[];
	auto_enrich: boolean;
	month_id?: number | null;
}

export interface GeneratorResponse {
	enriched_inscriptions: EnrichedInscription[];
	ordered_inscriptions: EnrichedInscription[];
	unmatched: string[];
	tournament: TournamentResponse | null;
	anomalies: AnomalyResponse[];
}

export interface ValidatorRequest {
	inscriptions: InscriptionInput[];
	auto_enrich: boolean;
	month_id?: number | null;
}

export interface ValidatorResponse {
	enriched_inscriptions: EnrichedInscription[];
	unmatched: string[];
	anomalies: AnomalyResponse[];
}

// --- Live open state ---

export interface LiveStanding {
	player_name: string;
	club: string;
	punts: number;
	mitjana: number;
}

export interface LiveMatch {
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
	is_played: boolean;
}

export interface LiveGroup {
	label: string;
	url: string;
	venue: string | null;
	standings: LiveStanding[];
	matches: LiveMatch[];
	n_matches_played: number;
	n_matches_total: number;
}

export interface ProvisionalQualifier {
	group_label: string;
	position_in_group: number;
	player_name: string;
	club: string;
	punts: number;
	mitjana: number;
	serie_major: number;
}

export interface LivePhase {
	label: string;
	kind: 'group' | 'ko';
	url: string;
	groups: LiveGroup[];
	ko_matches: LiveMatch[];
	is_active: boolean;
	provisional_qualifiers: ProvisionalQualifier[];
	provisional_matches: LiveMatch[];
}

export interface LiveOpenResponse {
	division_id: number;
	name: string;
	phase_id: number | null;
	phases: LivePhase[];
	fetched_at: string;
}

export interface LiveIndexEntry {
	division_id: number;
	name: string;
	index: number;
}

export interface LiveSnapshotSummary {
	id: number;
	captured_at: string;
}

export interface RankingBandEntry {
	player_name: string;
	club: string;
	fcb_position: number | null;
	fcb_is_definitive: boolean;
	phase_label: string;
	group_label: string;
	punts: number;
	mitjana: number;
}

export interface RankingBandResponse {
	division_id: number;
	open_name: string;
	month_id: number;
	month_is_saved: boolean;
	fetched_at: string;
	band_61_180: RankingBandEntry[];
	band_181_plus: RankingBandEntry[];
	unranked: RankingBandEntry[];
}

export interface OpenDocument {
	doc_id: number;
	title: string;
	date: string;
	view_url: string;
}

// --- Lliga (league) ---

export interface LeagueGroupSummary {
	id: number;
	fcb_group_id: number;
	name: string;
	teams_count: number;
	jornades_count: number;
	partides_played: number;
	standings: TeamStandingRow[];
	caramboles: number;
	entrades: number;
	average: number;
	last_jornada: LeagueJornadaRow | null;
}

export interface LeagueDivisionSummary {
	id: number;
	fcb_division_id: number;
	name: string;
	groups: LeagueGroupSummary[];
}

export interface LeagueSummary {
	id: number;
	fcb_competition_id: number;
	name: string;
	season: string;
	fetched_at: string | null;
	divisions: LeagueDivisionSummary[];
}

export interface TeamStandingRow {
	position: number;
	team_name: string;
	match_points: number;
	set_points: number;
	matches_played: number;
	caramboles: number;
	entrades: number;
	average: number;
}

export interface PlayerLeagueRankingRow {
	rank: number;
	player_id: number;
	display_name: string;
	team_name: string;
	matches_played: number;
	wins: number;
	draws: number;
	losses: number;
	match_points: number;
	caramboles: number;
	entrades: number;
	average: number;
	best_serie: number;
	s1: number;
	s2: number;
	s3: number;
	s4: number;
}

export interface LeagueGroupDetail {
	id: number;
	fcb_group_id: number;
	name: string;
	division_id: number;
	division_name: string;
	league_name: string;
	league_id: number;
	season: string;
	standings: TeamStandingRow[];
	player_ranking: PlayerLeagueRankingRow[];
	caramboles: number;
	entrades: number;
	average: number;
}

export interface LeagueDivisionGroupRef {
	id: number;
	name: string;
	teams_count: number;
	partides_played: number;
}

export interface LeagueDivisionDetail {
	id: number;
	fcb_division_id: number;
	name: string;
	league_id: number;
	league_name: string;
	season: string;
	groups: LeagueDivisionGroupRef[];
	player_ranking: PlayerLeagueRankingRow[];
	caramboles: number;
	entrades: number;
	average: number;
}

export interface LeagueEncontreRow {
	id: number;
	fcb_encontre_id: number;
	home_team_name: string;
	away_team_name: string;
	home_match_points: number;
	away_match_points: number;
	home_set_points: number;
	away_set_points: number;
	partides_played: number;
	partides_total: number;
}

export interface LeagueJornadaRow {
	id: number;
	fcb_jornada_id: number;
	number: number;
	played_on: string | null;
	encontres: LeagueEncontreRow[];
}

export interface LeagueJornadasResponse {
	group_id: number;
	jornades: LeagueJornadaRow[];
}

export interface LeaguePartidaRow {
	slot: number;
	home_player_id: number | null;
	home_player_name: string | null;
	home_caramboles: number;
	home_serie_major: number;
	home_punts: number;
	away_player_id: number | null;
	away_player_name: string | null;
	away_caramboles: number;
	away_serie_major: number;
	away_punts: number;
	entrades: number;
	arbitre: string | null;
	attendance: string | null;
	modalitat: string | null;
	is_played: boolean;
}

export interface LeagueEncontreDetail {
	id: number;
	fcb_encontre_id: number;
	home_team_name: string;
	away_team_name: string;
	home_match_points: number;
	away_match_points: number;
	home_set_points: number;
	away_set_points: number;
	jornada_number: number;
	played_on: string | null;
	group_name: string;
	division_name: string;
	league_name: string;
	partides: LeaguePartidaRow[];
}

export interface PlayerLeaguePartidaRow {
	partida_id: number;
	encontre_id: number;
	fcb_encontre_id: number;
	jornada_number: number;
	played_on: string | null;
	division_name: string;
	group_name: string;
	own_team_name: string;
	opponent_player_id: number | null;
	opponent_name: string | null;
	opponent_team_name: string;
	was_home: boolean;
	own_caramboles: number;
	own_serie_major: number;
	own_punts: number;
	opp_caramboles: number;
	opp_serie_major: number;
	opp_punts: number;
	entrades: number;
	is_played: boolean;
	result: string;
}

export interface PlayerLeagueGroupSummary {
	group_id: number;
	division_name: string;
	group_name: string;
	team_name: string;
	matches_played: number;
	wins: number;
	draws: number;
	losses: number;
	match_points: number;
	caramboles: number;
	entrades: number;
	average: number;
	best_serie: number;
	s1: number;
	s2: number;
	s3: number;
	s4: number;
}

export interface LeagueTeamDetail {
	group_id: number;
	group_name: string;
	division_id: number;
	division_name: string;
	league_id: number;
	league_name: string;
	season: string;
	team_name: string;
	standing: TeamStandingRow | null;
	player_ranking: PlayerLeagueRankingRow[];
}

export interface SlotPerformanceRow {
	slot: number;
	matches_played: number;
	wins: number;
	draws: number;
	losses: number;
	match_points: number;
	caramboles: number;
	entrades: number;
	average: number;
	win_rate: number;
	best_serie: number;
}

export interface PlayerLeagueProfile {
	player_id: number;
	display_name: string;
	current_club: string | null;
	summary: PlayerLeagueGroupSummary[];
	partides: PlayerLeaguePartidaRow[];
	slot_performance: SlotPerformanceRow[];
}

export interface LeagueRefreshLastResult {
	competition_id: number;
	started_at: string;
	finished_at: string;
	success: boolean;
	divisions: number;
	groups: number;
	jornades: number;
	jornades_skipped: number;
	encontres: number;
	partides: number;
	error: string | null;
}

export interface LeagueRefreshStatus {
	in_progress: number[];
	last_result: Record<number, LeagueRefreshLastResult>;
}

export interface LeagueRefreshTriggerResponse {
	competition_id: number;
	accepted: boolean;
	already_running: boolean;
}

// --- Diff (computed Opens ranking vs official FCB PDF) ---

export type DiffKind =
	| 'matched'
	| 'position_only'
	| 'total_points'
	| 'per_open'
	| 'penalty_expected'
	| 'penalty_cascade'
	| 'position_cascade'
	| 'source_mismatch'
	| 'missing_in_official'
	| 'missing_in_computed';

export interface DiffPlayerRef {
	display_name: string;
	club: string | null;
	player_id: number | null;
}

export type DiffOverrideDecision = 'keep_computed' | 'use_official' | 'dismissed';

export interface DiffOverrideRow {
	player_name: string;
	discrepancy_kind: string;
	decision: DiffOverrideDecision;
	note: string | null;
	official_total: number | null;
	computed_total: number | null;
	updated_at: string;
}

export interface DiffOverrideUpsertRequest {
	player_name: string;
	discrepancy_kind: string;
	decision: DiffOverrideDecision;
	note?: string | null;
	official_total?: number | null;
	computed_total?: number | null;
}

export interface DiffDiscrepancy {
	kind: DiffKind;
	player: DiffPlayerRef;
	official_position: number | null;
	computed_position: number | null;
	official_total: number | null;
	computed_total: number | null;
	details: string;
	n_penalties: number | null;
	override: DiffOverrideRow | null;
}

export interface DiffOpen {
	index: number;
	label: string;
	name: string;
	season: string | null;
	fcb_division_id: number | null;
}

export interface DiffReportResponse {
	official_source: string;
	official_size: number;
	computed_size: number;
	matched_count: number;
	counts_by_kind: Record<string, number>;
	discrepancies: DiffDiscrepancy[];
	penalty_adjusted_count: number;
	penalty_cascade_count: number;
	source_mismatch_count: number;
	position_cascade_count: number;
	fetched_at: string;
	official_opens: DiffOpen[];
	computed_opens: DiffOpen[];
	opens_set_match: boolean;
}

// --- Full FCB sync ---

export interface SyncTaskResult {
	name: string; // 'monthly_ranking' | 'current_opens' | 'lliga'
	success: boolean;
	saved: number;
	skipped: number;
	error: string | null;
	detail: string | null;
}

export interface SyncResultResponse {
	started_at: string;
	finished_at: string;
	success: boolean;
	tasks: SyncTaskResult[];
}

export interface SyncStatusResponse {
	in_progress: boolean;
	started_at: string | null;
	last_result: SyncResultResponse | null;
}

export interface SyncRunResponse {
	accepted: boolean;
	already_running: boolean;
}

// --- Open projections (provisional bracket from the inscrits PDF) ---

export interface ProjectionSummary {
	id: number;
	name: string;
	season: string | null;
	num_inscriptions: number;
	fcb_division_id: number | null;
	created_at: string;
}

export interface ProjectionSeed {
	seed_order: number;
	player_name: string;
	club: string | null;
	ranking_position: number | null;
	mitjana: number;
	ranquing_estat: string;
	entry_phase: string;
	fcb_id: string | null;
	opens_points: number | null;
}

export interface ProjectionSlot {
	slot: number;
	kind: 'player' | 'winner';
	seed_order?: number;
	player_name?: string;
	club?: string | null;
	ranking_position?: number | null;
	mitjana?: number;
	ranquing_estat?: string;
	fcb_id?: string | null;
	opens_points?: number | null;
	placeholder?: string;
	label?: string;
	group?: string;
}

export interface ProjectionWarning {
	level: 'error' | 'warning' | 'info';
	message: string;
}

export interface ProjectionGroup {
	label: string;
	players: ProjectionSlot[];
}

export interface ProjectionPhase {
	name: string;
	title: string;
	n_groups: number;
	groups: ProjectionGroup[];
}

export interface ProjectionSetzens {
	match: number;
	a: ProjectionSlot;
	b: ProjectionSlot;
}

export interface ProjectionDetail {
	id: number;
	name: string;
	season: string | null;
	num_inscriptions: number;
	declared_total: number | null;
	structure: Record<string, number>;
	warnings: ProjectionWarning[];
	seeds: ProjectionSeed[];
	phases: ProjectionPhase[];
	fase_final: {
		title: string;
		n_direct_seeds: number;
		setzens: ProjectionSetzens[];
	};
	created_at: string;
	fcb_division_id: number | null;
}
