"""Pydantic request/response schemas for the HTTP API.

Keeps a clear boundary between internal dataclasses (`models.py`,
`generator.py`, `reglament.ordenacio`) and the JSON representation
exposed to the frontend. Converting here means the internal modules
stay pure-Python and the schemas can evolve independently for
documentation and validation purposes.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Shared primitives
# --------------------------------------------------------------------------- #


class PlayerRef(BaseModel):
    """A minimal player reference used in list responses."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    display_name: str
    current_club: str | None = None


# --------------------------------------------------------------------------- #
# /api/health and /api/stats
# --------------------------------------------------------------------------- #


class HealthResponse(BaseModel):
    status: str
    version: str


class StatsResponse(BaseModel):
    monthly_rankings: int
    opens: int
    players: int
    latest_month_id: int | None = None
    latest_open_name: str | None = None


# --------------------------------------------------------------------------- #
# Monthly rankings
# --------------------------------------------------------------------------- #


class MonthlyRankingSummary(BaseModel):
    month_id: int
    fetched_at: str
    entry_count: int


class MonthlyRankingRow(BaseModel):
    position: int
    player_id: int
    player_name: str
    current_club: str | None
    average: float
    matches_scored: int
    matches_max: int
    is_definitive: bool


class MonthlyRankingDetail(BaseModel):
    month_id: int
    fetched_at: str
    entries: list[MonthlyRankingRow]


# --------------------------------------------------------------------------- #
# Opens ranking (computed)
# --------------------------------------------------------------------------- #


class OpenBreakdown(BaseModel):
    open_id: int
    fcb_division_id: int
    name: str
    season: str
    points: int | None


class OpensRankingRow(BaseModel):
    rank: int
    player_id: int
    display_name: str
    club: str | None
    total_points: int
    max_single_open: int
    opens_played: int
    breakdown: list[OpenBreakdown]


class OpensRankingResponse(BaseModel):
    window_size: int
    opens_in_window: int
    entries: list[OpensRankingRow]


# --------------------------------------------------------------------------- #
# Opens (stored)
# --------------------------------------------------------------------------- #


class OpenSummary(BaseModel):
    id: int
    fcb_division_id: int
    fcb_classification_id: int | None
    name: str
    season: str
    player_count: int


class OpenClassificationRow(BaseModel):
    position: int
    player_id: int
    player_name: str
    club: str | None
    matches_played: int
    match_points: int
    caramboles: int
    entries: int
    general_average: float
    particular_average: float
    best_series: int
    open_points: int


class OpenDetail(BaseModel):
    id: int
    fcb_division_id: int
    fcb_classification_id: int | None
    name: str
    season: str
    classification: list[OpenClassificationRow]


# --------------------------------------------------------------------------- #
# Player profile
# --------------------------------------------------------------------------- #


class PlayerOpenResult(BaseModel):
    open_id: int
    open_name: str
    position: int
    general_average: float
    open_points: int


class PlayerClubSourcesResponse(BaseModel):
    """Per-source club values plus the resolved value for one player.

    `source` is one of: "manual", "opens" (current season), "lliga",
    "opens_old" (older-season Opens fallback), "none". The frontend
    surfaces all four sources so the user can see why a particular
    club was chosen and disambiguate manually when needed.
    """

    opens_club: str | None = None      # current-season Opens
    opens_old_club: str | None = None  # older-season Opens (fallback only)
    lliga_club: str | None = None
    manual_club: str | None = None
    resolved_club: str | None = None
    source: str  # 'manual' | 'opens' | 'lliga' | 'opens_old' | 'none'


class PlayerRankingHistoryEntry(BaseModel):
    """One snapshot of a player's monthly FCB ranking over time."""

    month_id: int
    fetched_at: str
    position: int
    average: float
    matches_scored: int
    matches_max: int
    is_definitive: bool
    club: str | None = None


class PlayerProfile(BaseModel):
    id: int
    display_name: str
    normalized_name: str
    current_club: str | None
    club_sources: PlayerClubSourcesResponse
    latest_monthly_ranking: MonthlyRankingRow | None
    total_opens_points: int
    opens_history: list[PlayerOpenResult]
    # Chronological list of every monthly-ranking snapshot we have for this
    # player. Ordered oldest → newest so the frontend can plot the mitjana
    # evolution without sorting.
    ranking_history: list[PlayerRankingHistoryEntry]


class PlayerListEntry(BaseModel):
    id: int
    display_name: str
    normalized_name: str
    club_sources: PlayerClubSourcesResponse
    opens_played: int
    lliga_partides: int


class SetManualClubRequest(BaseModel):
    """Body for PATCH /api/players/{id}/club. Pass `null` or an empty
    string to clear the override; otherwise the trimmed value is stored."""

    manual_club: str | None = None


class ClubOption(BaseModel):
    """One distinct club seen across our data sources.

    `sources` lists where the value was found (any of: 'opens', 'lliga',
    'monthly_ranking', 'manual', 'players_current'). `occurrences` is a
    rough heuristic for how widely used the club is, useful for ranking
    suggestions in the picker.
    """

    name: str
    sources: list[str]
    occurrences: int


# --------------------------------------------------------------------------- #
# Generator
# --------------------------------------------------------------------------- #


class InscriptionInput(BaseModel):
    """One entry submitted by the user for an Open sign-up.

    Only `player_name` is strictly required. If `club` is omitted we
    use the empty string, and all ranking fields default to 0/None and
    will be auto-filled from the database if a match is found.
    """

    player_name: str
    club: str = ""
    opens_points: int | None = None  # if None, look up from stored Opens ranking
    fcb_ranking_position: int | None = None
    fcb_ranking_is_definitive: bool | None = None
    fcb_ranking_average: float | None = None


class EnrichedInscription(BaseModel):
    """An inscription after DB lookup."""

    player_name: str
    club: str
    opens_points: int
    fcb_ranking_position: int | None
    fcb_ranking_is_definitive: bool
    fcb_ranking_average: float
    matched: bool  # True if we found the player in the monthly ranking


class GroupSlotResponse(BaseModel):
    label: str  # e.g. "85" or "1-PPP"
    inscription_position: int | None
    placeholder_rank: int | None
    placeholder_phase: str | None
    # Resolved player info if this slot has a direct seed
    player_name: str | None = None
    club: str | None = None


class GroupResponse(BaseModel):
    label: str  # e.g. "AG", "Q", "A"
    slots: list[GroupSlotResponse]


class PhaseResponse(BaseModel):
    name: str  # "PPP", "PP", "P"
    groups: list[GroupResponse]


class TournamentResponse(BaseModel):
    num_inscriptions: int
    phases: dict[str, PhaseResponse]


class AnomalyResponse(BaseModel):
    code: str
    severity: str
    message: str
    affected_players: list[str]


class GeneratorRequest(BaseModel):
    inscriptions: list[InscriptionInput] = Field(..., min_length=1)
    auto_enrich: bool = True  # if True, look up missing fields from DB
    month_id: int | None = None  # which monthly ranking to use for enrichment


class GeneratorResponse(BaseModel):
    enriched_inscriptions: list[EnrichedInscription]  # in submitted order
    ordered_inscriptions: list[EnrichedInscription]  # after sort_inscriptions
    unmatched: list[str]  # names not found in monthly ranking
    tournament: TournamentResponse | None  # None if num != 120 (unsupported)
    anomalies: list[AnomalyResponse]


# --------------------------------------------------------------------------- #
# Validator
# --------------------------------------------------------------------------- #


class ValidatorRequest(BaseModel):
    inscriptions: list[InscriptionInput] = Field(..., min_length=1)
    auto_enrich: bool = True
    month_id: int | None = None


class ValidatorResponse(BaseModel):
    enriched_inscriptions: list[EnrichedInscription]
    unmatched: list[str]
    anomalies: list[AnomalyResponse]


# --------------------------------------------------------------------------- #
# Live open state
# --------------------------------------------------------------------------- #


class LiveStanding(BaseModel):
    player_name: str
    club: str
    punts: int
    mitjana: float


class LiveMatch(BaseModel):
    player_a: str
    player_b: str
    punts_a: int
    punts_b: int
    caramboles_a: int
    caramboles_b: int
    serie_major_a: int
    serie_major_b: int
    entrades: int | None
    arbitre: str | None
    is_played: bool


class LiveGroup(BaseModel):
    label: str
    url: str
    venue: str | None
    standings: list[LiveStanding]
    matches: list[LiveMatch]
    n_matches_played: int
    n_matches_total: int


class ProvisionalQualifier(BaseModel):
    """A player computed internally as advancing from a group. NOT FCB-official."""

    group_label: str
    position_in_group: int
    player_name: str
    club: str
    punts: int
    mitjana: float
    serie_major: int = 0


class LivePhase(BaseModel):
    label: str
    kind: str  # "group" | "ko"
    url: str
    groups: list[LiveGroup]
    ko_matches: list[LiveMatch]
    is_active: bool  # has some matches played AND some still pending
    provisional_qualifiers: list[ProvisionalQualifier] = []  # computed, not FCB
    provisional_matches: list[LiveMatch] = []  # computed pairings, not FCB


class LiveOpenResponse(BaseModel):
    division_id: int
    name: str
    phase_id: int | None
    phases: list[LivePhase]
    fetched_at: str  # ISO-8601 timestamp of when we scraped


class LiveIndexEntry(BaseModel):
    division_id: int
    name: str
    index: int


class RankingBandEntry(BaseModel):
    """One player in a parallel by-ranking-band classification view.

    Captures both the FCB ranking position at convocatòria time (the
    cutoff that decides which band they belong to) and the player's
    current live performance in the Open (group, punts, mitjana).
    """

    player_name: str
    club: str
    fcb_position: int | None
    fcb_is_definitive: bool
    phase_label: str  # phase the player is currently in (most-recent occurrence)
    group_label: str  # group within that phase
    punts: int
    mitjana: float


class RankingBandResponse(BaseModel):
    """Parallel classifications for an in-progress Open, partitioned by FCB
    ranking position at the moment of convocatòria.

    Three buckets are returned: positions 61-180 ("amateur amunt"),
    positions 181 onwards ("amateur avall"), and unranked players
    (Provisionals / Definitivas / mai apareguts al rànquing mensual).
    Top 60 are deliberately omitted — they're already the natural
    focus of the main standings view.
    """

    division_id: int
    open_name: str
    month_id: int
    fetched_at: str  # ISO-8601, same instant as the live fetch
    band_61_180: list[RankingBandEntry]
    band_181_plus: list[RankingBandEntry]
    unranked: list[RankingBandEntry]


class LiveSnapshotSummary(BaseModel):
    id: int
    captured_at: str


class OpenDocument(BaseModel):
    """A reference to a document published by the FCB in the Opens section."""

    doc_id: int
    title: str
    date: str           # DD/MM/YYYY as printed by FCB
    view_url: str


# --------------------------------------------------------------------------- #
# Lliga (league) feature
# --------------------------------------------------------------------------- #


class LeagueGroupSummary(BaseModel):
    id: int
    fcb_group_id: int
    name: str
    teams_count: int
    jornades_count: int
    partides_played: int
    standings: list["TeamStandingRow"] = []
    # Mitjana general del grup (Σ caramboles / Σ entrades per costat,
    # acumulat sobre les partides disputades). 0/0/0.0 si encara cap
    # partida no s'ha jugat.
    caramboles: int = 0
    entrades: int = 0
    average: float = 0.0
    # Latest played jornada (highest `number` with at least one played
    # partida). Null until the season's first results are in. Embedded so
    # the index page can render results without an extra round-trip.
    last_jornada: "LeagueJornadaRow | None" = None


class LeagueDivisionSummary(BaseModel):
    id: int
    fcb_division_id: int
    name: str
    groups: list[LeagueGroupSummary]


class LeagueSummary(BaseModel):
    id: int
    fcb_competition_id: int
    name: str
    season: str
    fetched_at: str | None
    divisions: list[LeagueDivisionSummary]


class TeamStandingRow(BaseModel):
    position: int
    team_name: str
    match_points: int
    set_points: int
    matches_played: int
    # Aggregated from played partides (NOT FCB-published — we compute it).
    # Defaults to 0/0/0.0 for teams that haven't played any partida yet.
    caramboles: int = 0
    entrades: int = 0
    average: float = 0.0


class PlayerLeagueRankingRow(BaseModel):
    rank: int
    player_id: int
    display_name: str
    team_name: str
    matches_played: int
    wins: int
    draws: int
    losses: int
    match_points: int
    caramboles: int
    entrades: int
    average: float
    best_serie: int
    # Slot distribution within an encontre (board 1..4).
    s1: int = 0
    s2: int = 0
    s3: int = 0
    s4: int = 0


class LeagueGroupDetail(BaseModel):
    id: int
    fcb_group_id: int
    name: str
    division_id: int
    division_name: str
    league_name: str
    league_id: int
    season: str
    standings: list[TeamStandingRow]
    player_ranking: list[PlayerLeagueRankingRow]
    # Group-wide mitjana (see LeagueGroupSummary for definition).
    caramboles: int = 0
    entrades: int = 0
    average: float = 0.0


class LeagueDivisionGroupRef(BaseModel):
    """Lightweight pointer to a group, for the division detail page."""

    id: int
    name: str
    teams_count: int
    partides_played: int


class LeagueTeamDetail(BaseModel):
    """A single team within a group: its standing row, aggregate (CAR/ENT/MG)
    and the ranked list of its players (those who appeared on the team's
    side in any played partida)."""

    group_id: int
    group_name: str
    division_id: int
    division_name: str
    league_id: int
    league_name: str
    season: str
    team_name: str
    standing: TeamStandingRow | None
    player_ranking: list[PlayerLeagueRankingRow]


class LeagueDivisionDetail(BaseModel):
    """Per-category (division) view: aggregated player ranking + group list."""

    id: int
    fcb_division_id: int
    name: str
    league_name: str
    league_id: int
    season: str
    groups: list[LeagueDivisionGroupRef]
    player_ranking: list[PlayerLeagueRankingRow]
    # Mitjana general de la categoria sencera (combinació de tots els grups).
    caramboles: int = 0
    entrades: int = 0
    average: float = 0.0


class LeagueEncontreRow(BaseModel):
    id: int
    fcb_encontre_id: int
    home_team_name: str
    away_team_name: str
    home_match_points: int
    away_match_points: int
    home_set_points: int
    away_set_points: int
    partides_played: int
    partides_total: int


class LeagueJornadaRow(BaseModel):
    id: int
    fcb_jornada_id: int
    number: int
    played_on: str | None
    encontres: list[LeagueEncontreRow]


class LeagueJornadasResponse(BaseModel):
    group_id: int
    jornades: list[LeagueJornadaRow]


class LeaguePartidaRow(BaseModel):
    slot: int
    home_player_id: int | None
    home_player_name: str | None
    home_caramboles: int
    home_serie_major: int
    home_punts: int
    away_player_id: int | None
    away_player_name: str | None
    away_caramboles: int
    away_serie_major: int
    away_punts: int
    entrades: int
    arbitre: str | None
    attendance: str | None
    modalitat: str | None
    is_played: bool


class LeagueEncontreDetail(BaseModel):
    id: int
    fcb_encontre_id: int
    home_team_name: str
    away_team_name: str
    home_match_points: int
    away_match_points: int
    home_set_points: int
    away_set_points: int
    jornada_number: int
    played_on: str | None
    group_name: str
    division_name: str
    league_name: str
    partides: list[LeaguePartidaRow]


class PlayerLeaguePartidaRow(BaseModel):
    partida_id: int
    encontre_id: int
    fcb_encontre_id: int
    jornada_number: int
    played_on: str | None
    division_name: str
    group_name: str
    own_team_name: str
    opponent_player_id: int | None
    opponent_name: str | None
    opponent_team_name: str
    was_home: bool
    own_caramboles: int
    own_serie_major: int
    own_punts: int
    opp_caramboles: int
    opp_serie_major: int
    opp_punts: int
    entrades: int
    is_played: bool
    result: str  # "V" | "D" | "E" | "—"


class PlayerLeagueGroupSummary(BaseModel):
    """Per-group KPIs of a player. Aggregated from played partides."""

    group_id: int
    division_name: str
    group_name: str
    team_name: str
    matches_played: int
    wins: int
    draws: int
    losses: int
    match_points: int
    caramboles: int
    entrades: int
    average: float
    best_serie: int
    s1: int = 0
    s2: int = 0
    s3: int = 0
    s4: int = 0


class SlotPerformanceRow(BaseModel):
    """Reliability metrics for one slot (board 1..4) — across every league
    partida the player has played in.
    """

    slot: int
    matches_played: int
    wins: int
    draws: int
    losses: int
    match_points: int
    caramboles: int
    entrades: int
    average: float
    win_rate: float          # 0..1
    best_serie: int


class PlayerLeagueProfile(BaseModel):
    player_id: int
    display_name: str
    current_club: str | None
    summary: list[PlayerLeagueGroupSummary]
    partides: list[PlayerLeaguePartidaRow]
    slot_performance: list[SlotPerformanceRow] = []


class LeagueRefreshLastResult(BaseModel):
    competition_id: int
    started_at: str
    finished_at: str
    success: bool
    divisions: int = 0
    groups: int = 0
    jornades: int = 0
    jornades_skipped: int = 0
    encontres: int = 0
    partides: int = 0
    error: str | None = None


class LeagueRefreshStatus(BaseModel):
    """Current refresh state for one or more competitions.

    `in_progress` lists competition ids that are actively being refreshed.
    `last_result[competition_id]` is the outcome of the most recent
    completed refresh, present only if at least one has finished in the
    current process.
    """

    in_progress: list[int]
    last_result: dict[int, LeagueRefreshLastResult]


class LeagueRefreshTriggerResponse(BaseModel):
    competition_id: int
    accepted: bool
    already_running: bool


# --------------------------------------------------------------------------- #
# Diff (computed Opens ranking vs official FCB PDF)
# --------------------------------------------------------------------------- #


class DiffPlayerRef(BaseModel):
    display_name: str
    club: str | None = None
    player_id: int | None = None


class DiffOverrideRow(BaseModel):
    """A user decision attached to a discrepancy: which side to trust."""

    player_name: str
    discrepancy_kind: str
    decision: str  # 'keep_computed' | 'use_official' | 'dismissed'
    note: str | None = None
    official_total: int | None = None
    computed_total: int | None = None
    updated_at: str


class DiffDiscrepancy(BaseModel):
    """One row of difference between official PDF and computed ranking.

    `kind` is one of: position_only, total_points, per_open, penalty_expected,
    penalty_cascade, position_cascade, source_mismatch, missing_in_official,
    missing_in_computed.

    `override` is the user-decided resolution if any. When `override.decision`
    differs from the *current* totals, the frontend should warn the user that
    the underlying discrepancy may have shifted since they decided.
    """

    kind: str
    player: DiffPlayerRef
    official_position: int | None = None
    computed_position: int | None = None
    official_total: int | None = None
    computed_total: int | None = None
    details: str
    n_penalties: int | None = None
    override: DiffOverrideRow | None = None


class DiffOpen(BaseModel):
    """An Open used either by the official PDF or by the computed ranking.

    `index` is the column index in the PDF (0-based) when the Open comes from
    the PDF; for the computed list it's the index in the rolling 5-Open window.
    `fcb_division_id` is set only for computed Opens (we don't try to match a
    PDF column to a FCB division id, since the PDF labels are free text).
    """

    index: int
    label: str  # short label as it appears in the PDF, e.g. "1r OPEN"
    name: str  # full name
    season: str | None = None
    fcb_division_id: int | None = None


class DiffReportResponse(BaseModel):
    official_source: str
    official_size: int
    computed_size: int
    matched_count: int
    counts_by_kind: dict[str, int]
    discrepancies: list[DiffDiscrepancy]
    penalty_adjusted_count: int
    penalty_cascade_count: int
    source_mismatch_count: int
    position_cascade_count: int
    fetched_at: str  # ISO8601 timestamp of when the diff was computed
    # Open-set comparison: the diff is only meaningful if both sides cover the
    # same set of Opens. The frontend surfaces these so the user can verify.
    official_opens: list[DiffOpen]
    computed_opens: list[DiffOpen]
    opens_set_match: bool


class DiffOverrideUpsertRequest(BaseModel):
    player_name: str = Field(..., min_length=1)
    discrepancy_kind: str = Field(..., min_length=1)
    decision: str  # 'keep_computed' | 'use_official' | 'dismissed'
    note: str | None = None
    official_total: int | None = None
    computed_total: int | None = None


# --------------------------------------------------------------------------- #
# Full FCB sync (refresh of monthly ranking + opens + lligues)
# --------------------------------------------------------------------------- #


class SyncTaskResult(BaseModel):
    name: str  # "monthly_ranking", "current_opens", "lliga"
    success: bool
    saved: int = 0
    skipped: int = 0
    error: str | None = None
    detail: str | None = None


class SyncResultResponse(BaseModel):
    started_at: str
    finished_at: str
    success: bool
    tasks: list[SyncTaskResult]


class SyncStatusResponse(BaseModel):
    in_progress: bool
    started_at: str | None = None
    last_result: SyncResultResponse | None = None


class SyncRunResponse(BaseModel):
    accepted: bool
    already_running: bool
