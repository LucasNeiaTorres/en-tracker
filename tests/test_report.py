"""Testes do painel — o que o HTML tem de conter para o dia a dia funcionar.

O botão de WhatsApp é o transporte do prompt para o celular, que é onde a sessão
acontece. Se ele sair do template, o loop diário volta a depender de copiar 3 mil
caracteres entre máquinas.
"""

from __future__ import annotations

from english_tracker import config, report as report_mod
from english_tracker.analytics import build_report
from english_tracker.parser import parse_log

LOG = """DIA 01 — 02/09 — Tipo: D — Tema: apresentação
Erros: esqueci o -s na terceira pessoa
Palavras novas: to figure out
Nota do professor: "Barely."
"""


def relatorio():
    return build_report(parse_log(LOG))


def test_painel_tem_botao_de_whatsapp_e_o_prompt():
    html = report_mod.render(relatorio())
    assert 'id="whats"' in html
    assert "wa.me/" in html
    assert "You are my English teacher" in html, "o prompt tem de estar na página"


def test_numero_configurado_vai_para_o_botao():
    html = report_mod.render(relatorio(), whatsapp="5551999998888")
    assert 'data-numero="5551999998888"' in html
    assert "5551999998888" in html


def test_sem_numero_o_painel_explica_o_que_fazer():
    html = report_mod.render(relatorio(), whatsapp="")
    assert 'data-numero=""' in html
    assert "Conversar comigo mesmo" in html
    assert "ENGLISH_TRACKER_WHATSAPP" in html


def test_numero_e_normalizado_para_digitos(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_ENV", "+55 (51) 99999-8888")
    assert config.whatsapp_number() == "5551999998888"


def test_numero_pode_vir_do_arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_ENV", "")
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    (tmp_path / "whatsapp").write_text("55 51 99999-8888\n", encoding="utf-8")
    assert config.whatsapp_number() == "5551999998888"


def test_sem_numero_em_lugar_nenhum_devolve_vazio(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_ENV", "")
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    assert config.whatsapp_number() == ""


def test_dia_ilegivel_aparece_no_painel():
    """A anomalia tem de ser visível no HTML, não só no terminal."""
    log = LOG + """
DIA 02 — 03/09 — Tipo: T — Tema: dois
Erros: —
Palavras novas: —
Nota do professor: "—"
"""
    html = report_mod.render(build_report(parse_log(log)))
    assert "cell illegible" in html
    assert "ilegível" in html


# ——— quando republicar a semana ———

def test_pacote_ausente_e_pendencia():
    from english_tracker.report import _pendencia_pacote

    p = _pendencia_pacote(relatorio(), {})
    assert p["estado"] == "ausente"


def test_pacote_vencido_quando_o_dia_passou_do_ultimo():
    from datetime import date

    from english_tracker.report import _pendencia_pacote

    rep = relatorio()   # log de 1 dia: next_day == 2
    p = _pendencia_pacote(rep, {"em": date.today().isoformat(), "primeiro": 1, "ultimo": 1})
    assert p["estado"] == "vencido"
    assert "sem prompt" in p["texto"]


def test_pacote_velho_depois_de_uma_semana():
    from datetime import date, timedelta

    from english_tracker.report import _pendencia_pacote

    antigo = (date.today() - timedelta(days=8)).isoformat()
    p = _pendencia_pacote(relatorio(), {"em": antigo, "primeiro": 1, "ultimo": 9})
    assert p["estado"] == "velho"
    assert "8 dias" in p["texto"]


def test_pacote_recente_e_suficiente_nao_incomoda():
    from datetime import date

    from english_tracker.report import _pendencia_pacote

    p = _pendencia_pacote(
        relatorio(), {"em": date.today().isoformat(), "primeiro": 1, "ultimo": 9}
    )
    assert p["estado"] == "ok"
