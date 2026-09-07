"""Testes da análise e do prompt.

A regra que estes testes protegem: o sistema nunca assume que uma sessão
foi registrada. Dia que o plano esperava e o log não tem é buraco, e buraco
tem que aparecer.
"""

from __future__ import annotations

from english_tracker import plan, prompt
from english_tracker.analytics import build_report, review_deck
from english_tracker.parser import parse_log

LOG = """DIA 01 — 02/09 — Tipo: D — Tema: apresentação
Erros: esqueci o -s na terceira pessoa; "I have 28 years"
Palavras novas: to figure out, kind of
Nota do professor: "Barely."

DIA 02 — 03/09 — Tipo: T — Tema: injeção de dependência
Erros: esqueci o -s na terceira pessoa; pronúncia de "architecture"
Palavras novas: boilerplate, under the hood
Nota do professor: "Upside down."

DIA 04 — 05/09 — Tipo: T — Tema: starters
Erros: Esqueci o -s na terceira pessoa; "depends of"
Palavras novas: classpath, to override
Nota do professor: "Still allergic to S."
"""


def relatorio():
    return build_report(parse_log(LOG))


def test_dia_faltando_e_detectado():
    rep = relatorio()
    assert rep.done_days == [1, 2, 4]
    assert rep.missing_days == [3]
    assert rep.has_gaps is True


def test_proximo_dia_e_o_primeiro_buraco():
    """Se o dia 3 ficou pra trás, é ele o próximo — não o 5."""
    assert relatorio().next_day == 3


def test_sequencia_quebra_no_buraco():
    rep = relatorio()
    assert rep.current_streak == 1   # só o dia 4
    assert rep.longest_streak == 2   # dias 1 e 2


def test_erros_agrupam_ignorando_maiuscula_e_acento():
    rep = relatorio()
    topo = rep.top_errors[0]
    assert topo.count == 3
    assert topo.days == [1, 2, 4]


def test_vocabulario_nao_duplica():
    rep = relatorio()
    palavras = [v.word for v in rep.vocab]
    assert len(palavras) == len(set(palavras)) == 6
    assert rep.vocab[0].first_day == 1


def test_log_vazio_aponta_para_o_dia_1():
    rep = build_report([])
    assert rep.next_day == 1
    assert rep.missing_days == []
    assert rep.total_sessions == 0


def test_prompt_embute_erros_recorrentes():
    texto = prompt.build(3, relatorio())
    assert "mistakes I keep repeating" in texto
    assert "esqueci o -s na terceira pessoa" in texto


def test_prompt_muda_conforme_o_tipo_do_dia():
    rep = relatorio()
    assert "NEWS day" in prompt.build(6, rep)      # dia 6 é N
    assert "TECH day" in prompt.build(9, rep)      # dia 9 é T
    assert "REVIEW day" in prompt.build(7, rep)    # dia 7 é R
    assert "EVERYDAY day" in prompt.build(5, rep)  # dia 5 é D


def test_prompt_tecnico_traz_a_trilha_da_semana():
    texto = prompt.build(9, relatorio())
    assert "Mensageria" in texto


def test_prompt_manda_imprimir_o_bloco_e_nao_confia_no_drive():
    """A instrução principal é IMPRIMIR o bloco, não salvá-lo.

    O acesso do Gemini ao Drive é de leitura — verificado na documentação do
    Google em 2026-09-07, e relatado pelo próprio Gemini ao Lucas. Um prompt que
    manda salvar, e só isso, produz um dia perdido cada vez que o modelo não
    consegue. Escrever no Drive continua no texto, mas como extra condicional.
    """
    texto = prompt.build(3, relatorio(), drive_file="meu-log")
    assert "meu-log" in texto
    assert "DIA 03" in texto
    assert "PRINT the summary block" in texto, "imprimir é a instrução principal"
    assert "the day is lost" in texto, "o modelo tem de saber o custo de omitir"
    assert "read-only" in texto, "dizer ao modelo que não conseguir é o esperado"
    assert "claiming you saved something you did not save" in texto


def test_plano_esta_integro():
    assert plan.TOTAL_DAYS == 30
    assert sorted(plan.PLAN) == list(range(1, 31))
    assert all(pd.kind in {"D", "T", "N", "R"} for pd in plan.PLAN.values())
    assert all(pd.topic for pd in plan.PLAN.values())


def test_baralho_de_revisao_prioriza_o_que_repete():
    deck = review_deck(relatorio(), size=3)
    assert deck[0] == "esqueci o -s na terceira pessoa"


def test_error_themes_e_deterministico():
    """Mesmo log, mesma ordem — mesmo em processos com hash seed diferente.

    A ordem vinha de iteração de `set` de strings, que muda a cada processo:
    o mesmo log gerava painéis diferentes.
    """
    import subprocess
    import sys

    codigo = (
        "from english_tracker.parser import parse_log;"
        "from english_tracker.analytics import build_report;"
        "print(build_report(parse_log(open('sample/english-log.md',"
        "encoding='utf-8').read())).error_themes)"
    )
    saidas = set()
    for seed in ("0", "1", "42", "7919"):
        env = {"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"}
        saidas.add(
            subprocess.run(
                [sys.executable, "-c", codigo],
                capture_output=True, text=True, env=env, check=True,
            ).stdout
        )
    assert len(saidas) == 1, f"ordem instável entre processos: {saidas}"


def test_prompt_leva_a_data_resolvida():
    """O molde tinha DD/MM literal, e cabeçalho com DD/MM o parser não lê."""
    from datetime import date

    texto = prompt.build(3, relatorio())
    assert "DD/MM" not in texto
    assert date.today().strftime("%d/%m") in texto


def test_prompt_exige_acrescentar_sem_reescrever():
    """A IA que ESCREVE o arquivo (quando alguma conseguir) pode substituí-lo em
    vez de acrescentar — e aí o log inteiro vira o dia de hoje. A exigência
    continua no texto mesmo agora que a escrita é opcional: ela vale para
    qualquer assistente que tenha a ferramenta, não só para o Gemini."""
    texto = prompt.build(3, relatorio())
    assert "Never replace or rewrite" in texto
