"""Testes da revisão espaçada.

A agenda não tem banco de dados: ela é derivada do log. Isso a torna barata e
frágil ao mesmo tempo — qualquer mudança no parser ou nos rótulos muda o
cronograma. É aqui que se descobre.

A regra que estes testes protegem: **ausência não promove**. Um erro que
simplesmente não reapareceu continua na fila; o que faz um item avançar é o
professor registrar `Acertos:` (ou `Reusou:`, para palavra). "Não errei" não é o
mesmo que "acertei" — e sem essa distinção a agenda mediria silêncio, não
aprendizado.
"""

from __future__ import annotations

from datetime import date, timedelta

from english_tracker import prompt
from english_tracker.analytics import INTERVALOS, build_report, deck
from english_tracker.parser import parse_log

HOJE = date.today()


def dia(n: int) -> str:
    """Data de n dias atrás, no formato do log."""
    return (HOJE - timedelta(days=n)).strftime("%d/%m")


def relatorio(log: str):
    return build_report(parse_log(log))


def item(rep, rotulo: str):
    todos = rep.revisao + rep.dominados
    achados = [i for i in todos if i.rotulo == rotulo]
    assert achados, f"item {rotulo!r} não está na agenda: {[i.rotulo for i in todos]}"
    return achados[0]


def test_erro_novo_volta_no_dia_seguinte():
    rep = relatorio(f"DIA 01 — {dia(0)} — Tipo: D — Tema: um\nErros: esqueci o -s\n")
    alvo = item(rep, "esqueci o -s")
    assert alvo.caixa == 0
    assert alvo.vence == HOJE + timedelta(days=INTERVALOS[0])


def test_acerto_afasta_o_item():
    log = (
        f"DIA 01 — {dia(5)} — Tipo: D — Tema: um\nErros: esqueci o -s\n\n"
        f"DIA 02 — {dia(0)} — Tipo: T — Tema: dois\nAcertos: esqueci o -s\n"
    )
    alvo = item(relatorio(log), "esqueci o -s")
    assert alvo.caixa == 1
    assert alvo.vence == HOJE + timedelta(days=INTERVALOS[1])


def test_erro_que_reaparece_volta_para_a_primeira_caixa():
    log = (
        f"DIA 01 — {dia(9)} — Tipo: D — Tema: um\nErros: esqueci o -s\n\n"
        f"DIA 02 — {dia(6)} — Tipo: T — Tema: dois\nAcertos: esqueci o -s\n\n"
        f"DIA 03 — {dia(3)} — Tipo: D — Tema: três\nAcertos: esqueci o -s\n\n"
        f"DIA 04 — {dia(0)} — Tipo: D — Tema: quatro\nErros: esqueci o -s\n"
    )
    alvo = item(relatorio(log), "esqueci o -s")
    assert alvo.caixa == 0, "errar de novo desfaz o progresso"
    assert alvo.vence == HOJE + timedelta(days=1)


def test_ausencia_nao_promove():
    """Erro de 10 dias atrás que nunca mais foi tocado continua vencido."""
    rep = relatorio(f"DIA 01 — {dia(10)} — Tipo: D — Tema: um\nErros: esqueci o -s\n")
    alvo = item(rep, "esqueci o -s")
    assert alvo.caixa == 0
    assert alvo.atraso(HOJE) == 9
    assert alvo in rep.vencidos


def test_palavra_nunca_reusada_fica_vencida():
    rep = relatorio(
        f"DIA 01 — {dia(8)} — Tipo: D — Tema: um\nPalavras novas: to roll out\n"
    )
    alvo = item(rep, "to roll out")
    assert alvo.tipo == "palavra"
    assert alvo.caixa == 0
    assert alvo.atraso(HOJE) > 0


def test_palavra_reusada_avanca():
    log = (
        f"DIA 01 — {dia(8)} — Tipo: D — Tema: um\nPalavras novas: backoff\n\n"
        f"DIA 02 — {dia(5)} — Tipo: T — Tema: dois\nReusou: backoff\n\n"
        f"DIA 03 — {dia(1)} — Tipo: D — Tema: três\nReusou: backoff\n"
    )
    alvo = item(relatorio(log), "backoff")
    assert alvo.caixa == 2
    assert alvo.vence == HOJE - timedelta(days=1) + timedelta(days=INTERVALOS[2])


def test_item_sai_da_fila_quando_domina():
    linhas = [f"DIA 01 — {dia(40)} — Tipo: D — Tema: um\nErros: esqueci o -s\n"]
    for numero in range(2, 2 + len(INTERVALOS)):
        linhas.append(
            f"DIA {numero:02d} — {dia(40 - numero * 2)} — Tipo: D — Tema: x\n"
            "Acertos: esqueci o -s\n"
        )
    rep = relatorio("\n".join(linhas))
    assert [i.rotulo for i in rep.dominados] == ["esqueci o -s"]
    assert not [i for i in rep.revisao if i.rotulo == "esqueci o -s"]


def test_acerto_casa_com_o_erro_mesmo_com_acento_e_caixa_diferentes():
    """O professor escreve como quiser; a agenda não pode criar item duplicado."""
    log = (
        f'DIA 01 — {dia(5)} — Tipo: D — Tema: um\nErros: Pronúncia de "architecture"\n\n'
        f"DIA 02 — {dia(0)} — Tipo: T — Tema: dois\nAcertos: pronuncia de architecture\n"
    )
    rep = relatorio(log)
    erros = [i for i in rep.revisao if i.tipo == "erro"]
    assert len(erros) == 1, f"deveria ser um item só: {[i.rotulo for i in erros]}"
    assert erros[0].caixa == 1


def test_dia_sem_data_e_cobrado_logo():
    rep = relatorio("DIA 01\nErros: sem data nenhuma\n")
    alvo = item(rep, "sem data nenhuma")
    assert alvo.vence is None
    assert alvo in rep.vencidos


def test_deck_respeita_o_tamanho_e_ordena_pelo_mais_atrasado():
    log = (
        f"DIA 01 — {dia(20)} — Tipo: D — Tema: um\nPalavras novas: antiga\n\n"
        f"DIA 02 — {dia(10)} — Tipo: D — Tema: dois\nPalavras novas: media\n\n"
        f"DIA 03 — {dia(2)} — Tipo: D — Tema: três\nPalavras novas: recente\n"
    )
    rep = relatorio(log)
    escolhidos = deck(rep, tamanho=2)
    assert len(escolhidos) == 2
    assert [i.rotulo for i in escolhidos] == ["antiga", "media"]


def test_deck_vazio_quando_nada_venceu():
    rep = relatorio(f"DIA 01 — {dia(0)} — Tipo: D — Tema: um\nErros: erro de hoje\n")
    assert deck(rep) == []


def test_dia_de_revisao_usa_a_agenda_no_prompt():
    log = (
        f"DIA 01 — {dia(12)} — Tipo: D — Tema: um\n"
        "Erros: erro esquecido\nPalavras novas: palavra esquecida\n"
    )
    texto = prompt.build(7, relatorio(log))
    assert "Due for review today" in texto
    assert "palavra esquecida" in texto
    assert "erro esquecido" in texto


def test_prompt_pede_acertos_e_reuso_com_a_regra():
    texto = prompt.build(1, relatorio(""))
    assert "Acertos:" in texto
    assert "Reusou:" in texto
    assert "spaced-repetition" in texto, "o professor tem de saber para que serve"


def test_painel_mostra_a_revisao_e_os_dominados():
    from english_tracker import report as report_mod

    log = f"DIA 01 — {dia(9)} — Tipo: D — Tema: um\nPalavras novas: esquecida\n"
    html = report_mod.render(relatorio(log))
    assert "Revisão de hoje" in html
    assert "esquecida" in html
    assert "vencido há" in html


# ——— pronúncia: o regime rígido tem de ser mensurável, não só declarado ———

def test_etiqueta_de_pronuncia_e_lida():
    from english_tracker.parser import parse_log as pl
    entrada = pl(f"DIA 01 — {dia(0)} — Tipo: T — Tema: x\nErros: [pron] queue; [gram] the informations\n")[0]
    assert entrada.errors == ["queue", "the informations"], "a etiqueta sai do rótulo"
    assert entrada.classes["queue"] == "pronúncia"
    assert entrada.classes["the informations"] == "gramática"


def test_classe_inferida_sem_etiqueta_no_log_antigo():
    """Log escrito antes da etiqueta existir continua sendo classificado."""
    from english_tracker.parser import classe_do_erro
    assert classe_do_erro('pronúncia de "architecture"') == "pronúncia"
    assert classe_do_erro('travei em "prejudicar"') == "fluência"
    assert classe_do_erro("ordem de adjetivos") == ""


def test_pronuncia_tem_intervalos_mais_curtos():
    from english_tracker.analytics import INTERVALOS_PRONUNCIA

    log = (
        f"DIA 01 — {dia(6)} — Tipo: T — Tema: x\nErros: [pron] queue; [gram] plurais\n\n"
        f"DIA 02 — {dia(3)} — Tipo: T — Tema: y\nAcertos: [pron] queue; [gram] plurais\n"
    )
    rep = relatorio(log)
    pron, gram = item(rep, "queue"), item(rep, "plurais")
    assert pron.classe == "pronúncia" and gram.classe == "gramática"
    assert pron.escala == INTERVALOS_PRONUNCIA
    assert pron.vence < gram.vence, "pronúncia volta antes, com a mesma caixa"


def test_deck_reserva_vagas_para_pronuncia():
    """Sem reserva, o passivo de vocabulário empurra a pronúncia para fora."""
    log = [f"DIA 01 — {dia(30)} — Tipo: D — Tema: x\n"
           "Palavras novas: uma, duas, tres, quatro, cinco, seis\n"]
    log.append(f"DIA 02 — {dia(2)} — Tipo: T — Tema: y\nErros: [pron] queue\n")
    rep = relatorio("\n".join(log))

    escolhidos = deck(rep, tamanho=5)
    assert any(i.classe == "pronúncia" for i in escolhidos), \
        "pronúncia de 2 dias não pode perder para vocabulário de 30"
    assert escolhidos[0].rotulo == "queue", "e vem primeiro"


def test_painel_conta_por_classe():
    from english_tracker import report as report_mod

    log = (f"DIA 01 — {dia(1)} — Tipo: T — Tema: x\n"
           "Erros: [pron] queue; [pron] receipt; [gram] plurais\n")
    rep = relatorio(log)
    assert rep.por_classe == {"pronúncia": 2, "gramática": 1}
    html = report_mod.render(rep)
    assert "Onde o inglês falha" in html
    assert "pronúncia" in html


def test_prompt_e_extremamente_rigido_com_pronuncia():
    texto = prompt.build(1, relatorio(""))
    # o procedimento, não só a intenção
    assert "PRONUNCIATION" in texto
    assert "close enough" in texto, "tem de proibir a saída fácil do modelo"
    assert "3 times" in texto
    assert "[pron]" in texto, "o erro tem de voltar etiquetado para a agenda"
    # o inventário específico de brasileiro
    for alvo in ("Epenthesis", "WORD STRESS", "queue", "/θ/"):
        assert alvo in texto, f"faltou policiar: {alvo}"


def test_gramatica_e_a_primeira_no_desempate_da_sessao():
    """A regra de desempate tem de estar escrita, senão o modelo escolhe sozinho."""
    texto = prompt.build(1, relatorio(""))
    assert "TWO ZERO-TOLERANCE REGIMES" in texto
    assert "correct the grammar first" in texto
    assert "GRAMMAR AND MEANING" in texto


def test_procedimento_de_gramatica_e_diferente_do_de_pronuncia():
    texto = prompt.build(1, relatorio(""))
    # gramática: o aluno PRODUZ, não repete — e produz uma segunda frase
    assert "make ME produce the corrected sentence" in texto
    assert "DIFFERENT sentence using the same rule" in texto
    # pronúncia: repetição motora
    assert "make me repeat the word 3 times" in texto


def test_prompt_cobra_significado_da_palavra_errada():
    texto = prompt.build(1, relatorio(""))
    assert "what the word I actually said MEANS" in texto
    assert "pretend" in texto and "intend" in texto


def test_etiqueta_lex_vira_vocabulario():
    from english_tracker.parser import parse_log as pl
    entrada = pl(f"DIA 01 — {dia(0)} — Tipo: T — Tema: x\nErros: [lex] support (apoiar) em vez de tolerate\n")[0]
    assert entrada.classes["support (apoiar) em vez de tolerate"] == "vocabulário"


def test_deck_reserva_vagas_para_gramatica_e_pronuncia():
    log = [f"DIA 01 — {dia(30)} — Tipo: D — Tema: x\n"
           "Palavras novas: uma, duas, tres, quatro, cinco, seis, sete\n",
           f"DIA 02 — {dia(2)} — Tipo: T — Tema: y\n"
           "Erros: [gram] terceira pessoa; [gram] plurais; [pron] queue\n"]
    escolhidos = deck(relatorio("\n".join(log)), tamanho=5)
    classes = [i.classe for i in escolhidos]
    assert classes.count("gramática") == 2, f"faltou vaga de gramática: {classes}"
    assert classes.count("pronúncia") == 1, f"faltou vaga de pronúncia: {classes}"


def test_inventario_encolhe_quando_o_log_aprende():
    """Prompt de 11 mil caracteres dilui instrução: o genérico sai quando há dado."""
    vazio = relatorio("")
    log = "\n".join(
        f"DIA {n:02d} — {dia(20 - n)} — Tipo: D — Tema: x\n"
        f"Erros: [gram] erro {n}; [pron] palavra {n}\n"
        for n in range(1, 7)
    )
    cheio = relatorio(log)
    assert cheio.total_sessions >= 5

    curto = prompt.build(10, cheio)
    completo = prompt.build(10, cheio, completo=True)
    assert len(curto) < len(completo)
    assert "My recorded pronunciation offenders" in curto
    assert "Epenthesis: adding a vowel" not in curto, "o inventário genérico sai"
    assert "Epenthesis: adding a vowel" in completo
    # e com log vazio o genérico entra sozinho
    assert "Epenthesis: adding a vowel" in prompt.build(1, vazio)


# ——— o pacote da semana: tirar o notebook do caminho diário ———

def test_pacote_traz_os_proximos_dias_a_partir_do_buraco():
    log = (
        f"DIA 01 — {dia(3)} — Tipo: D — Tema: um\nErros: a\n\n"
        f"DIA 02 — {dia(2)} — Tipo: T — Tema: dois\nErros: b\n"
    )
    rep = relatorio(log)
    blocos = prompt.pacote_dias(rep, dias=4)
    assert [b["dia"] for b in blocos] == [3, 4, 5, 6]
    assert all(b["prompt"].startswith("You are my English teacher") for b in blocos)
    assert blocos[0]["tema"], "cada bloco leva o tema do plano"


def test_pacote_nao_passa_do_fim_do_plano():
    from english_tracker import plan

    log = "\n".join(
        f"DIA {n:02d} — {dia(30 - n)} — Tipo: D — Tema: x\nErros: e{n}\n"
        for n in range(1, plan.TOTAL_DAYS)
    )
    blocos = prompt.pacote_dias(relatorio(log), dias=7)
    assert [b["dia"] for b in blocos] == [plan.TOTAL_DAYS]


def test_pacote_avisa_que_o_conteudo_envelhece():
    """O tema está sempre certo; o histórico e a agenda, não. Isso tem de estar escrito."""
    texto = prompt.pacote(relatorio(f"DIA 01 — {dia(1)} — Tipo: D — Tema: x\nErros: a\n"), dias=3)
    assert "PROMPTS DOS DIAS" in texto
    assert "mais desatualizados" in texto
    assert texto.count("You are my English teacher") == 3, "um prompt por dia"
    assert "Regenere o pacote" in texto


def test_pacote_de_plano_concluido():
    from english_tracker import plan

    log = "\n".join(
        f"DIA {n:02d} — {dia(40 - n)} — Tipo: D — Tema: x\nErros: e{n}\n"
        for n in range(1, plan.TOTAL_DAYS + 1)
    )
    rep = relatorio(log)
    assert rep.next_day is None
    assert prompt.pacote_dias(rep, dias=7) == []
    assert "concluído" in prompt.pacote(rep, dias=7)


def test_pacote_leva_a_revisao_para_o_celular():
    """A revisão tem de sobreviver ao notebook desligado."""
    log = (
        f"DIA 01 — {dia(20)} — Tipo: T — Tema: x\n"
        'Erros: [pron] queue → som de "kyoo"; [gram] plurais → "the information"\n'
        "Palavras novas: backoff = espera exponencial\n"
    )
    texto = prompt.pacote(relatorio(log), dias=3)

    assert "REVISÃO —" in texto
    assert "PRONÚNCIA" in texto
    assert "queue" in texto and 'som de "kyoo"' in texto, "o verso vai junto"
    assert "backoff  =  espera exponencial" in texto
    assert "vencido há" in texto
    # e o aviso que impede a leitura errada do que ali está
    assert '"Acertos:"' in texto


def test_revisao_do_pacote_usa_a_mesma_selecao_do_deck():
    """Duas ordenações para o mesmo conceito seria defeito — inclusive as vagas."""
    log = [
        f"DIA 01 — {dia(30)} — Tipo: D — Tema: x\n"
        "Palavras novas: uma, duas, tres, quatro, cinco, seis, sete, oito\n",
        f"DIA 02 — {dia(2)} — Tipo: T — Tema: y\nErros: [pron] queue\n",
    ]
    rep = relatorio("\n".join(log))
    texto = prompt.pacote(rep, dias=2)
    assert "PRONÚNCIA" in texto, "a pronúncia não pode perder para o passivo de vocabulário"
    assert "queue" in texto


def test_pacote_sem_nada_vencido_nao_inventa_secao():
    log = f"DIA 01 — {dia(0)} — Tipo: D — Tema: x\nErros: erro de hoje\n"
    texto = prompt.pacote(relatorio(log), dias=2)
    assert "REVISÃO —" not in texto
    assert "You are my English teacher" in texto
