// Typed API client for the fcb-opens backend.
// In development, Vite proxies /api/* to FastAPI at :8000. In
// production, the same origin serves both (or a reverse proxy does it).

import type {
	ClubOption,
	DiffOverrideRow,
	DiffOverrideUpsertRequest,
	DiffReportResponse,
	GeneratorRequest,
	GeneratorResponse,
	HealthResponse,
	LeagueDivisionDetail,
	LeagueEncontreDetail,
	LeagueGroupDetail,
	LeagueJornadasResponse,
	LeagueTeamDetail,
	LeagueRefreshStatus,
	LeagueRefreshTriggerResponse,
	LeagueSummary,
	LiveIndexEntry,
	LiveOpenResponse,
	LiveSnapshotSummary,
	OpenDocument,
	RankingBandResponse,
	MonthlyRankingDetail,
	MonthlyRankingSummary,
	OpenDetail,
	OpenSummary,
	OpensRankingResponse,
	PlayerClubSources,
	PlayerLeagueProfile,
	PlayerListEntry,
	PlayerProfile,
	StatsResponse,
	SyncRunResponse,
	SyncStatusResponse,
	ValidatorRequest,
	ValidatorResponse,
	ProjectionSummary,
	ProjectionDetail
} from './types';

const BASE = '/opens-backend/api';

async function request<T>(
	path: string,
	init: RequestInit = {},
	fetchFn: typeof fetch = fetch
): Promise<T> {
	const res = await fetchFn(`${BASE}${path}`, {
		headers: {
			'Content-Type': 'application/json',
			...(init.headers || {})
		},
		...init
	});
	if (!res.ok) {
		let detail = res.statusText;
		try {
			const body = await res.json();
			detail = body?.detail || detail;
		} catch {
			// ignore
		}
		throw new Error(`${res.status} ${detail}`);
	}
	return (await res.json()) as T;
}

export const api = {
	health: (fetchFn?: typeof fetch) => request<HealthResponse>('/health', {}, fetchFn),

	stats: (fetchFn?: typeof fetch) => request<StatsResponse>('/stats', {}, fetchFn),

	listMonthlyRankings: (fetchFn?: typeof fetch) =>
		request<MonthlyRankingSummary[]>('/rankings/monthly', {}, fetchFn),

	getMonthlyRanking: (monthId: number, fetchFn?: typeof fetch) =>
		request<MonthlyRankingDetail>(`/rankings/monthly/${monthId}`, {}, fetchFn),

	opensRanking: (window: number = 5, fetchFn?: typeof fetch) =>
		request<OpensRankingResponse>(`/rankings/opens?window=${window}`, {}, fetchFn),

	listOpens: (fetchFn?: typeof fetch) => request<OpenSummary[]>('/opens', {}, fetchFn),

	getOpen: (openId: number, fetchFn?: typeof fetch) =>
		request<OpenDetail>(`/opens/${openId}`, {}, fetchFn),

	// Provisional brackets computed from the inscrits PDF (pre-publication).
	listProjections: (fetchFn?: typeof fetch) =>
		request<ProjectionSummary[]>('/opens/projections', {}, fetchFn),

	getProjection: (id: number, fetchFn?: typeof fetch) =>
		request<ProjectionDetail>(`/opens/projections/${id}`, {}, fetchFn),

	linkProjection: (id: number, divisionId: number, fetchFn?: typeof fetch) =>
		request<{ ok: boolean }>(
			`/opens/projections/${id}/link?fcb_division_id=${divisionId}`,
			{ method: 'POST' },
			fetchFn
		),

	compareProjection: (id: number, fetchFn?: typeof fetch) =>
		request<any>(`/opens/projections/${id}/compare`, {}, fetchFn),

	getOpenLive: (
		divisionId: number,
		opts?: { force?: boolean; persist?: boolean },
		fetchFn?: typeof fetch
	) => {
		const qs = new URLSearchParams();
		if (opts?.force) qs.set('force', 'true');
		if (opts?.persist) qs.set('persist', 'true');
		const q = qs.toString();
		return request<LiveOpenResponse>(
			`/opens/live/${divisionId}${q ? '?' + q : ''}`,
			{},
			fetchFn
		);
	},

	listLiveCompetitions: (opts?: { force?: boolean }, fetchFn?: typeof fetch) => {
		const q = opts?.force ? '?force=true' : '';
		return request<LiveIndexEntry[]>(`/opens/live${q}`, {}, fetchFn);
	},

	listSnapshots: (divisionId: number, fetchFn?: typeof fetch) =>
		request<LiveSnapshotSummary[]>(`/opens/live/${divisionId}/snapshots`, {}, fetchFn),

	getSnapshot: (snapshotId: number, fetchFn?: typeof fetch) =>
		request<LiveOpenResponse>(`/opens/live/snapshot/${snapshotId}`, {}, fetchFn),

	getLiveOpenByRankingBand: (
		divisionId: number,
		opts?: { monthId?: number | null; force?: boolean },
		fetchFn?: typeof fetch
	) => {
		const qs = new URLSearchParams();
		if (opts?.monthId != null) qs.set('month_id', String(opts.monthId));
		if (opts?.force) qs.set('force', 'true');
		const q = qs.toString();
		return request<RankingBandResponse>(
			`/opens/live/${divisionId}/by-ranking-band${q ? '?' + q : ''}`,
			{},
			fetchFn
		);
	},

	// Pin the monthly ranking used for an Open's prize bands (convocatòria-time
	// ranking). `monthId = 0` clears the choice (falls back to latest).
	setPrizeRanking: (divisionId: number, monthId: number, fetchFn?: typeof fetch) =>
		request<{ ok: boolean; division_id: number; month_id: number | null }>(
			`/opens/live/${divisionId}/prize-ranking?month_id=${monthId}`,
			{ method: 'PUT' },
			fetchFn
		),

	listOpensDocs: (fetchFn?: typeof fetch) =>
		request<OpenDocument[]>('/opens/docs', {}, fetchFn),

	getDocsForOpen: (divisionId: number, fetchFn?: typeof fetch) =>
		request<OpenDocument[]>(`/opens/live/${divisionId}/documents`, {}, fetchFn),

	listClubs: (fetchFn?: typeof fetch) =>
		request<ClubOption[]>('/clubs', {}, fetchFn),

	listPlayers: (
		opts?: { q?: string; missingClub?: boolean; limit?: number; offset?: number },
		fetchFn?: typeof fetch
	) => {
		const qs = new URLSearchParams();
		if (opts?.q) qs.set('q', opts.q);
		if (opts?.missingClub) qs.set('missing_club', 'true');
		if (opts?.limit !== undefined) qs.set('limit', String(opts.limit));
		if (opts?.offset !== undefined) qs.set('offset', String(opts.offset));
		const q = qs.toString();
		return request<PlayerListEntry[]>(`/players${q ? '?' + q : ''}`, {}, fetchFn);
	},

	getPlayer: (playerId: number, fetchFn?: typeof fetch) =>
		request<PlayerProfile>(`/players/${playerId}`, {}, fetchFn),

	setPlayerManualClub: (
		playerId: number,
		manualClub: string | null,
		fetchFn?: typeof fetch
	) =>
		request<PlayerClubSources>(
			`/players/${playerId}/club`,
			{ method: 'PATCH', body: JSON.stringify({ manual_club: manualClub }) },
			fetchFn
		),

	getPlayerLeagueProfile: (playerId: number, fetchFn?: typeof fetch) =>
		request<PlayerLeagueProfile>(`/players/${playerId}/lliga`, {}, fetchFn),

	listLeagues: (fetchFn?: typeof fetch) =>
		request<LeagueSummary[]>('/leagues', {}, fetchFn),

	getLeagueGroup: (groupId: number, fetchFn?: typeof fetch) =>
		request<LeagueGroupDetail>(`/leagues/groups/${groupId}`, {}, fetchFn),

	getLeagueDivision: (divisionId: number, fetchFn?: typeof fetch) =>
		request<LeagueDivisionDetail>(`/leagues/divisions/${divisionId}`, {}, fetchFn),

	getLeagueTeam: (groupId: number, teamName: string, fetchFn?: typeof fetch) =>
		request<LeagueTeamDetail>(
			`/leagues/groups/${groupId}/teams/${encodeURIComponent(teamName)}`,
			{},
			fetchFn
		),

	getLeagueJornades: (groupId: number, fetchFn?: typeof fetch) =>
		request<LeagueJornadasResponse>(`/leagues/groups/${groupId}/jornades`, {}, fetchFn),

	getLeagueEncontre: (encontreId: number, fetchFn?: typeof fetch) =>
		request<LeagueEncontreDetail>(`/leagues/encontres/${encontreId}`, {}, fetchFn),

	getLeagueRefreshStatus: (fetchFn?: typeof fetch) =>
		request<LeagueRefreshStatus>('/leagues/refresh-status', {}, fetchFn),

	triggerLeagueRefresh: (competitionId: number = 36, fetchFn?: typeof fetch) =>
		request<LeagueRefreshTriggerResponse>(
			`/leagues/refresh?competition_id=${competitionId}`,
			{ method: 'POST' },
			fetchFn
		),

	runGenerator: (body: GeneratorRequest, fetchFn?: typeof fetch) =>
		request<GeneratorResponse>(
			'/generator',
			{ method: 'POST', body: JSON.stringify(body) },
			fetchFn
		),

	runValidator: (body: ValidatorRequest, fetchFn?: typeof fetch) =>
		request<ValidatorResponse>(
			'/validator',
			{ method: 'POST', body: JSON.stringify(body) },
			fetchFn
		),

	getOfficialDiff: (
		opts?: { force?: boolean; useCacheOnly?: boolean },
		fetchFn?: typeof fetch
	) => {
		const qs = new URLSearchParams();
		if (opts?.force) qs.set('force', 'true');
		if (opts?.useCacheOnly) qs.set('use_cache_only', 'true');
		const q = qs.toString();
		return request<DiffReportResponse>(`/diff/official${q ? '?' + q : ''}`, {}, fetchFn);
	},

	listDiffOverrides: (fetchFn?: typeof fetch) =>
		request<DiffOverrideRow[]>('/diff/overrides', {}, fetchFn),

	upsertDiffOverride: (body: DiffOverrideUpsertRequest, fetchFn?: typeof fetch) =>
		request<DiffOverrideRow>(
			'/diff/overrides',
			{ method: 'POST', body: JSON.stringify(body) },
			fetchFn
		),

	deleteDiffOverride: (
		playerName: string,
		discrepancyKind: string,
		fetchFn?: typeof fetch
	) => {
		const qs = new URLSearchParams({
			player_name: playerName,
			discrepancy_kind: discrepancyKind
		});
		return request<{ deleted: number }>(
			`/diff/overrides?${qs.toString()}`,
			{ method: 'DELETE' },
			fetchFn
		);
	},

	triggerFullSync: (force: boolean = true, fetchFn?: typeof fetch) =>
		request<SyncRunResponse>(
			`/sync/run?force=${force ? 'true' : 'false'}`,
			{ method: 'POST' },
			fetchFn
		),

	getSyncStatus: (fetchFn?: typeof fetch) =>
		request<SyncStatusResponse>('/sync/status', {}, fetchFn)
};

/** Parse a user-pasted textarea into a list of inscription inputs.
 *
 * Accepts lines like:
 *    "SURNAME, GIVEN"
 *    "SURNAME, GIVEN | C.B. CLUB"
 *    "SURNAME, GIVEN | C.B. CLUB | 150"      (name, club, opens_points)
 * Blank lines and lines starting with # are ignored.
 */
export function parseInscriptionText(text: string): { player_name: string; club: string }[] {
	const lines = text.split(/\r?\n/);
	const out: { player_name: string; club: string }[] = [];
	for (const raw of lines) {
		const line = raw.trim();
		if (!line || line.startsWith('#')) continue;
		const parts = line.split('|').map((s) => s.trim());
		const player_name = parts[0];
		const club = parts[1] || '';
		if (player_name) out.push({ player_name, club });
	}
	return out;
}

/** Format a list of inscriptions back into textarea-style lines. */
export function formatInscriptionLines(rows: { player_name: string; club?: string | null }[]): string {
	return rows
		.map((r) => {
			const club = (r.club ?? '').trim();
			return club ? `${r.player_name} | ${club}` : r.player_name;
		})
		.join('\n');
}

type RawInscription = { player_name: string; club: string };

/** Best-effort extraction of inscriptions from a JSON document.
 *
 * Recognises the shapes produced by this project (e.g. `jugadors_banyoles.json`,
 * monthly ranking exports, generator dumps) plus generic
 * `{name, club}` / `{display_name, equips}` arrays.
 */
function extractFromJson(data: unknown): RawInscription[] {
	const arr: unknown[] = Array.isArray(data)
		? data
		: data && typeof data === 'object' && Array.isArray((data as Record<string, unknown>).players)
			? ((data as Record<string, unknown>).players as unknown[])
			: data && typeof data === 'object' && Array.isArray((data as Record<string, unknown>).inscriptions)
				? ((data as Record<string, unknown>).inscriptions as unknown[])
				: data && typeof data === 'object' && Array.isArray((data as Record<string, unknown>).entries)
					? ((data as Record<string, unknown>).entries as unknown[])
					: [];
	const out: RawInscription[] = [];
	for (const item of arr) {
		if (!item || typeof item !== 'object') continue;
		const o = item as Record<string, unknown>;
		const name =
			(typeof o.display_name === 'string' && o.display_name) ||
			(typeof o.player_name === 'string' && o.player_name) ||
			(typeof o.name === 'string' && o.name) ||
			(typeof o.cognoms === 'string' && typeof o.nom === 'string' && `${o.cognoms}, ${o.nom}`) ||
			'';
		if (!name) continue;
		const club =
			(typeof o.club === 'string' && o.club) ||
			(typeof o.current_club === 'string' && o.current_club) ||
			(Array.isArray(o.equips) && typeof o.equips[0] === 'string' && (o.equips[0] as string)) ||
			'';
		out.push({ player_name: String(name).trim(), club: String(club).trim() });
	}
	return out;
}

/** Pick the most likely delimiter for a CSV/TSV blob. */
function detectDelimiter(text: string): string {
	const firstLine = text.split(/\r?\n/).find((l) => l.trim().length > 0) ?? '';
	if (firstLine.includes('\t')) return '\t';
	if (firstLine.includes(';')) return ';';
	if (firstLine.includes('|')) return '|';
	// Plain comma is risky because names contain ", " (e.g. "AGUILAR SALA, RAMÓN").
	// Only fall back to comma if there are multiple commas per line, suggesting >2 columns.
	const commas = (firstLine.match(/,/g) || []).length;
	return commas >= 2 ? ',' : '';
}

/** Header-aware CSV/TSV row parser.
 *
 * If the first non-empty row looks like a header (contains keywords like
 * "name", "nom", "club", "equip"), use it to map columns. Otherwise
 * assume column 1 = name, column 2 = club.
 */
function extractFromDelimited(text: string, delimiter: string): RawInscription[] {
	const rows: string[] = text.split(/\r?\n/).map((l) => l.trim()).filter((l) => l.length > 0);
	if (rows.length === 0) return [];
	const split = (line: string) => line.split(delimiter).map((c) => c.trim().replace(/^"|"$/g, ''));
	const first = split(rows[0]);
	const looksLikeHeader = first.some((c) => /^(name|player_name|nom|jugador|display_name)$/i.test(c));
	let nameIdx = 0;
	let clubIdx = 1;
	let dataStart = 0;
	if (looksLikeHeader) {
		const lc = first.map((c) => c.toLowerCase());
		const findIdx = (...keys: string[]) => lc.findIndex((c) => keys.includes(c));
		const ni = findIdx('name', 'player_name', 'nom', 'jugador', 'display_name');
		const ci = findIdx('club', 'equip', 'current_club', 'team');
		if (ni >= 0) nameIdx = ni;
		if (ci >= 0) clubIdx = ci;
		dataStart = 1;
	}
	const out: RawInscription[] = [];
	for (let i = dataStart; i < rows.length; i++) {
		const cols = split(rows[i]);
		const name = cols[nameIdx]?.trim() ?? '';
		if (!name) continue;
		const club = cols[clubIdx]?.trim() ?? '';
		out.push({ player_name: name, club });
	}
	return out;
}

/** Parse the contents of an uploaded file into inscription rows.
 *
 * Supports: .json (project shape or generic array), .csv / .tsv (header-aware),
 * .txt (one player per line, optional ` | club`). Returns null if the format
 * is unrecognised so the caller can show a hint.
 */
export function parseInscriptionFile(
	filename: string,
	content: string
): RawInscription[] | null {
	const ext = filename.toLowerCase().split('.').pop() ?? '';
	const trimmed = content.trim();
	if (ext === 'json' || trimmed.startsWith('[') || trimmed.startsWith('{')) {
		try {
			return extractFromJson(JSON.parse(trimmed));
		} catch {
			// fall through to delimited parsing
		}
	}
	if (ext === 'tsv') return extractFromDelimited(content, '\t');
	if (ext === 'csv') {
		const delim = detectDelimiter(content) || ',';
		return extractFromDelimited(content, delim);
	}
	if (ext === 'txt' || ext === '' || ext === 'md') {
		// Plain text: reuse the textarea parser so users get the same semantics.
		return parseInscriptionText(content);
	}
	// Unknown extension: try to be helpful by sniffing.
	const delim = detectDelimiter(content);
	if (delim) return extractFromDelimited(content, delim);
	return null;
}

// --- FCBillar main-app endpoints (/api, not the mounted opens sub-app) ---

/** Map opens player names → FCBillar fcb_id (null when absent/ambiguous). */
export async function resolvePlayers(
	names: string[],
	fetchFn: typeof fetch = fetch
): Promise<Record<string, string | null>> {
	if (!names.length) return {};
	const res = await fetchFn('/api/opens/resolve-players', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ names })
	});
	return res.ok ? res.json() : {};
}

/** Players flagged as 'seguiment' in FCBillar. */
export async function followedPlayers(
	fetchFn: typeof fetch = fetch
): Promise<{ fcb_id: string; nom: string }[]> {
	const res = await fetchFn('/api/opens/followed-players');
	return res.ok ? res.json() : [];
}

/** Upload an inscrits PDF (raw body) and build/save its projection. */
export async function importInscrits(
	file: File,
	opts: { name?: string; season?: string } = {}
): Promise<{ id: number; name: string; num_inscriptions: number; structure: Record<string, number>; n_linked: number }> {
	const qs = new URLSearchParams();
	if (opts.name) qs.set('name', opts.name);
	if (opts.season) qs.set('season', opts.season);
	const res = await fetch(`/api/opens/import-inscrits?${qs}`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/pdf' },
		body: file
	});
	if (!res.ok) {
		let detail = res.statusText;
		try {
			detail = (await res.json())?.detail ?? detail;
		} catch {
			/* ignore */
		}
		throw new Error(detail);
	}
	return res.json();
}
