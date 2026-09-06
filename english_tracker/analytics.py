"""Análise do log: consistência, dias faltando, erros que se repetem, vocabulário.

A regra central: nunca confiar que a sessão foi registrada. Toda análise
compara o que o plano esperava com o que existe de fato no arquivo.

Ela tem três desfechos, não dois. Além do dia feito e do buraco existe o dia
**registrado e ilegível**: o professor escreveu algo, o parser não aproveitou
nada, e o dia não pode contar como feito só porque tem um cabeçalho. Junto vai o
**dia fora do plano** (um `DIA 45` digitado errado), que antes somava erros e
vocabulário sem aparecer como sessão — inflava as estatísticas em silêncio.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import config, plan
from .parser import Entry, classe_do_erro, keywords, normalize


@dataclass
class ErrorGroup:
    label: str
    count: int
    days: list[int]


@dataclass
class VocabItem:
    word: str
    first_day: int
    times: int


# Intervalos de recuperação, em DIAS DE CALENDÁRIO. Aproximadamente dobrando, na
# forma clássica de Leitner. O último é a linha de chegada: item que sobrevive a
# 30 dias sem reaparecer como erro sai da fila e conta como dominado.
INTERVALOS = (1, 3, 7, 16, 30)

# Pronúncia recebe intervalos MAIS CURTOS de propósito. Ela decai mais rápido que
# gramática — é motor, não regra: envolve articulação, e articulação sem prática
# recente volta ao padrão do português. Além disso é a única classe de erro que
# um modelo de texto não consegue corrigir, então cada oportunidade conta.
INTERVALOS_PRONUNCIA = (1, 2, 5, 10, 21)


def intervalos_de(classe: str) -> tuple[int, ...]:
    return INTERVALOS_PRONUNCIA if classe == "pronúncia" else INTERVALOS


@dataclass
class ItemRevisao:
    """Um item na agenda de revisão — um erro a extinguir, ou uma palavra a fixar."""

    chave: str
    rotulo: str
    tipo: str          # "erro" | "palavra"
    caixa: int         # quantos acertos consecutivos desde a última falha
    visto: date | None  # quando apareceu por último (falha, acerto ou reúso)
    vence: date | None  # quando volta a ser cobrado
    aparicoes: int
    dias: list[int]
    classe: str = ""
    verso: str = ""     # forma certa / frase-modelo / gloss — escrita na sessão
    revisado_hoje: bool = False   # "pronúncia" | "gramática" | "fluência" | "vocabulário" | ""

    @property
    def escala(self) -> tuple[int, ...]:
        return intervalos_de(self.classe)

    @property
    def dominado(self) -> bool:
        return self.caixa >= len(self.escala)

    def atraso(self, hoje: date) -> int:
        """Dias de atraso. Negativo = ainda não venceu. Sem data = cobra logo."""
        if self.vence is None:
            return 0
        return (hoje - self.vence).days


@dataclass
class Report:
    entries: list[Entry]
    done_days: list[int] = field(default_factory=list)
    missing_days: list[int] = field(default_factory=list)
    illegible_days: list[int] = field(default_factory=list)
    unknown_days: list[int] = field(default_factory=list)
    next_day: int | None = None
    current_streak: int = 0
    longest_streak: int = 0
    completion: float = 0.0
    by_kind: dict[str, int] = field(default_factory=dict)
    top_errors: list[ErrorGroup] = field(default_factory=list)
    error_themes: list[tuple[str, int]] = field(default_factory=list)
    vocab: list[VocabItem] = field(default_factory=list)
    errors_per_day: list[tuple[int, int]] = field(default_factory=list)
    total_errors: int = 0
    revisao: list[ItemRevisao] = field(default_factory=list)
    dominados: list[ItemRevisao] = field(default_factory=list)
    por_classe: dict[str, int] = field(default_factory=dict)
    generated_at: date = field(default_factory=date.today)

    @property
    def total_sessions(self) -> int:
        return len(self.done_days)

    @property
    def vocab_count(self) -> int:
        return len(self.vocab)

    @property
    def has_gaps(self) -> bool:
        return bool(self.missing_days)

    @property
    def vencidos(self) -> list[ItemRevisao]:
        """O que está na hora de revisar, mais atrasado primeiro."""
        hoje = self.generated_at
        devidos = [
            i for i in self.revisao if i.atraso(hoje) >= 0 and not i.revisado_hoje
        ]
        # Pronúncia ganha o desempate: é o que decai mais rápido e o que só a
        # sessão de voz corrige.
        return sorted(
            devidos,
            key=lambda i: (-i.atraso(hoje), i.classe != "pronúncia",
                           -i.aparicoes, i.rotulo),
        )

    @property
    def has_anomalies(self) -> bool:
        """Dia registrado que não deu para aproveitar. Tão vermelho quanto buraco."""
        return bool(self.illegible_days or self.unknown_days)


def build_report(entries: list[Entry]) -> Report:
    report = Report(entries=entries)

    # Só entra na contabilidade o dia que existe no plano E de que se aproveitou
    # alguma coisa. O resto é anomalia, e anomalia aparece — não some na média.
    usable = [e for e in entries if e.day in plan.PLAN and e.ok]
    report.unknown_days = sorted({e.day for e in entries if e.day not in plan.PLAN})
    report.illegible_days = sorted(
        {e.day for e in entries if e.day in plan.PLAN and not e.ok}
    )

    done = sorted({e.day for e in usable})
    report.done_days = done

    registered = set(done) | set(report.illegible_days)
    if registered:
        highest = max(registered)
        report.missing_days = [d for d in range(1, highest) if d not in registered]
        report.next_day = next(
            (d for d in range(1, plan.TOTAL_DAYS + 1) if d not in done), None
        )
    else:
        report.next_day = 1

    report.current_streak = _current_streak(done)
    report.longest_streak = _longest_streak(done)
    report.completion = len(done) / plan.TOTAL_DAYS * 100

    kinds: Counter[str] = Counter()
    for day in done:
        pd = plan.get(day)
        if pd:
            kinds[pd.kind] += 1
    report.by_kind = dict(kinds)

    report.top_errors = _group_errors(usable)
    report.error_themes = _themes(usable)
    report.vocab = _collect_vocab(usable)
    report.errors_per_day = [(e.day, e.error_count) for e in usable]
    report.total_errors = sum(e.error_count for e in usable)

    classes: Counter[str] = Counter()
    for entrada in usable:
        for erro in entrada.errors:
            classes[entrada.classes.get(erro, "") or classe_do_erro(erro) or "sem classe"] += 1
    report.por_classe = dict(classes)

    agenda_completa = _agenda(usable)
    report.revisao = [i for i in agenda_completa if not i.dominado]
    report.dominados = [i for i in agenda_completa if i.dominado]
    return report


def _agenda(entries: list[Entry]) -> list[ItemRevisao]:
    """Monta a agenda de revisão espaçada a partir do próprio log.

    Não há banco de dados nem estado extra: o log já diz, para cada item, quando
    ele apareceu e o que aconteceu com ele. A leitura é cronológica —

    - erro em `Erros:`   → FALHA: volta para a primeira caixa;
    - erro em `Acertos:` → ACERTO: avança uma caixa;
    - palavra em `Palavras novas:` → entra na primeira caixa;
    - palavra em `Reusou:`         → ACERTO: avança uma caixa.

    Ausência NÃO promove: um erro que simplesmente não voltou continua na fila,
    porque "não errei" não é o mesmo que "acertei" — e é exatamente para isso que
    existe a linha `Acertos:`. O que faz um item sair da fila é sobreviver à
    última caixa: aí ele é dado por dominado.

    A data usada é a do calendário (`Entry.when`); dia sem data fica sem
    vencimento e é cobrado na primeira oportunidade.
    """
    itens: dict[str, ItemRevisao] = {}

    def toque(rotulo: str, tipo: str, dia: int, quando: date | None,
              acerto: bool, classe: str = "", verso: str = "") -> None:
        chave = f"{tipo}:{normalize(rotulo)}"
        if not normalize(rotulo):
            return
        item = itens.get(chave)
        if item is None:
            item = ItemRevisao(
                chave=chave, rotulo=rotulo, tipo=tipo, caixa=0,
                visto=quando, vence=None, aparicoes=0, dias=[],
                classe=classe,
            )
            itens[chave] = item
        if acerto:
            item.caixa += 1
        else:
            item.caixa = 0
            item.aparicoes += 1
        if dia not in item.dias:
            item.dias.append(dia)
        if classe and not item.classe:
            item.classe = classe
        if verso and not item.verso:
            item.verso = verso
        item.visto = quando or item.visto

    for entrada in sorted(entries, key=lambda e: (e.when or date.min, e.day)):
        for erro in entrada.errors:
            toque(erro, "erro", entrada.day, entrada.when, acerto=False,
                  classe=entrada.classes.get(erro, "") or classe_do_erro(erro),
                  verso=entrada.versos.get(erro, ""))
        for acerto in entrada.hits:
            toque(acerto, "erro", entrada.day, entrada.when, acerto=True,
                  classe=entrada.classes.get(acerto, "") or classe_do_erro(acerto),
                  verso=entrada.versos.get(acerto, ""))
        for palavra in entrada.vocab:
            toque(palavra, "palavra", entrada.day, entrada.when, acerto=False,
                  verso=entrada.versos.get(palavra, ""))
        for palavra in entrada.reused:
            toque(palavra, "palavra", entrada.day, entrada.when, acerto=True,
                  verso=entrada.versos.get(palavra, ""))

    # O que o aluno relatou hoje. Falha rebaixa; "já revisei" só tira do dia.
    local = config.read_revisao_local()
    hoje_iso = date.today().isoformat()
    for registro in local["falhas"]:
        alvo = itens.get(registro.get("chave", ""))
        if alvo is None:
            continue
        try:
            quando = date.fromisoformat(registro.get("data", ""))
        except ValueError:
            continue
        if alvo.visto is None or quando >= alvo.visto:
            alvo.caixa = 0
            alvo.visto = quando
            alvo.aparicoes += 1
    for registro in local["revisados"]:
        alvo = itens.get(registro.get("chave", ""))
        if alvo is not None and registro.get("data") == hoje_iso:
            alvo.revisado_hoje = True

    for item in itens.values():
        if item.visto is not None:
            escala = item.escala
            passo = escala[min(item.caixa, len(escala) - 1)]
            item.vence = item.visto + timedelta(days=passo)

    return sorted(itens.values(), key=lambda i: (i.vence or date.min, i.rotulo))


# Vagas garantidas por classe no baralho do dia. Sem reserva, o passivo de
# vocabulário (que cresce umas quatro palavras por sessão) empurra erro de
# gramática e de pronúncia para fora da lista por atraso bruto — e são justamente
# as duas classes de tolerância zero. Gramática vem primeiro por decisão do dono
# do projeto: agreement e palavra errada mudam o que ele disse; sotaque custa uma
# repetição.
VAGAS = (("gramática", 2), ("pronúncia", 2))


def deck(report: Report, tamanho: int = 5) -> list[ItemRevisao]:
    """O baralho do dia: o que está vencido, com vagas reservadas por classe.

    Limitado de propósito. Fila longa não se revisa — se tudo está atrasado, o
    que importa é fazer cinco hoje, não encarar quarenta.
    """
    devidos = report.vencidos
    if tamanho <= 0:
        return []

    escolhidos: list[ItemRevisao] = []
    for classe, vagas in VAGAS:
        candidatos = [i for i in devidos if i.classe == classe]
        livre = max(tamanho - len(escolhidos), 0)
        escolhidos.extend(candidatos[: min(vagas, livre)])

    for item in devidos:
        if len(escolhidos) >= tamanho:
            break
        if item not in escolhidos:
            escolhidos.append(item)
    return escolhidos


def _current_streak(done: list[int]) -> int:
    if not done:
        return 0
    streak = 1
    for prev, cur in zip(reversed(done[:-1]), reversed(done[1:])):
        if cur - prev == 1:
            streak += 1
        else:
            break
    return streak


def _longest_streak(done: list[int]) -> int:
    best = run = 0
    previous: int | None = None
    for day in done:
        run = run + 1 if previous is not None and day - previous == 1 else 1
        best = max(best, run)
        previous = day
    return best


def _group_errors(entries: list[Entry], limit: int = 12) -> list[ErrorGroup]:
    buckets: dict[str, ErrorGroup] = {}
    for entry in entries:
        for raw in entry.errors:
            key = normalize(raw)
            if not key:
                continue
            group = buckets.get(key)
            if group is None:
                buckets[key] = ErrorGroup(label=raw, count=1, days=[entry.day])
            else:
                group.count += 1
                if entry.day not in group.days:
                    group.days.append(entry.day)
    ordered = sorted(buckets.values(), key=lambda g: (-g.count, g.days[0], g.label))
    return ordered[:limit]


def _themes(entries: list[Entry], limit: int = 10) -> list[tuple[str, int]]:
    """Palavras que mais aparecem nos erros: mostra o padrão por trás deles.

    `sorted` no lugar do `set` cru porque a ordem de iteração de um set de
    strings muda a cada processo (randomização de hash) e o desempate do
    `most_common` é por ordem de inserção: o mesmo log gerava painéis diferentes.
    """
    counter: Counter[str] = Counter()
    for entry in entries:
        for raw in entry.errors:
            counter.update(sorted(set(keywords(raw))))
    common = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [(word, count) for word, count in common[:limit] if count > 1]


def _collect_vocab(entries: list[Entry]) -> list[VocabItem]:
    seen: dict[str, VocabItem] = {}
    for entry in entries:
        for word in entry.vocab:
            key = normalize(word)
            if not key:
                continue
            if key in seen:
                seen[key].times += 1
            else:
                seen[key] = VocabItem(word=word, first_day=entry.day, times=1)
    return sorted(seen.values(), key=lambda v: (v.first_day, v.word))


def review_deck(report: Report, size: int = 10) -> list[str]:
    """Monta o baralho de revisão: erros mais repetidos primeiro."""
    deck = [g.label for g in report.top_errors[:size]]
    if len(deck) < size:
        deck += [v.word for v in report.vocab[-(size - len(deck)):]]
    return deck
