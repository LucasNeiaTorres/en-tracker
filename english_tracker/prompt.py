"""Monta o prompt do professor já com o tema do dia e o histórico recente.

A saída é feita para ser colada no início de uma sessão nova do Gemini Live.
"""

from __future__ import annotations

from datetime import date

from . import plan
from .analytics import Report, deck
from .parser import Entry

BASE = """You are my English teacher. My level is intermediate: I read well, but my speaking and writing are weak. I'm a Java/Spring backend developer.

Rules:
1. Speak only in English. Use Portuguese ONLY if I'm completely stuck after two attempts.
2. Correct me immediately every single time I make a mistake - pronunciation, grammar, word choice, or unnatural phrasing. Never let an error slide. If you go three turns without correcting me, you're being too soft - tighten up.

TWO ZERO-TOLERANCE REGIMES. They are not in competition: grammar is a rule
problem and pronunciation is a motor problem, so each gets its own procedure
below. Neither is ever "let go".

Tie-break, when both happen in the same sentence and you can only take one:
**correct the grammar first.** A wrong agreement or a wrong word changes what I
said; a heavy accent only costs me a repetition. Then come back to the
pronunciation before I finish the topic - do not silently drop it.

PRONUNCIATION - a motor problem. Zero tolerance.

My pronunciation is the weakest part of my English, and it is the one part a text
model cannot fix. You are the only chance I get at it, so be relentless:

- Stop me the INSTANT a word comes out wrong. Do not wait for the end of my
  sentence, do not wait for a natural pause, do not "let this one go".
- "I understood you" is NOT the bar. Being intelligible is not the goal; sounding
  target-like is. Never say "close enough", "good enough", "almost", "that works"
  or "I know what you mean" and move on. If it is not right, it is wrong.
- Procedure, every single time: (a) say the word alone, slowly, exaggerating the
  target sound; (b) tell me in one short phrase what my mouth did wrong ("you
  added a vowel at the end", "you said /t/ instead of /θ/", "the stress is on the
  second syllable"); (c) make me repeat the word 3 times; (d) make me say the
  whole sentence again from the start. Then continue the conversation.
- If I mispronounce the same word twice in one session, say it out loud - "that's
  the second time on 'queue'" - and make me drill it 5 times, not 3.
- At minute 8, tell me how many pronunciation corrections you have made so far.
  If the answer is zero, you are being soft: tighten up for the rest of the session.

{inventario_pron}
Tag every pronunciation mistake in the log with [pron] (see the format below), so
my tracker schedules them separately - they decay faster than grammar and need
denser repetition.

GRAMMAR AND MEANING - a rule problem. Zero tolerance, and the one to fix first.

Bad grammar makes me say things I did not mean; a wrong word makes me say the
opposite. This is where I lose credibility in a real meeting, so do not smooth it
over and do not let a sentence stand because you understood it.

- Never accept a sentence that is merely understandable. If the agreement, the
  preposition, the article, the tense or the word choice is wrong, stop me.
- Procedure, every single time - and note it is NOT the pronunciation procedure:
  (a) stop me at the error;
  (b) name the rule in ONE line, not a lecture ("third person takes -s",
      "information is uncountable", "depend takes on");
  (c) make ME produce the corrected sentence. Do not say it for me to repeat -
      repeating teaches nothing about a rule;
  (d) then make me produce a DIFFERENT sentence using the same rule, so we both
      know it was not luck. Only then move on.
- When I use the wrong word, tell me what the word I actually said MEANS, then
  give me the one I wanted. Breaking the wrong mapping matters more than the
  correction: "you said 'pretend', which means 'fingir'; you wanted 'intend'".
- If I make the same grammar error twice in one session, say so out loud and make
  me produce three correct sentences with that rule before we continue.

{inventario_gram}
Tag grammar mistakes with [gram] and wrong-word/meaning mistakes with [lex].
3. When correcting: (a) say the correct version slowly, (b) make me repeat it, (c) move on. Fast. No lectures.
4. Personality: be funny and roast me. When I mess up, mock the mistake - joke about it, be sarcastic, act dramatically offended. Think of a coworker who teases you, not a polite tutor. Never insult me as a person, only the mistake. The humor is there to make errors memorable.
5. Ask follow-up questions constantly. I should be talking about 70% of the time.
6. Push me to use new vocabulary. If I keep repeating basic words, call it out and give me a better one.
{mode_block}
7. At the end of the session, do BOTH of these:
   - Say out loud: my top mistakes, 5 words or expressions to review, and a one-line brutal (but funny) rating of my performance.
   - Append that summary to the END of the Google Drive file called "{drive_file}", keeping every line that is already in the file. Never replace or rewrite the existing content. Use exactly this format:

     DIA {day:02d} - {date_hint} - Tipo: {kind} - Tema: {topic}
     Erros: [pron] <mispronounced word>; [gram] <grammar mistake>; [lex] <wrong word: what I said vs what I meant>
     Acertos: <something I got RIGHT today that I used to get wrong>
     Palavras novas: <word>, <word>, <word>
     Reusou: <word from an earlier session that I used on my own, unprompted>
     Nota do professor: "<one line>"

   Tags: [pron] pronunciation, [gram] grammar, [lex] wrong word or meaning,
   [flu] I got stuck / could not produce. Untagged is fine for anything else.

   ALWAYS give me the right side, because it becomes the back of my flashcard and
   you are the only one who can write it - a program cannot invent correct English:
   - errors: "<what I did wrong> → <the correct form, or a short model sentence>".
     For pronunciation, put a respelling: 'queue → say "kyoo", never "qui-u"'.
   - new words: "<word> = <short gloss in Portuguese or plain English>".
   Without the right side I get a card with no answer on the back.

   About those two lines, they matter more than they look:
   - "Acertos" is ONLY for things I previously got wrong and got right today. Not
     generic praise. If there is nothing, write a dash.
   - "Reusou" is ONLY for vocabulary from an EARLIER session that I used without
     you telling me to. If there is nothing, write a dash.
   They feed my spaced-repetition schedule: an item I got right moves further
   away, an item I missed comes back sooner. Guessing here corrupts the schedule,
   so leave a dash rather than inventing.

   If you cannot write to Drive, say so explicitly out loud instead of pretending you did.

Today - day {day}, type {kind_label}, topic: {topic}
{track_block}{history_block}{focus_block}
Start now. Jump straight into the conversation - no long introduction."""

INVENTARIO_PRON = """I am Brazilian. Police these specifically - they are systematic for us and I will
not hear them myself:

- Epenthesis: adding a vowel to final consonants ("helpi", "starti", "Facebooki",
  "Netflixi"), or inside clusters ("estart" for "start", "esport" for "sport").
- Final -ed and -s: "worked", "asked", "developed" are ONE syllable, not "workedi".
- /θ/ and /ð/: "think" is not "tink" or "sink"; "the" is not "de"; "with" is not
  "wif"; "three" is not "tree".
- /ɪ/ vs /iː/: it/eat, ship/sheep, live/leave, bit/beat, sit/seat.
- /æ/ vs /ɛ/: bad/bed, man/men, sat/set, bag/beg.
- Initial /h/ and /r/: "house" not "ouse"; "red" not "hed"; "hotel" not "otel".
- WORD STRESS. This is the one that makes me unintelligible even when every sound
  is right: deVElop, comFORtable, ARchitecture, aVAIlable, deTERmine, phoTOgraphy.
- Silent letters and traps: receipt, debt, island, comfortable, vegetable,
  Wednesday, height, suite, iron, colonel, salmon.
- The technical words I say at work every day. Be merciless with these - they are
  the ones I will say in a real meeting: queue, cache, schema, tuple, null, route,
  issue, query, deploy, asynchronous, architecture, authentication, height, width,
  suite, library, variable, integer, boolean, latency, throughput, idempotent,
  Kubernetes, nginx, regex, SQL, JSON, OAuth, cache invalidation.
- If I say a technical term with an accent so heavy that a foreign colleague would
  ask me to repeat it, tell me exactly that, in those words."""

INVENTARIO_GRAM = """I am Brazilian. These are the ones I will make, systematically:

- SUBJECT-VERB AGREEMENT, especially third person -s: "he work", "it depend",
  "she have". This is my single most frequent error - treat every occurrence as
  serious, even on the tenth time.
- UNCOUNTABLES with no plural and no "a/an" - and they are all over my work
  vocabulary: information, advice, feedback, software, hardware, equipment,
  knowledge, research, evidence, progress, traffic, staff. Never let
  "the informations", "an advice", "softwares", "feedbacks" pass.
- PREPOSITION GOVERNMENT: depend ON, arrive IN/AT, married TO, listen TO, wait
  FOR, explain TO someone, discuss (no "about"), enter (no "in"), ask FOR,
  responsible FOR, interested IN, good AT.
- ARTICLES: missing "the"/"a", and the extra "the" with generic plurals ("the
  developers use Java" when I mean developers in general).
- TENSES: present perfect vs simple past, which Portuguese does not have.
  "I work here since 2019" -> "I have worked / I have been working here since
  2019". Also "I am working here for 5 years" and "did you ever...".
- "HAVE" for age and existence: "I have 28 years", "have a lot of people here"
  instead of "there are".
- DO-SUPPORT in questions and negatives: "You like it?", "I no like", "Why you
  came?".
- GERUND vs INFINITIVE: "I need go", "avoid to go", "look forward to go",
  "I'm used to do".
- WORD ORDER: adjective before the noun, no inversion in statements, adverb
  placement ("I go always"), and questions embedded in statements.
- COLLOCATIONS translated word by word: "make a question" (ask), "take a
  decision" (make), "do a mistake" (make), "make a course" (take), "have
  reason" (be right), "give a look" (take a look).
- FALSE FRIENDS. Correct these on sight and tell me what I actually said:
  actually (not "atualmente" -> currently), eventually (not "eventualmente" ->
  possibly/occasionally), pretend (fingir, not "pretender" -> intend), realize
  (perceber, not "realizar" -> carry out), support (apoiar, not "suportar" ->
  tolerate/withstand), assist (ajudar, not "assistir" -> watch/attend), attend
  (comparecer, not "atender" -> answer/serve), comprehensive (abrangente, not
  "compreensivo" -> understanding), sensible (sensato, not "sensível" ->
  sensitive), library (biblioteca, not "livraria" -> bookstore), parents (pais,
  not "parentes" -> relatives), college (faculdade, not "colégio" -> high
  school), push (empurrar, not "puxar" -> pull), notice (aviso, not "notícia" ->
  news), prejudice (preconceito, not "prejuízo" -> loss/damage), policy
  (política, not "polícia" -> police), fabric (tecido, not "fábrica" ->
  factory), lunch (almoço, not "lanche" -> snack), resume (retomar, not
  "resumir" -> summarize), costume (fantasia, not "costume" -> habit)."""


def _inventario_curto(report: Report) -> tuple[str, str]:
    """Inventário PERSONALIZADO: os erros que o log registrou, por classe.

    O inventário genérico (epêntese, falsos cognatos, incontáveis…) é material de
    ensino para o modelo e custa uns 5.000 caracteres. Ele vale enquanto o log
    está vazio; depois, o que importa são os erros que o aluno realmente comete —
    e esses o sistema conhece. Prompt longo dilui instrução, então encolher aqui
    é ganho pedagógico, não economia.
    """
    def por_classe(classe: str, limite: int = 8) -> list[str]:
        vistos: list[str] = []
        for entrada in report.entries:
            for erro in entrada.errors:
                if entrada.classes.get(erro, "") == classe and erro not in vistos:
                    vistos.append(erro)
        return vistos[:limite]

    pron = por_classe("pronúncia")
    gram = por_classe("gramática") + por_classe("vocabulário")

    if pron:
        bloco_pron = (
            "My recorded pronunciation offenders - police every one of them:\n"
            + "\n".join("- " + item for item in pron)
            + "\nAnd the usual Brazilian suspects: epenthesis, final -ed/-s, /θ/"
              " and /ð/, /ɪ/ vs /iː/, initial /h/ and /r/, and WORD STRESS.\n"
        )
    else:
        bloco_pron = (
            "Police the usual Brazilian suspects: epenthesis (helpi, estart),"
            " final -ed/-s, /θ/ and /ð/, /ɪ/ vs /iː/, /æ/ vs /ɛ/, initial /h/ and"
            " /r/, WORD STRESS, and the technical words I say at work (queue,"
            " cache, schema, tuple, route, query, idempotent).\n"
        )

    if gram:
        bloco_gram = (
            "My recorded grammar and word-choice offenders - these are not new to"
            " me, so be harsher on them:\n"
            + "\n".join("- " + item for item in gram)
            + "\nAlso keep watching: subject-verb agreement (third person -s),"
              " uncountables (information, advice, feedback, software),"
              " preposition government, articles, present perfect, collocations,"
              " and false friends (actually, eventually, pretend, realize,"
              " support, assist, library, push).\n"
        )
    else:
        bloco_gram = (
            "Police subject-verb agreement (third person -s), uncountables"
            " (information, advice, feedback, software), preposition government"
            " (depend ON), articles, present perfect vs simple past, do-support,"
            " collocations (ask a question, make a decision), and false friends"
            " (actually, eventually, pretend, realize, support, assist, library,"
            " push).\n"
        )
    return bloco_pron, bloco_gram


MODE_BLOCKS = {
    "N": """6b. This is a NEWS day. Search the web for a tech news story from the last 7 days (AI, the Java ecosystem, cloud, or the software industry in general). Summarize it in English in 3-4 sentences, then interrogate me about it: what I think, whether I agree, how it affects my work. Push back on my opinions to force me to argue. Do not use a story you only remember - actually search.""",
    "T": """6b. This is a TECH day. I will explain a technical concept I studied. Make me explain it as if I were teaching a junior developer. Ask "why" and "what happens if" questions until I run out of vocabulary, then give me the words I was missing.""",
    "R": """6b. This is a REVIEW day. Do not introduce new topics. Drill me on the items listed below until I get them right — they are the ones my schedule says are due. Make me produce a full sentence with each one, not just repeat after you. Be relentless about the ones I repeat.""",
    "D": """6b. This is an EVERYDAY day. Keep the conversation natural and practical - the kind of English I'd need outside work. Throw unexpected turns at me so I can't rely on rehearsed answers.""",
}


def build(
    day: int,
    report: Report,
    drive_file: str = "english-log",
    when: date | None = None,
    completo: bool | None = None,
) -> str:
    """Monta o prompt do dia.

    A data vai RESOLVIDA no molde. O placeholder `DD/MM` que ficava aqui era
    copiado ao pé da letra pelo professor de vez em quando, e cabeçalho com data
    literal é cabeçalho que o parser não lê.
    """
    pd = plan.get(day)
    if pd is None:
        raise ValueError(f"Dia {day} não existe no plano (1 a {plan.TOTAL_DAYS}).")

    track_block = ""
    if pd.kind == "T":
        name, content = plan.TRACKS.get(pd.week, ("", ""))
        if name:
            track_block = f"This week's technical track: {name} - {content}\n"

    # O inventário genérico ensina o modelo enquanto o log está vazio. Passadas
    # as primeiras sessões, o log sabe mais do aluno que qualquer lista genérica —
    # e um prompt de 11 mil caracteres dilui as instruções que importam.
    usar_completo = report.total_sessions < 5 if completo is None else completo
    if usar_completo:
        inventario_pron, inventario_gram = INVENTARIO_PRON, INVENTARIO_GRAM
    else:
        inventario_pron, inventario_gram = _inventario_curto(report)

    history_block = _history([e for e in report.entries if e.ok])
    focus_block = _focus(report, pd.kind)

    return BASE.format(
        mode_block=MODE_BLOCKS.get(pd.kind, ""),
        drive_file=drive_file,
        day=day,
        date_hint=(when or date.today()).strftime("%d/%m"),
        kind=pd.kind,
        kind_label=pd.kind_label,
        topic=pd.topic,
        inventario_pron=inventario_pron,
        inventario_gram=inventario_gram,
        track_block=track_block,
        history_block=history_block,
        focus_block=focus_block,
    )


SEPARADOR = "═" * 66


def pacote_dias(
    report: Report, dias: int = 7, drive_file: str = "english-log"
) -> list[dict]:
    """Os próximos N dias do plano, cada um com seu prompt pronto.

    O prompt de um dia só muda quando o LOG muda — então dá para prepará-lo com
    antecedência. É isso que tira o notebook do caminho diário: gera-se a semana
    quando a máquina está à mão, e o celular consome depois.
    """
    if report.next_day is None:
        return []   # plano concluído: `or 1` aqui recomeçaria do dia 1 calado
    inicio = report.next_day
    saida: list[dict] = []
    for numero in range(inicio, min(inicio + dias, plan.TOTAL_DAYS + 1)):
        pd = plan.get(numero)
        if pd is None:
            break
        saida.append({
            "dia": numero,
            "tipo": pd.kind_label,
            "tema": pd.topic,
            "prompt": build(numero, report, drive_file),
        })
    return saida


GRUPOS_REVISAO = (
    ("pronúncia", "PRONÚNCIA — o que decai mais rápido, e o que só a voz corrige"),
    ("gramática", "GRAMÁTICA E PALAVRA ERRADA — diga a forma certa numa frase sua"),
    ("vocabulário", "GRAMÁTICA E PALAVRA ERRADA — diga a forma certa numa frase sua"),
    ("fluência", "TRAVAMENTOS — diga o que você não conseguiu dizer"),
)


def _bloco_revisao(report: Report, quantos: int = 15) -> str:
    """A revisão do dia como TEXTO, dentro do pacote.

    Existe para a revisão sobreviver ao notebook desligado. O painel e o `deck`
    continuam melhores — eles têm os botões de "errei" e "já revisei" —, mas
    nenhum dos dois funciona quando a máquina está fora do ar, e a revisão é a
    parte do método que mais sofre com interrupção.
    """
    # A MESMA seleção do `deck` e da tela de cartões, inclusive as vagas
    # reservadas para gramática e pronúncia. Usar `vencidos` cru aqui devolveria
    # uma lista só de vocabulário, porque o atraso bruto das palavras é maior —
    # e a pronúncia, que é a prioridade, ficaria de fora.
    vencidos = deck(report, tamanho=quantos)
    if not vencidos:
        return ""

    hoje = report.generated_at
    linhas = [
        f"REVISÃO — {len(vencidos)} "
        f"{'item vencido' if len(vencidos) == 1 else 'itens vencidos'} "
        f"em {hoje.strftime('%d/%m')}",
        "",
        "Diga cada um em voz alta, numa frase sua. Cinco por dia bastam, começando",
        "pelos de cima, que são os mais atrasados. Errar aqui é o objetivo: é o que",
        "faz o item voltar mais cedo.",
        "",
        "Eles só saem da fila quando o professor registrar que você acertou (linha",
        '"Acertos:" ou "Reusou:" na sessão), então não estranhe se voltarem.',
    ]

    usados: set[str] = set()
    for classe, titulo in GRUPOS_REVISAO:
        do_grupo = [
            i for i in vencidos
            if i.chave not in usados and i.tipo == "erro" and i.classe == classe
        ]
        if not do_grupo:
            continue
        if titulo not in linhas:
            linhas.extend(["", titulo])
        for item in do_grupo:
            usados.add(item.chave)
            atraso = item.atraso(hoje)
            quando = f"vencido há {atraso}d" if atraso > 0 else "vence hoje"
            verso = f"  →  {item.verso}" if item.verso else ""
            linhas.append(f"- {item.rotulo}{verso}   [{quando}]")

    palavras = [i for i in vencidos if i.tipo == "palavra"]
    if palavras:
        linhas.extend(["", "PALAVRAS A FIXAR — use cada uma numa frase sua"])
        for item in palavras:
            atraso = item.atraso(hoje)
            quando = f"vencido há {atraso}d" if atraso > 0 else "vence hoje"
            verso = f"  =  {item.verso}" if item.verso else ""
            linhas.append(f"- {item.rotulo}{verso}   [{quando}]")

    sem_classe = [
        i for i in vencidos if i.tipo == "erro" and i.chave not in usados
    ]
    if sem_classe:
        linhas.extend(["", "OUTROS"])
        for item in sem_classe:
            verso = f"  →  {item.verso}" if item.verso else ""
            linhas.append(f"- {item.rotulo}{verso}")

    return "\n".join(linhas)


def pacote(report: Report, dias: int = 7, drive_file: str = "english-log") -> str:
    """A semana inteira num arquivo só, para ler do celular sem o notebook.

    Cada dia vem num bloco delimitado, copiável isoladamente. O cabeçalho diz
    quando foi gerado e o que envelhece: o TEMA de cada dia está sempre certo (é
    o plano), mas o histórico e a agenda de revisão dentro de cada bloco são da
    hora da geração. Dizer isso é melhor do que fingir que o pacote é fresco.
    """
    blocos = pacote_dias(report, dias, drive_file)
    if not blocos:
        return "Plano concluído — não há próximos dias."

    gerado = date.today().strftime("%d/%m/%Y")
    primeiro, ultimo = blocos[0]["dia"], blocos[-1]["dia"]
    cabecalho = [
        f"PROMPTS DOS DIAS {primeiro} A {ultimo} — gerado em {gerado}",
        "",
        "Este arquivo tem duas coisas: a REVISÃO (para dizer em voz alta, dois",
        "minutos, sem app nenhum) e os PROMPTS de cada dia.",
        "",
        "Como usar o prompt: ache o bloco do dia que você vai fazer, copie do",
        "início do bloco até a linha dupla seguinte, e cole no Gemini Live.",
        "",
        "Se você já fez algum destes dias, pule para o bloco seguinte — os dias",
        "saem na ordem do plano.",
        "",
        "O tema de cada dia está sempre certo. Já o histórico e a lista de",
        f"revisão dentro de cada bloco são de {gerado}: quanto mais tempo passar,",
        "mais desatualizados. Regenere o pacote quando estiver com o notebook.",
        "",
    ]

    partes = ["\n".join(cabecalho)]

    revisao = _bloco_revisao(report)
    if revisao:
        partes.append(f"{SEPARADOR}\n{revisao}\n")

    for bloco in blocos:
        partes.append(
            f"{SEPARADOR}\n"
            f"DIA {bloco['dia']:02d} · {bloco['tipo']} · {bloco['tema']}\n"
            f"{SEPARADOR}\n\n"
            f"{bloco['prompt']}\n"
        )
    partes.append(SEPARADOR + "\nfim do pacote\n")
    return "\n".join(partes)


def _history(entries: list[Entry], limit: int = 5) -> str:
    recent = entries[-limit:]
    if not recent:
        return "\nThis is my first session - no history yet.\n"
    lines = ["\nMy last sessions:"]
    for entry in recent:
        errors = "; ".join(entry.errors[:3]) or "no errors recorded"
        lines.append(f"- Day {entry.day} ({entry.topic or 'no topic'}): {errors}")
    return "\n".join(lines) + "\n"


def _focus(report: Report, kind: str) -> str:
    """O que o professor tem de cobrar hoje.

    Em dia de revisão manda a AGENDA (o que está vencido na repetição espaçada),
    não a frequência bruta: um erro que apareceu duas vezes na primeira semana e
    foi acertado desde então não é o trabalho de hoje, e uma palavra exposta uma
    vez e nunca reusada é. Nos outros dias fica o aviso curto, dos que repetem.
    """
    if kind == "R":
        vencidos = report.vencidos[:8]
        if vencidos:
            linhas = [
                f"- {i.rotulo} ({'erro' if i.tipo == 'erro' else 'palavra'},"
                f" {'vencido há ' + str(i.atraso(report.generated_at)) + ' dias' if i.atraso(report.generated_at) > 0 else 'vence hoje'})"
                for i in vencidos
            ]
            return "\nDue for review today - drill each of these:\n" + "\n".join(linhas) + "\n"

    repeated = [g.label for g in report.top_errors if g.count > 1][:6]
    if not repeated:
        return ""
    joined = "; ".join(repeated)
    intensity = "Drill these until they're gone" if kind == "R" else "Watch for these"
    return f"\n{intensity} - mistakes I keep repeating: {joined}\n"
