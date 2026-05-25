"""Controller central: media entre DataSource (model) i views (Qt).

La regla d'or: views NO criden DataSource directament. Tot va via signals
que el controller emet/rep.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from desktop.models import (
    ClubKpi,
    Counts,
    DataSource,
    GameRow,
    PlayerKpi,
    RankingEntry,
)
from desktop.workers.query_worker import QueryWorker


class MainController(QObject):
    """Punt central per a comunicació UI ↔ dades."""

    # Signals que les views consumeixen
    counts_loaded = pyqtSignal(Counts)
    top_rankings_loaded = pyqtSignal(list)         # list[RankingEntry]
    clubs_loaded = pyqtSignal(list)                # list[ClubKpi]
    club_players_loaded = pyqtSignal(str, list)    # (club_fcb_id, list[PlayerKpi])
    players_loaded = pyqtSignal(list)              # list[PlayerKpi]
    player_games_loaded = pyqtSignal(str, list)    # (fcb_id, list[GameRow])
    error_occurred = pyqtSignal(str)

    def __init__(self, data_source: DataSource | None = None) -> None:
        super().__init__()
        self._ds = data_source or DataSource()
        # Reference holder per als workers actius (evita garbage collection
        # mentre s'executen al thread).
        self._active_workers: list[QueryWorker] = []

    # ---------- helpers ----------

    def _run(self, task, on_result_signal) -> None:
        """Llança un QueryWorker, connecta el resultat al signal donat
        i el desreferencia quan acaba."""
        worker = QueryWorker(task)
        worker.finished_with_result.connect(on_result_signal.emit)
        worker.error.connect(self.error_occurred.emit)
        worker.finished.connect(lambda: self._active_workers.remove(worker))
        self._active_workers.append(worker)
        worker.start()

    # ---------- requests ----------

    def request_counts(self) -> None:
        self._run(self._ds.counts, self.counts_loaded)

    def request_top_rankings(self, top_n: int = 10) -> None:
        self._run(lambda: self._ds.top_ranking_per_modalitat(top_n), self.top_rankings_loaded)

    def request_clubs(self) -> None:
        self._run(self._ds.clubs_with_kpis, self.clubs_loaded)

    def request_club_players(self, club_fcb_id: str) -> None:
        def task() -> tuple[str, list[PlayerKpi]]:
            return club_fcb_id, self._ds.club_players(club_fcb_id)

        worker = QueryWorker(task)
        worker.finished_with_result.connect(
            lambda result: self.club_players_loaded.emit(result[0], result[1])
        )
        worker.error.connect(self.error_occurred.emit)
        worker.finished.connect(lambda: self._active_workers.remove(worker))
        self._active_workers.append(worker)
        worker.start()

    def request_players(self, query: str = "", limit: int = 200) -> None:
        self._run(lambda: self._ds.search_players(query, limit), self.players_loaded)

    def request_player_games(self, fcb_id: str, limit: int = 50) -> None:
        def task() -> tuple[str, list[GameRow]]:
            return fcb_id, self._ds.player_games(fcb_id, limit)

        worker = QueryWorker(task)
        worker.finished_with_result.connect(
            lambda result: self.player_games_loaded.emit(result[0], result[1])
        )
        worker.error.connect(self.error_occurred.emit)
        worker.finished.connect(lambda: self._active_workers.remove(worker))
        self._active_workers.append(worker)
        worker.start()
