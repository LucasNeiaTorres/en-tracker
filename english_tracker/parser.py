"""Lê o arquivo english-log e transforma em dados.

Quem escreve este arquivo é outra IA — o professor do Gemini Live, em modo voz,
com uma ferramenta de escrita no Drive. Isso define o trabalho deste módulo:
ele não lê um formato, ele lê a *tentativa* de um formato.

Duas classes de variação, tratadas de formas diferentes:

- **Formatação** (travessão ou dois-pontos, língua, ano ausente, negrito,
  bullet, cabeçalho markdown, tipo por extenso): absorvida em silêncio. É ruído,
  não informação.
- **Estrutura** (cabeçalho que não dá para ler, entrada sem conteúdo nenhum):
  NUNCA absorvida em silêncio. Vira `status` na entrada, para a análise mostrar
  em vermelho ao lado dos buracos.

A regra que sustenta o projeto — nunca assumir que a sessão foi registrada —
vale também para o conteúdo, não só para a presença do dia. Sessão registrada
com zero erros, zero vocabulário e nota vazia é parse falhado, não sessão
perfeita: o prompt exige do professor os erros, cinco palavras e uma nota, então
as três coisas vazias ao mesmo tempo significam que o texto não foi entendido.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

# Um cabeçalho é qualquer linha que comece por DIA/DAY seguido de número. Esta é
# a única coisa exigida: o resto é procurado campo por campo, não casado de uma
# vez. O padrão monolítico anterior exigia a linha inteira e, a cada variação do
# modelo, perdia a entrada nova E apagava os erros da entrada anterior.
LOOKS_HEADER_RE = re.compile(r"^(?:DIA|DAY)\s*\d", re.IGNORECASE)
HEADER_DAY_RE = re.compile(r"^(?:DIA|DAY)\s*0*(\d{1,4})\b", re.IGNORECASE)

DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
KIND_RE = re.compile(r"(?:Tipo|Type)\s*[:=]?\s*([A-Za-zÀ-ÿ]+)", re.IGNORECASE)
TOPIC_RE = re.compile(
    r"(?:Tema|Topic|Assunto|Subject)\s*[:=—–-]?\s*(.*)$", re.IGNORECASE
)

_LABEL_SEP = r"\s*[:=—–-]\s*"
FIELD_PATTERNS = {
    "errors": re.compile(rf"^(?:Erros|Errors|Mistakes){_LABEL_SEP}(.*)$", re.IGNORECASE),
    "vocab": re.compile(
        rf"^(?:Palavras novas|Vocabulário|Vocabulario|Vocabulary|New words|Words)"
        rf"{_LABEL_SEP}(.*)$",
        re.IGNORECASE,
    ),
    "note": re.compile(
        rf"^(?:Nota do professor|Nota|Teacher'?s? note|Rating|Note|Avaliação)"
        rf"{_LABEL_SEP}(.*)$",
        re.IGNORECASE,
    ),
    # O que deu CERTO hoje e antes não dava. Sem isto, o log é registro só de
    # fracasso — e a agenda de revisão não tem sinal positivo: saber que um erro
    # não reapareceu não é o mesmo que saber que ele foi acertado.
    "hits": re.compile(
        rf"^(?:Acertos|Acerto|Got right|Right|Wins|Melhorou){_LABEL_SEP}(.*)$",
        re.IGNORECASE,
    ),
    # Palavra de sessão anterior que o aluno usou SEM ser mandado. É a diferença
    # entre vocabulário exposto e vocabulário adquirido.
    "reused": re.compile(
        rf"^(?:Reusou|Reutilizou|Reused|Used again|Reuse){_LABEL_SEP}(.*)$",
        re.IGNORECASE,
    ),
}

# Item de lista. O modelo quebra "Erros:" em bullets ou lista numerada sempre que
# há mais de um item. Antes essas linhas eram ignoradas e o dia entrava com zero
# erros — o pior modo de falha do sistema, porque se lia como dia limpo.
BULLET_RE = re.compile(r"^\s*(?:[-*•·–—]|\d{1,2}[.)])\s+(.+)$")

_SPLIT_ERRORS = re.compile(r"\s*[;•]\s*|\s*\|\s*")
_SPLIT_VOCAB = re.compile(r"\s*[,;•]\s*")

# O verso do cartão. Só o professor pode escrevê-lo, na hora em que a forma certa
# existe: um programa em Python que inventasse a correção — ou a pronúncia de
# "queue" — estaria dando o palpite que este projeto foi feito para não dar.
#   erro:    esqueci o -s na terceira pessoa → "He works at a radar company"
#   palavra: backoff = espera exponencial entre retentativas
_VERSO_ERRO_RE = re.compile(r"\s*(?:→|->|=>)\s*")
_VERSO_PALAVRA_RE = re.compile(r"\s*=\s*")

# Placeholder do próprio molde do prompt: <mistake>, <word>, <one line>. Se o
# professor copiar o gabarito ao pé da letra, isso não é erro do aluno.
_PLACEHOLDER_RE = re.compile(r"^<[^>]*>$")

# Etiqueta de classe do erro, escrita pelo professor: "[pron] queue".
# Pronúncia é o que decai mais rápido e o que um modelo de texto não conserta,
# então ela precisa ser distinguida — não para estatística bonita, mas porque a
# agenda de revisão usa intervalos mais curtos para ela.
_TAG_RE = re.compile(
    r"^\s*\[\s*(pron|pronuncia|pronúncia|gram|gramatica|gramática|lex|vocab|"
    r"flu|fluencia|fluência)\s*\]\s*",
    re.IGNORECASE,
)

CLASSES = {
    "pron": "pronúncia", "pronuncia": "pronúncia", "pronúncia": "pronúncia",
    "gram": "gramática", "gramatica": "gramática", "gramática": "gramática",
    "lex": "vocabulário", "vocab": "vocabulário",
    "flu": "fluência", "fluencia": "fluência", "fluência": "fluência",
}

# Sem etiqueta, o texto do erro ainda entrega a classe em muitos casos — é o que
# faz a distinção funcionar no log ANTIGO, escrito antes de a etiqueta existir.
_PISTAS = (
    ("pronúncia", "pronúncia"), ("pronuncia", "pronúncia"),
    ("pronunciation", "pronúncia"), ("pronounce", "pronúncia"),
    ("stress", "pronúncia"), ("sotaque", "pronúncia"),
    ("travei", "fluência"), ("travou", "fluência"), ("got stuck", "fluência"),
    ("concordância", "gramática"), ("concordancia", "gramática"),
    ("terceira pessoa", "gramática"), ("third person", "gramática"),
    ("preposição", "gramática"), ("preposicao", "gramática"),
    ("artigo", "gramática"), ("tempo verbal", "gramática"),
    ("plural", "gramática"), ("agreement", "gramática"),
    ("falso cognato", "vocabulário"), ("false friend", "vocabulário"),
    ("em vez de", "vocabulário"), ("wrong word", "vocabulário"),
)

VALID_KINDS = frozenset({"D", "T", "N", "R"})

# O tipo vem abreviado, por extenso, em português ou em inglês.
KIND_WORDS = {
    "d": "D", "dia": "D", "diaadia": "D", "cotidiano": "D",
    "everyday": "D", "daily": "D", "smalltalk": "D",
    "t": "T", "tecnico": "T", "technical": "T", "tech": "T",
    "n": "N", "noticia": "N", "news": "N",
    "r": "R", "revisao": "R", "review": "R", "revisar": "R", "revision": "R",
}

STOPWORDS = {
    "de", "do", "da", "em", "no", "na", "o", "a", "e", "que", "com", "para",
    "the", "to", "of", "in", "an", "and", "i", "my", "is", "it", "on",
}

STATUS_OK = "ok"
STATUS_SEM_CONTEUDO = "sem-conteudo"


@dataclass
class Entry:
    """Uma sessão registrada."""

    day: int
    when: date | None = None
    kind: str | None = None
    topic: str = ""
    errors: list[str] = field(default_factory=list)
    vocab: list[str] = field(default_factory=list)
    hits: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    # rótulo limpo -> classe ("pronúncia", "gramática", ...). Preenchido na
    # leitura, quando a etiqueta `[pron]` ainda está no texto; depois ela sai do
    # rótulo e só sobra aqui.
    classes: dict[str, str] = field(default_factory=dict)
    # rótulo limpo -> verso do cartão (forma certa, frase-modelo ou gloss).
    versos: dict[str, str] = field(default_factory=dict)
    note: str = ""
    raw: str = ""
    extra: str = ""
    status: str = STATUS_OK

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def has_content(self) -> bool:
        """Sessão de que se aproveitou alguma coisa."""
        return bool(
            self.errors or self.vocab or self.hits or self.reused or self.note.strip()
        )

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


def _strip_decoration(line: str) -> str:
    """Tira a decoração markdown que o modelo põe sem ninguém pedir."""
    text = line.strip()
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"^>\s*", "", text)
    text = text.replace("**", "").replace("__", "")
    for mark in ("*", "_"):
        if len(text) > 2 and text.startswith(mark) and text.endswith(mark):
            text = text[1:-1]
    # Bullet só no começo, e só se vier espaço depois: "- DIA 03", "1. DIA 03".
    text = re.sub(r"^(?:[-*•·]|\d{1,2}[.)])\s+", "", text)
    return text.strip()


def _kind_from_word(word: str | None) -> str | None:
    if not word:
        return None
    key = normalize(word).replace(" ", "").replace("-", "")
    if key in KIND_WORDS:
        return KIND_WORDS[key]
    initial = key[:1].upper()
    return initial if initial in VALID_KINDS else None


def _parse_date(d: str | None, m: str | None, y: str | None) -> date | None:
    if not d or not m:
        return None
    year = int(y) if y else date.today().year
    if year < 100:
        year += 2000
    try:
        return date(year, int(m), int(d))
    except ValueError:
        return None


def _cut(text: str, span: tuple[int, int]) -> str:
    """Remove o trecho já consumido, para o campo seguinte não reler o dele."""
    return text[: span[0]] + " " + text[span[1] :]


def _parse_header(clean: str) -> Entry | None:
    """Lê o cabeçalho por busca de campo, não por casamento da linha inteira."""
    day_match = HEADER_DAY_RE.match(clean)
    if not day_match:
        return None

    rest = clean[day_match.end() :]

    when = None
    date_match = DATE_RE.search(rest)
    if date_match:
        when = _parse_date(*date_match.groups())
        rest = _cut(rest, date_match.span())

    kind = None
    kind_match = KIND_RE.search(rest)
    if kind_match:
        kind = _kind_from_word(kind_match.group(1))
        rest = _cut(rest, kind_match.span())

    topic = ""
    topic_match = TOPIC_RE.search(rest)
    if topic_match:
        topic = topic_match.group(1).strip(" —–-:*_").strip()

    return Entry(day=int(day_match.group(1)), when=when, kind=kind, topic=topic)


def _match_field(clean: str) -> tuple[str | None, str]:
    for key, pattern in FIELD_PATTERNS.items():
        match = pattern.match(clean)
        if match:
            return key, match.group(1).strip()
    return None, ""


def _collect_values(inline: str, lines: list[str], start: int) -> tuple[list[str], int]:
    """Junta o valor da linha do rótulo com os itens de lista que vierem abaixo.

    Devolve (valores, quantas linhas seguintes foram consumidas). Para no primeiro
    sinal de que a lista acabou: linha em branco, prosa, outro rótulo ou cabeçalho.
    """
    values = [inline] if inline else []
    consumed = 0
    for line in lines[start:]:
        bullet = BULLET_RE.match(line)
        if not bullet:
            break
        item = _strip_decoration(bullet.group(1))
        if not item or LOOKS_HEADER_RE.match(item) or _match_field(item)[0]:
            break
        values.append(item)
        consumed += 1
    return values, consumed


def _is_empty_marker(text: str) -> bool:
    """Travessão, hífen ou placeholder: o professor dizendo "não tenho isto"."""
    return not text.strip(" \t—–-•.:") or bool(_PLACEHOLDER_RE.match(text))


def classe_do_erro(rotulo: str) -> str:
    """Classifica um erro: pronúncia, gramática, vocabulário, fluência ou "".

    Primeiro pela etiqueta que o professor escreve (`[pron] queue`); se não
    houver, por pista no próprio texto. A pista é o que faz isto valer para o
    histórico já registrado, sem migração de formato.
    """
    tag = _TAG_RE.match(rotulo)
    if tag:
        return CLASSES.get(tag.group(1).lower(), "")
    baixo = normalize(rotulo)
    for pista, classe in _PISTAS:
        if normalize(pista) in baixo:
            return classe
    return ""


def _sem_etiqueta(rotulo: str) -> str:
    """Tira a etiqueta do rótulo exibido: ela é metadado, não parte do erro."""
    return _TAG_RE.sub("", rotulo).strip()


def _clean_list(items: list[str]) -> list[str]:
    out = []
    for item in items:
        cleaned = item.strip().strip("-–—•").strip()
        if not cleaned or _PLACEHOLDER_RE.match(cleaned):
            continue
        # A etiqueta sai do rótulo, mas a classe continua deduzível dele pelas
        # pistas — e o agrupamento não pode separar "[pron] queue" de "queue".
        sem_tag = _sem_etiqueta(cleaned)
        out.append(sem_tag or cleaned)
    return out


def _split_all(values: list[str], pattern: re.Pattern[str]) -> list[str]:
    parts: list[str] = []
    for value in values:
        parts.extend(pattern.split(value))
    return _clean_list(parts)


def _split_classificado(
    values: list[str], pattern: re.Pattern[str], verso_re: re.Pattern[str] | None = None
) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """Separa os itens e colhe, de cada um, a classe e o verso do cartão.

    A classe tem de ser lida antes de a etiqueta cair do rótulo; o verso, antes de
    o separador cair. Depois disso o rótulo é só o item, e é ele que identifica a
    entrada na agenda.
    """
    brutos: list[str] = []
    for value in values:
        brutos.extend(pattern.split(value))

    limpos: list[str] = []
    classes: dict[str, str] = {}
    versos: dict[str, str] = {}
    for bruto in brutos:
        cru = bruto.strip().strip("-–—•").strip()
        if not cru or _PLACEHOLDER_RE.match(cru):
            continue
        classe = classe_do_erro(cru)
        sem_tag = _sem_etiqueta(cru) or cru

        verso = ""
        if verso_re is not None:
            partes = verso_re.split(sem_tag, maxsplit=1)
            if len(partes) == 2 and partes[0].strip() and partes[1].strip():
                sem_tag, verso = partes[0].strip(), partes[1].strip()

        limpos.append(sem_tag)
        if classe:
            classes[sem_tag] = classe
        if verso and not _PLACEHOLDER_RE.match(verso):
            versos[sem_tag] = verso
    return limpos, classes, versos


def parse_log(text: str) -> list[Entry]:
    """Converte o conteúdo bruto do log numa lista de entradas, ordenada por dia.

    Toda linha que começa com DIA/DAY + número inicia uma entrada, e nenhuma
    linha de campo é atribuída à entrada anterior: era assim que um cabeçalho
    torto apagava os erros do dia de cima.
    """
    lines = text.splitlines()
    entries: list[Entry] = []
    current: Entry | None = None
    buffer: list[str] = []
    unparsed: list[str] = []

    def flush() -> None:
        if current is None:
            return
        current.raw = "\n".join(buffer).strip()
        current.extra = "\n".join(unparsed).strip()
        if not current.has_content:
            current.status = STATUS_SEM_CONTEUDO
        entries.append(current)

    index = 0
    while index < len(lines):
        line = lines[index]
        clean = _strip_decoration(line)

        if LOOKS_HEADER_RE.match(clean):
            # Linha de cabeçalho SEMPRE fecha a entrada corrente, mesmo quando não
            # dá para ler o dia dela. Deixar seguir era o que permitia a uma linha
            # `Erros:` de outra sessão sobrescrever os erros do dia de cima.
            header = _parse_header(clean)
            flush()
            current, buffer, unparsed = header, ([line] if header else []), []
            index += 1
            continue

        if current is None:
            index += 1
            continue

        buffer.append(line)
        key, inline = _match_field(clean)
        if key is None:
            if clean:
                unparsed.append(clean)
            index += 1
            continue

        values, consumed = _collect_values(inline, lines, index + 1)
        buffer.extend(lines[index + 1 : index + 1 + consumed])

        if key == "errors":
            current.errors, classes, versos = _split_classificado(
                values, _SPLIT_ERRORS, _VERSO_ERRO_RE
            )
            current.classes.update(classes)
            current.versos.update(versos)
        elif key == "vocab":
            current.vocab, _, versos = _split_classificado(
                values, _SPLIT_VOCAB, _VERSO_PALAVRA_RE
            )
            current.versos.update(versos)
        elif key == "hits":
            current.hits, classes, versos = _split_classificado(
                values, _SPLIT_ERRORS, _VERSO_ERRO_RE
            )
            current.classes.update(classes)
            current.versos.update(versos)
        elif key == "reused":
            current.reused, _, _ = _split_classificado(values, _SPLIT_VOCAB)
        else:
            joined = " ".join(values).strip().strip('"“”').strip()
            current.note = "" if _is_empty_marker(joined) else joined

        index += 1 + consumed

    flush()

    # Se o mesmo dia aparecer duas vezes, a última entrada vence.
    by_day: dict[int, Entry] = {}
    for entry in entries:
        by_day[entry.day] = entry
    return sorted(by_day.values(), key=lambda e: e.day)


def parse_session(text: str, day: int) -> Entry | None:
    """Lê o resumo de UMA sessão colada à mão, com ou sem o cabeçalho `DIA`.

    Quem cola um resumo digita "Erros: ...", não "DIA 05 — ... — Erros: ...":
    o cabeçalho é coisa do arquivo, não do que o professor fala. Sem isto, o
    caso MAIS COMUM do `add` — justamente o mecanismo que existe porque o
    professor falhou — caía no "não entendi o formato" e os erros não entravam
    na conta.

    Devolve a entrada aproveitável, ou None quando não há nada de que se
    aproveite (aí quem chama guarda o texto como prosa, sem perder nada).
    """
    for candidato in (text, f"DIA {day:02d}\n{text}"):
        entradas = parse_log(candidato)
        if entradas and entradas[0].has_content:
            entrada = entradas[0]
            entrada.day = day
            return entrada
    return None


def set_verso(text: str, rotulo: str, verso: str) -> tuple[str, bool]:
    """Escreve o verso de um item no log, na ÚLTIMA linha onde ele aparece.

    O verso do aluno vai para o log — e não para um arquivo à parte — porque o
    log é a fonte da verdade e é ele que sobe para o Drive; anotação em arquivo
    local se perderia na troca de máquina.

    A linha alvo é RECONSTRUÍDA a partir dos seus itens (mantendo etiquetas e
    versos existentes) em vez de recortada por posição: recorte com aritmética de
    índice erra quando os separadores variam, e errar aqui é corromper o log.
    Efeito colateral aceito: a linha editada perde a decoração markdown que o
    professor tivesse posto nela. Nenhuma outra linha é tocada.

    Nunca sobrescreve verso existente. Devolve (texto novo, escreveu?).
    """
    alvo = normalize(rotulo)
    if not alvo or not verso.strip():
        return text, False

    linhas = text.splitlines()
    achado: tuple[int, str] | None = None

    for indice, linha in enumerate(linhas):
        clean = _strip_decoration(linha)
        campo, valor = _match_field(clean)
        if campo not in ("errors", "vocab", "hits") or not valor:
            continue
        verso_re = _VERSO_PALAVRA_RE if campo == "vocab" else _VERSO_ERRO_RE
        divisor = _SPLIT_VOCAB if campo == "vocab" else _SPLIT_ERRORS
        for bruto in divisor.split(valor):
            item = _sem_etiqueta(bruto.strip())
            partes = verso_re.split(item, maxsplit=1)
            if normalize(partes[0].strip()) != alvo:
                continue
            if len(partes) == 2 and partes[1].strip():
                return text, False   # o professor já escreveu; não se sobrescreve
            achado = (indice, campo)

    if achado is None:
        return text, False

    indice, campo = achado
    clean = _strip_decoration(linhas[indice])
    rotulo_campo = clean.split(":", 1)[0].strip()
    _, valor = _match_field(clean)

    verso_re = _VERSO_PALAVRA_RE if campo == "vocab" else _VERSO_ERRO_RE
    divisor = _SPLIT_VOCAB if campo == "vocab" else _SPLIT_ERRORS
    separador = " = " if campo == "vocab" else " → "
    junta = ", " if campo == "vocab" else "; "

    itens: list[str] = []
    for bruto in divisor.split(valor):
        cru = bruto.strip()
        if not cru:
            continue
        base = verso_re.split(_sem_etiqueta(cru), maxsplit=1)[0].strip()
        if normalize(base) == alvo:
            cru = cru.rstrip() + separador + verso.strip()
        itens.append(cru)

    linhas[indice] = f"{rotulo_campo}: {junta.join(itens)}"
    return "\n".join(linhas) + ("\n" if text.endswith("\n") else ""), True


def remove_day(text: str, day: int) -> tuple[str, int]:
    """Remove do log as entradas de um dia, preservando todo o resto byte a byte.

    Corta por FAIXA DE LINHAS, do cabeçalho do dia até o cabeçalho seguinte, em
    vez de reescrever o arquivo a partir das entradas parseadas: reescrever
    perderia a prosa do professor, os campos que o parser ignora e a formatação
    original dos outros dias. O que este programa não entende, ele não apaga.

    Devolve (texto novo, quantas entradas saíram).
    """
    lines = text.splitlines()
    manter: list[str] = []
    removidas = 0
    apagando = False

    for line in lines:
        clean = _strip_decoration(line)
        if LOOKS_HEADER_RE.match(clean):
            header = _parse_header(clean)
            apagando = header is not None and header.day == day
            if apagando:
                removidas += 1
                continue
        if apagando:
            continue
        manter.append(line)

    novo = "\n".join(manter).strip()
    return (novo + "\n" if novo else ""), removidas


def normalize(text: str) -> str:
    """Normaliza um erro para agrupar repetições: sem acento, minúsculo, sem pontuação."""
    lowered = unicodedata.normalize("NFKD", text.lower())
    lowered = "".join(c for c in lowered if not unicodedata.combining(c))
    cleaned = re.sub(r"[^a-z0-9\s'→>]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def keywords(text: str) -> list[str]:
    return [w for w in normalize(text).split() if len(w) > 2 and w not in STOPWORDS]


def _com_verso(rotulo: str, versos: dict[str, str], separador: str) -> str:
    verso = versos.get(rotulo, "")
    return f"{rotulo}{separador}{verso}" if verso else rotulo


def render_entry(entry: Entry) -> str:
    """Volta uma entrada para o formato canônico do log.

    `extra` (o texto que o parser não entendeu, ou o resumo colado no `add`) vai
    para o arquivo do mesmo jeito: é melhor guardar prosa que ninguém lê a perder
    o que o aluno digitou.
    """
    when = entry.when.strftime("%d/%m") if entry.when else date.today().strftime("%d/%m")
    lines = [
        f"DIA {entry.day:02d} — {when} — Tipo: {entry.kind or '?'} — Tema: {entry.topic}",
        f"Erros: {'; '.join(_com_verso(e, entry.versos, ' → ') for e in entry.errors) if entry.errors else '—'}",
        f"Palavras novas: {', '.join(_com_verso(v, entry.versos, ' = ') for v in entry.vocab) if entry.vocab else '—'}",
    ]
    # Acertos e reúso só aparecem quando existem: linha vazia todo dia é ruído
    # que o professor aprende a copiar sem preencher.
    if entry.hits:
        acertos = '; '.join(_com_verso(h, entry.versos, ' → ') for h in entry.hits)
        lines.append(f"Acertos: {acertos}")
    if entry.reused:
        lines.append(f"Reusou: {', '.join(entry.reused)}")
    lines.append(
        f'Nota do professor: "{entry.note}"' if entry.note else 'Nota do professor: "—"'
    )
    if entry.extra:
        lines.append("Resumo colado:")
        lines.extend(f"  {part}" for part in entry.extra.splitlines())
    return "\n".join(lines)
