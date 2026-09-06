"""Testes do parser — a parte mais frágil do sistema.

O professor escreve em linguagem natural, em duas línguas, com formatação
irregular. Se você mexer no parser, rode isto antes de confiar no resultado.

    python -m pytest tests/ -q
"""

from __future__ import annotations

from datetime import date

from english_tracker.parser import (
    Entry,
    normalize,
    parse_log,
    parse_session,
    remove_day,
    render_entry,
    set_verso,
)

CANONICO = """DIA 01 — 02/09 — Tipo: D — Tema: apresentação pessoal
Erros: "I have 28 years" → "I'm 28"; esqueci o -s na terceira pessoa
Palavras novas: to figure out, I'd say
Nota do professor: "You survived. Barely."
"""


def test_formato_canonico():
    entries = parse_log(CANONICO)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.day == 1
    assert entry.kind == "D"
    assert entry.topic == "apresentação pessoal"
    assert entry.when == date(date.today().year, 9, 2)
    assert len(entry.errors) == 2
    assert entry.vocab == ["to figure out", "I'd say"]
    assert entry.note == "You survived. Barely."


def test_rotulos_em_ingles():
    """O Gemini costuma responder em inglês mesmo com o prompt pedindo o formato."""
    texto = """DAY 3 - 04/09 - Type: T - Topic: dependency injection
Errors: forgot third person -s; "explain about" -> "explain"
New words: loosely coupled, boilerplate
Teacher's note: "Rough."
"""
    entry = parse_log(texto)[0]
    assert entry.day == 3
    assert entry.kind == "T"
    assert entry.topic == "dependency injection"
    assert entry.errors == ["forgot third person -s", '"explain about"']
    assert entry.versos['"explain about"'] == '"explain"', "o `->` também separa"
    assert entry.note == "Rough."


def test_cabecalho_incompleto():
    """Sem data, sem tipo, sem tema — ainda assim a entrada conta como dia feito."""
    entry = parse_log("DIA 12\nErros: ordem de adjetivos\n")[0]
    assert entry.day == 12
    assert entry.kind is None
    assert entry.topic == ""
    assert entry.errors == ["ordem de adjetivos"]


def test_linhas_desconhecidas_sao_ignoradas():
    texto = """DIA 02 — 03/09 — Tipo: T — Tema: beans
Great session today! Here is your summary:
Erros: pronúncia de "architecture"
Random line the model decided to add
Palavras novas: under the hood
"""
    entry = parse_log(texto)[0]
    assert entry.errors == ['pronúncia de "architecture"']
    assert entry.vocab == ["under the hood"]


def test_dia_repetido_a_ultima_entrada_vence():
    texto = CANONICO + "\nDIA 01 — 02/09 — Tipo: D — Tema: refeito\nErros: nenhum\n"
    entries = parse_log(texto)
    assert len(entries) == 1
    assert entries[0].topic == "refeito"


def test_entrada_vazia_nao_quebra():
    assert parse_log("") == []
    assert parse_log("qualquer texto sem cabeçalho") == []


def test_render_volta_ao_formato_canonico():
    original = parse_log(CANONICO)[0]
    reparsed = parse_log(render_entry(original))[0]
    assert reparsed.day == original.day
    assert reparsed.errors == original.errors
    assert reparsed.vocab == original.vocab
    assert reparsed.note == original.note


def test_normalize_agrupa_variacoes():
    """É isto que faz 'erros que se repetem' funcionar."""
    assert normalize('Pronúncia de "architecture"') == normalize(
        'pronuncia de architecture'
    )
    assert normalize("Esqueci o -s!") == normalize("esqueci o s")


def test_render_com_campos_vazios():
    entry = Entry(day=7, when=date(2026, 9, 8), kind="R", topic="revisão")
    texto = render_entry(entry)
    assert "DIA 07" in texto
    assert parse_log(texto)[0].day == 7


def test_parse_session_aceita_resumo_sem_cabecalho():
    texto = 'Erros: a; b\nPalavras novas: x, y\nNota do professor: "ouch"'
    entry = parse_session(texto, 5)
    assert entry is not None
    assert entry.day == 5
    assert entry.errors == ["a", "b"]
    assert entry.vocab == ["x", "y"]


def test_parse_session_forca_o_dia_pedido():
    """Se o professor errou o número no texto, vale o dia que se está registrando."""
    entry = parse_session("DIA 09 — Tipo: T — Tema: kafka\nErros: a", 5)
    assert entry.day == 5
    assert entry.topic == "kafka"


def test_parse_session_devolve_none_para_prosa():
    assert parse_session("falei de kafka e travei em prejudicar", 5) is None


def test_remove_day_tira_so_o_dia_pedido():
    log = (
        "DIA 01 — 02/09 — Tipo: D — Tema: um\n"
        "Erros: erro do dia 1\n\n"
        "DIA 02 — 03/09 — Tipo: T — Tema: dois\n"
        "Erros: erro do dia 2\n"
        'Nota do professor: "nota do dia 2"\n\n'
        "DIA 03 — 04/09 — Tipo: D — Tema: três\n"
        "Erros: erro do dia 3\n"
    )
    novo, removidas = remove_day(log, 2)
    assert removidas == 1
    assert [e.day for e in parse_log(novo)] == [1, 3]
    assert "nota do dia 2" not in novo
    assert "erro do dia 1" in novo and "erro do dia 3" in novo


def test_remove_day_preserva_a_prosa_dos_outros_dias():
    """O que o parser não entende, ele não apaga."""
    log = (
        "Preâmbulo educado que ninguém pediu.\n\n"
        "DIA 01 — 02/09 — Tipo: D — Tema: um\n"
        "Great session! Here is your summary:\n"
        "Erros: erro do dia 1\n\n"
        "DIA 02 — 03/09 — Tipo: T — Tema: dois\n"
        "Erros: erro do dia 2\n"
    )
    novo, _ = remove_day(log, 2)
    assert "Preâmbulo educado" in novo
    assert "Great session!" in novo


def test_remove_day_de_dia_inexistente_nao_muda_nada():
    log = "DIA 01 — 02/09 — Tipo: D — Tema: um\nErros: a\n"
    novo, removidas = remove_day(log, 9)
    assert removidas == 0
    assert parse_log(novo)[0].errors == ["a"]


def test_remove_day_apaga_as_duas_entradas_de_um_dia_repetido():
    log = (
        "DIA 01 — 02/09 — Tipo: D — Tema: um\nErros: a\n\n"
        "DIA 01 — 02/09 — Tipo: D — Tema: refeito\nErros: b\n\n"
        "DIA 02 — 03/09 — Tipo: T — Tema: dois\nErros: c\n"
    )
    novo, removidas = remove_day(log, 1)
    assert removidas == 2
    assert [e.day for e in parse_log(novo)] == [2]


def test_set_verso_escreve_no_log_preservando_o_resto():
    log = (
        "DIA 09 — 11/09 — Tipo: T — Tema: kafka\n"
        'Erros: [gram] esqueci o -s → "He works here"; [pron] queue; [gram] ordem\n'
        "Palavras novas: backoff, to retry\n"
    )
    novo, escreveu = set_verso(log, "queue", 'som de "kyoo"')
    assert escreveu
    entrada = parse_log(novo)[0]
    assert entrada.versos["queue"] == 'som de "kyoo"'
    assert entrada.versos["esqueci o -s"] == '"He works here"', "o verso do professor fica"
    assert entrada.errors == ["esqueci o -s", "queue", "ordem"]
    assert entrada.classes["queue"] == "pronúncia", "a etiqueta sobrevive"
    assert "backoff" in novo and "to retry" in novo


def test_set_verso_usa_o_separador_certo_para_palavra():
    log = "DIA 01 — 02/09 — Tipo: D — Tema: x\nPalavras novas: backoff, to retry\n"
    novo, escreveu = set_verso(log, "backoff", "espera exponencial")
    assert escreveu
    assert "backoff = espera exponencial" in novo
    assert parse_log(novo)[0].vocab == ["backoff", "to retry"]


def test_set_verso_nunca_sobrescreve_o_do_professor():
    log = 'DIA 01 — 02/09 — Tipo: D — Tema: x\nErros: [gram] plurais → "the information"\n'
    novo, escreveu = set_verso(log, "plurais", "outra coisa")
    assert not escreveu
    assert novo == log


def test_set_verso_recusa_item_inexistente_e_verso_vazio():
    log = "DIA 01 — 02/09 — Tipo: D — Tema: x\nErros: plurais\n"
    assert set_verso(log, "não existe", "x") == (log, False)
    assert set_verso(log, "plurais", "   ") == (log, False)
