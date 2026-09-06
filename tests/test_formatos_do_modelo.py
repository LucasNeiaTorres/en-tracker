"""Testes das formas que o professor (outra IA) realmente escreve.

Estes testes existem porque o parser antigo aceitava só uma forma do cabeçalho e
só o valor na mesma linha do rótulo. Cada caso aqui já quebrou o sistema em
silêncio, de dois jeitos:

- **cabeçalho torto:** a entrada nova desaparecia E a linha `Erros:` dela
  sobrescrevia os erros do dia anterior;
- **erro em lista:** o dia entrava como feito com zero erros, o que se lê como
  dia limpo — pior que buraco, porque buraco aparece em vermelho.

Se você mexer no parser, é aqui que se descobre se quebrou.
"""

from __future__ import annotations

from english_tracker.analytics import build_report
from english_tracker.parser import STATUS_SEM_CONTEUDO, parse_log

CABECALHOS = [
    ("data literal do molde", "DIA 07 - DD/MM - Tipo: R - Tema: revisão"),
    ("tipo por extenso", "DIA 07 — 09/09 — Tipo: Técnico — Tema: kafka"),
    ("tipo em inglês", "DAY 07 - 09/09 - Type: Tech - Topic: kafka"),
    ("data entre parênteses", "DIA 07 (09/09) — Tipo: T — Tema: kafka"),
    ("negrito markdown", "**DIA 07 — 09/09 — Tipo: T — Tema: kafka**"),
    ("cabeçalho markdown", "## DIA 07 — 09/09 — Tipo: T — Tema: kafka"),
    ("item de lista", "- DIA 07 — 09/09 — Tipo: T — Tema: kafka"),
    ("citação", "> DIA 07 — 09/09 — Tipo: T — Tema: kafka"),
    ("ordem trocada", "DIA 07 — Tema: kafka — Tipo: T"),
    ("sem separador", "DIA 07"),
    ("dois-pontos", "DIA 07: 09/09: Tipo: T: Tema: kafka"),
]


def test_todo_cabecalho_plausivel_e_lido():
    for nome, linha in CABECALHOS:
        entries = parse_log(f"{linha}\nErros: a; b\n")
        assert len(entries) == 1, f"cabeçalho perdido: {nome}"
        assert entries[0].day == 7, f"dia errado em: {nome}"
        assert entries[0].errors == ["a", "b"], f"erros perdidos em: {nome}"


def test_cabecalho_torto_nao_contamina_o_dia_anterior():
    """O modo de falha mais destrutivo do parser antigo."""
    texto = (
        "DIA 01 — 02/09 — Tipo: D — Tema: um\n"
        "Erros: erro do dia 1\n\n"
        "DIA 02 - DD/MM - Tipo: D - Tema: dois\n"
        "Erros: erro do dia 2\n"
    )
    entries = parse_log(texto)
    assert [e.day for e in entries] == [1, 2]
    assert entries[0].errors == ["erro do dia 1"]
    assert entries[1].errors == ["erro do dia 2"]


def test_erros_em_bullets():
    texto = (
        "DIA 07 — 09/09 — Tipo: T — Tema: kafka\n"
        "Erros:\n"
        '- "depends of" → "depends on"\n'
        "- esqueci o -s na terceira pessoa\n"
        "Palavras novas:\n"
        "- backoff\n"
        "- to retry\n"
    )
    entry = parse_log(texto)[0]
    # A seta separa o erro da forma certa: o rótulo é o erro, o resto é o verso
    # do cartão. Era assim que o log já vinha escrito, e é o que dá gabarito ao
    # flashcard sem ninguém inventar inglês.
    assert entry.errors == ['"depends of"', "esqueci o -s na terceira pessoa"]
    assert entry.versos['"depends of"'] == '"depends on"'
    assert entry.vocab == ["backoff", "to retry"]


def test_erros_em_lista_numerada():
    texto = "DIA 07 — 09/09 — Tipo: T — Tema: kafka\nErros:\n1. primeiro\n2) segundo\n"
    assert parse_log(texto)[0].errors == ["primeiro", "segundo"]


def test_rotulo_em_negrito():
    texto = "DIA 07 — 09/09 — Tipo: T — Tema: kafka\n**Erros:** a; b\n__Palavras novas:__ x, y\n"
    entry = parse_log(texto)[0]
    assert entry.errors == ["a", "b"]
    assert entry.vocab == ["x", "y"]


def test_lista_para_no_fim_da_lista():
    """Prosa depois dos bullets não entra na lista."""
    texto = (
        "DIA 07 — 09/09 — Tipo: T — Tema: kafka\n"
        "Erros:\n"
        "- a\n"
        "See you tomorrow!\n"
        "- isto não é mais item da lista\n"
    )
    assert parse_log(texto)[0].errors == ["a"]


def test_placeholder_do_molde_nao_vira_erro():
    texto = (
        "DIA 07 — 09/09 — Tipo: T — Tema: kafka\n"
        "Erros: <mistake>; <mistake>\n"
        "Palavras novas: <word>, <word>\n"
        'Nota do professor: "<one line>"\n'
    )
    entry = parse_log(texto)[0]
    assert entry.errors == []
    assert entry.vocab == []
    assert entry.note == ""
    # Nada aproveitado: não pode contar como sessão feita.
    assert entry.status == STATUS_SEM_CONTEUDO


def test_sessao_sem_conteudo_nao_conta_como_feita():
    texto = (
        "DIA 01 — 02/09 — Tipo: D — Tema: um\n"
        "Erros: erro de verdade\n\n"
        "DIA 02 — 03/09 — Tipo: T — Tema: dois\n"
        "Erros: —\n"
        "Palavras novas: —\n"
        'Nota do professor: "—"\n'
    )
    rep = build_report(parse_log(texto))
    assert rep.done_days == [1]
    assert rep.illegible_days == [2]
    assert rep.has_anomalies is True
    assert rep.next_day == 2, "o dia ilegível é o próximo a refazer"


def test_dia_fora_do_plano_nao_infla_estatistica():
    texto = (
        "DIA 01 — 02/09 — Tipo: D — Tema: um\n"
        "Erros: erro de verdade\n\n"
        "DIA 45 — 03/09 — Tipo: D — Tema: dia digitado errado\n"
        "Erros: erro que não deve contar; outro\n"
    )
    rep = build_report(parse_log(texto))
    assert rep.unknown_days == [45]
    assert rep.done_days == [1]
    assert rep.total_errors == 1, "erro de dia fora do plano não entra na conta"


def test_prosa_do_modelo_e_preservada():
    """O preâmbulo educado é ignorado na análise, mas não é jogado fora."""
    texto = (
        "DIA 07 — 09/09 — Tipo: T — Tema: kafka\n"
        "Great session today! Here is your summary:\n"
        "Erros: a\n"
    )
    entry = parse_log(texto)[0]
    assert entry.errors == ["a"]
    assert "Great session today" in entry.extra


def test_cabecalho_ilegivel_nao_contamina_e_nao_desaparece_calado():
    """Cabeçalho cujo dia não dá para ler fecha a entrada anterior de todo jeito."""
    texto = (
        "DIA 01 — 02/09 — Tipo: D — Tema: um\n"
        "Erros: erro do dia 1\n\n"
        "DIA 99999999 — Tipo: D\n"
        "Erros: erro do intruso\n"
    )
    entries = parse_log(texto)
    assert [e.day for e in entries] == [1]
    assert entries[0].errors == ["erro do dia 1"]


def test_dia_de_quatro_digitos_aparece_como_fora_do_plano():
    texto = "DIA 1234 — 02/09 — Tipo: D — Tema: erro de digitação\nErros: a\n"
    rep = build_report(parse_log(texto))
    assert rep.unknown_days == [1234]
    assert rep.done_days == []
