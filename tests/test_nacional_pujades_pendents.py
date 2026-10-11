"""Quins documents del magatzem de pas esperen ser processats."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "nacional_pujades", Path(__file__).parent.parent / "scripts" / "nacional_pujades.py"
)
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)


def test_pendent_es_el_pdf_que_encara_no_te_estat():
    claus = [
        "nacional-pujades/sant-adri/aaa.pdf",
        "nacional-pujades/sant-adri/aaa.meta.json",
        # Ja tractat (i amb el PDF encara per esborrar): no es torna a processar.
        "nacional-pujades/sant-adri/bbb.pdf",
        "nacional-pujades/sant-adri/bbb.meta.json",
        "nacional-pujades/sant-adri/bbb.estat.json",
        "nacional-pujades/monforte/ccc.pdf",
    ]
    assert P.pendents(claus) == [
        "nacional-pujades/monforte/ccc.pdf",
        "nacional-pujades/sant-adri/aaa.pdf",
    ]


def test_una_clau_que_no_te_la_forma_esperada_no_es_toca():
    claus = [
        "nacional-pujades/sant-adri/../../etc/passwd.pdf",
        "nacional-pujades/sant-adri/sub/altre.pdf",
        "nacional-pujades/SantAdri/ABC.pdf",
        "altres/sant-adri/aaa.pdf",
    ]
    assert P.pendents(claus) == []
