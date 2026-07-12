"""Vista Reingesta: dos panells (LOGADA / NO LOGADA) amb execució seqüencial.

- LOGADA (necessita login + captcha → manual): rànquing + partides (`games`).
  Opció: només el rànquing recent o reimport històric complet.
- NO LOGADA (pàgines públiques, sense sessió): lliga, copa, opens, individuals.
  Seleccionables; opcionalment publica al núvol en acabar. És la part que es podrà
  automatitzar al núvol (GitHub Actions, disparat per Vercel).

Cada acció encua una o més comandes `uv run …` que s'executen EN SÈRIE (cada pas
aïllat; si un falla, la resta continua, com weekly_reingest.ps1) amb log en viu.
"""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from desktop.views.widgets import SectionTitle
from desktop.workers import SubprocessWorker

UV = ["uv", "run"]
FCB = [*UV, "fcbillar"]
OPENS = [*UV, "python", "-m", "fcb_opens.cli"]


def _panel(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("reingestPanel")
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    lab = QLabel(title)
    lab.setObjectName("reingestPanelTitle")
    lab.setFont(QFont("", 11, QFont.Weight.Bold))
    lay.addWidget(lab)
    return frame, lay


class ReingestaView(QWidget):
    """Reingesta logada/no-logada amb cua de comandes i log en viu."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: SubprocessWorker | None = None
        self._queue: list[tuple[str, list[str]]] = []
        self._build_ui()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)
        root.addWidget(SectionTitle("Reingesta"))

        info = QLabel(
            "Dues menes d'ingesta. La <b>logada</b> (rànquing + partides) necessita "
            "login amb captcha i s'executa a mà. La <b>no logada</b> (lliga, copa, "
            "opens, individuals) llegeix pàgines públiques i és la que s'automatitzarà "
            "al núvol. Cada acció corre en sèrie i mostra el log a sota."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        panels = QHBoxLayout()
        panels.setSpacing(12)
        panels.addWidget(self._build_logada(), 1)
        panels.addWidget(self._build_nologada(), 1)
        root.addLayout(panels)

        # Status + log
        self._status = QLabel("Llest")
        self._status.setObjectName("scrapingStatus")
        root.addWidget(self._status)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 10))
        self._log.setObjectName("scrapingLog")
        root.addWidget(self._log, stretch=1)

        controls = QHBoxLayout()
        clear_btn = QPushButton("Netejar log")
        clear_btn.clicked.connect(self._log.clear)
        controls.addStretch()
        controls.addWidget(clear_btn)
        root.addLayout(controls)

    def _build_logada(self) -> QFrame:
        frame, lay = _panel("🔐  Logada — requereix login")

        login_btn = QPushButton("🔑  Re-login (Chromium)")
        login_btn.setToolTip("Obre Chromium per fer login (resol captcha manualment)")
        login_btn.setMinimumHeight(40)
        login_btn.clicked.connect(lambda: self._run([("Login", [*FCB, "login"])]))
        lay.addWidget(login_btn)

        lay.addWidget(QLabel("Rànquing + partides (games):"))
        self._rb_recent = QRadioButton("Només el rànquing recent")
        self._rb_recent.setChecked(True)
        self._rb_all = QRadioButton("Reimport històric complet")
        grp = QButtonGroup(self)
        grp.addButton(self._rb_recent)
        grp.addButton(self._rb_all)
        lay.addWidget(self._rb_recent)
        lay.addWidget(self._rb_all)

        run_btn = QPushButton("▶  Executar reingesta logada")
        run_btn.setMinimumHeight(40)
        run_btn.clicked.connect(self._run_logada)
        lay.addWidget(run_btn)
        lay.addStretch()
        return frame

    def _build_nologada(self) -> QFrame:
        frame, lay = _panel("🌐  No logada — pàgines públiques")

        self._cb_lliga = QCheckBox("Lliga 3 bandes (encontres + promocions → games/pendents)")
        self._cb_copa = QCheckBox("Copa")
        self._cb_opens = QCheckBox("Opens / competicions individuals (resultats)")
        self._cb_oprank = QCheckBox("Rànquing d'opens (en directe)")
        for cb in (self._cb_lliga, self._cb_copa):
            cb.setChecked(True)
            lay.addWidget(cb)

        # Opens: igual que la part logada, tria recent vs reimport històric complet.
        self._cb_opens.setChecked(True)
        lay.addWidget(self._cb_opens)
        opens_scope = QHBoxLayout()
        opens_scope.addSpacing(22)
        self._rb_opens_recent = QRadioButton("Només la temporada actual")
        self._rb_opens_recent.setChecked(True)
        self._rb_opens_all = QRadioButton("Reimport històric complet")
        opens_grp = QButtonGroup(self)
        opens_grp.addButton(self._rb_opens_recent)
        opens_grp.addButton(self._rb_opens_all)
        opens_scope.addWidget(self._rb_opens_recent)
        opens_scope.addWidget(self._rb_opens_all)
        opens_scope.addStretch()
        lay.addLayout(opens_scope)
        self._cb_opens.toggled.connect(self._rb_opens_recent.setEnabled)
        self._cb_opens.toggled.connect(self._rb_opens_all.setEnabled)

        self._cb_oprank.setChecked(True)
        lay.addWidget(self._cb_oprank)

        # Validació del PDF oficial d'opens (FCB) contra el rànquing calculat.
        # No ingesta res: baixa el PDF fresc (--force refresca la cache d'1h) i
        # mostra el diff (posicions, punts, penalitzacions -20, absents).
        opens_diff_btn = QPushButton("🔍  Diff PDF oficial d'opens vs calculat")
        opens_diff_btn.setToolTip(
            "Baixa el PDF oficial d'opens 3B de la FCB (fresc) i el compara amb el "
            "rànquing calculat. No publica res; només informa de discrepàncies."
        )
        opens_diff_btn.clicked.connect(
            lambda: self._run([
                ("Diff PDF oficial d'opens vs calculat",
                 [*OPENS, "diff-official", "--force"]),
            ])
        )
        lay.addWidget(opens_diff_btn)

        copa_row = QHBoxLayout()
        copa_row.addWidget(QLabel("Edició Copa:"))
        self._copa_edicio = QSpinBox()
        self._copa_edicio.setRange(1, 99)
        self._copa_edicio.setValue(7)
        copa_row.addWidget(self._copa_edicio)
        copa_row.addStretch()
        lay.addLayout(copa_row)

        self._cb_publish = QCheckBox("📤  Publica al núvol en acabar (Supabase)")
        self._cb_publish.setChecked(True)
        lay.addWidget(self._cb_publish)

        run_btn = QPushButton("▶  Scrapejar seleccionats")
        run_btn.setMinimumHeight(40)
        run_btn.clicked.connect(self._run_nologada)
        lay.addWidget(run_btn)

        pub_btn = QPushButton("📤  Només publicar al núvol")
        pub_btn.setMinimumHeight(36)
        pub_btn.clicked.connect(lambda: self._run(self._publish_steps()))
        lay.addWidget(pub_btn)
        lay.addStretch()
        return frame

    # ---------- comandes ----------

    def _run_logada(self) -> None:
        if self._rb_all.isChecked():
            steps = [
                ("Reimport històric (clubs + rànquings + entrades)",
                 [*FCB, "import-temporada", "--historical"]),
            ]
        else:
            steps = [
                ("Sync rànquings nous", [*FCB, "sync"]),
                ("Backfill partides Tres Bandes (rànquing actual)",
                 [*FCB, "backfill", "1"]),
            ]
        self._run(steps)

    def _run_nologada(self) -> None:
        steps: list[tuple[str, list[str]]] = []
        if self._cb_opens.isChecked():
            if self._rb_opens_all.isChecked():
                # Reimport històric: totes les temporades. ingest_open_games recorre
                # tots els torneigs de la taula, així que en treu també els històrics.
                steps.append(("Ingest individuals — TOT l'històric",
                              [*FCB, "ingest-individuals", "--historical"]))
                steps.append(("Resultats reals d'opens (torneig_partides)",
                              [*UV, "python", "scripts/ingest_open_games.py"]))
                steps.append(("Scrape historical opens (fcb_opens)", [*OPENS, "scrape-historical"]))
                steps.append(("Scrape current opens (fcb_opens)", [*OPENS, "scrape-current-opens"]))
            else:
                steps.append(("Ingest individuals (opens/catalans)", [*FCB, "ingest-individuals"]))
                steps.append(("Resultats reals d'opens (torneig_partides)",
                              [*UV, "python", "scripts/ingest_open_games.py"]))
                steps.append(("Scrape current opens (fcb_opens)", [*OPENS, "scrape-current-opens"]))
        if self._cb_oprank.isChecked():
            steps.append(("Rànquing d'opens en directe (open_live)", [*FCB, "publish-live-opens"]))
        if self._cb_copa.isChecked():
            steps.append((f"Ingest Copa (edició {self._copa_edicio.value()})",
                          [*FCB, "ingest-copa", str(self._copa_edicio.value())]))
        if self._cb_lliga.isChecked():
            steps.append(("Lliga 3B → games/pendents (fcbillar ingest-lliga)",
                          [*FCB, "ingest-lliga", "36"]))
            steps.append(("Lliga 3B → classificacions (fcb_opens)",
                          [*OPENS, "scrape-lliga", "36", "--full"]))
        if self._cb_publish.isChecked():
            steps.extend(self._publish_steps())
        if not steps:
            self._append("⚠ No has seleccionat res.")
            return
        self._run(steps)

    def _publish_steps(self) -> list[tuple[str, list[str]]]:
        return [
            ("Publica fcbillar a Supabase", [*FCB, "publish-cloud"]),
            ("Sync fcb_opens a Supabase", [*OPENS, "supabase-sync"]),
        ]

    # ---------- cua seqüencial ----------

    def _run(self, steps: list[tuple[str, list[str]]]) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._append("⚠ Ja hi ha una seqüència corrent. Espera que acabi.")
            return
        self._queue = list(steps)
        self._run_next()

    def _run_next(self) -> None:
        if not self._queue:
            self._status.setText("Llest. Seqüència acabada.")
            self._append("\n=== SEQÜÈNCIA ACABADA ===\n")
            return
        label, args = self._queue.pop(0)
        self._append(f"\n=== {label} ===")
        self._append(f"$ {' '.join(args)}")
        self._status.setText(f"Corrent: {label}…  ({len(self._queue)} passos pendents)")
        self._worker = SubprocessWorker(args)
        self._worker.line_received.connect(self._append)
        self._worker.finished_with_code.connect(self._on_step_finished)
        self._worker.start()

    def _on_step_finished(self, code: int) -> None:
        self._append(f"--- {'OK' if code == 0 else f'FAIL (codi {code})'} ---")
        self._run_next()  # cada pas aïllat: continua encara que un falli

    # ---------- misc ----------

    def request_data(self) -> None:
        pass

    def _append(self, line: str) -> None:
        self._log.appendPlainText(line)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())
