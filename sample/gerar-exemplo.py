#!/usr/bin/env python3
"""Gera um log de exemplo COMPLETO, com datas relativas a hoje.

    python3 sample/gerar-exemplo.py > sample/exemplo-rico.md

Por que gerador e não arquivo fixo: a revisão espaçada trabalha com **datas de
calendário**. Um arquivo com datas cravadas envelhece — em duas semanas tudo
estaria vencido e o exemplo deixaria de mostrar a diferença entre um item que
acabou de ser acertado e outro esquecido há um mês.

O que este exemplo exercita, de propósito:

- **buraco**: o dia 5 não existe (o professor não salvou);
- **registrado mas ilegível**: o dia 8 tem cabeçalho e nada aproveitável;
- **dia fora do plano**: um `DIA 45` digitado errado;
- **tolerância de formato**: cabeçalho em negrito, cabeçalho markdown, erros em
  lista de bullets, rótulo em negrito, preâmbulo educado do modelo, tipo escrito
  por extenso, data entre parênteses;
- **agenda de revisão**: item dominado (cinco acertos), erro que reapareceu e
  voltou para a primeira caixa, palavra reusada várias vezes e palavra exposta
  uma vez e nunca mais.
"""

from __future__ import annotations

from datetime import date, timedelta

HOJE = date.today()


def d(dias_atras: int) -> str:
    return (HOJE - timedelta(days=dias_atras)).strftime("%d/%m")


LOG = f"""DIA 01 — {d(34)} — Tipo: D — Tema: apresentação pessoal
Erros: [gram] "I have 28 years" → "I'm 28"; [gram] esqueci o -s na terceira pessoa; [flu] travei em "achar"
Palavras novas: to figure out, kind of, to be into something, a heads-up
Nota do professor: "You survived. Barely. Your verbs did not."

DIA 02 — {d(31)} — Tipo: T — Tema: injeção de dependência
Erros: [gram] esqueci o -s na terceira pessoa; [gram] "explain about" → "explain"; [pron] architecture
Acertos: [gram] "I have 28 years" → "I'm 28"
Palavras novas: dependency graph, loosely coupled, under the hood, boilerplate
Reusou: to figure out
Nota do professor: "You explained IoC like a man reading a manual upside down."

DIA 03 — {d(28)} — Tipo: D — Tema: pedir comida e reclamar do delivery
Great session today! Here is your summary:
Erros:
- [gram] "I want" em vez de "I'd like"
- [pron] receipt
- esqueci o -s na terceira pessoa
Acertos: [gram] "I have 28 years" → "I'm 28"; [gram] "explain about" → "explain"
Palavras novas: to place an order, refund, on its way
Reusou: to figure out, boilerplate
Nota do professor: "The restaurant would have called the police."

**DIA 04 — {d(24)} — Tipo: Técnico — Tema: auto-configuration e starters**
**Erros:** [gram] "depends of" → "depends on"; [pron] architecture
**Acertos:** [gram] "I have 28 years" → "I'm 28"; [gram] esqueci o -s na terceira pessoa
Palavras novas: opinionated defaults, to override, out of the box, classpath
Reusou: under the hood
Nota do professor: "Better. Still allergic to the letter S."

## DIA 06 — {d(20)} — Tipo: N — Tema: notícia da semana
Erros: [gram] "depends of" → "depends on"; "in my opinion I think" (redundante); [flu] travei em "prejudicar"
Acertos: [gram] "I have 28 years" → "I'm 28"; [pron] receipt
Palavras novas: hype cycle, to roll out, trade-off, game changer
Reusou: to figure out, on its way
Nota do professor: "You had opinions. Some of them were even in English."

DIA 07 ({d(16)}) — Tipo: R — Tema: revisão semanal
Erros: [gram] esqueci o -s na terceira pessoa
Acertos: [gram] "I have 28 years" → "I'm 28"; [gram] "depends of" → "depends on"
Palavras novas: to catch up
Reusou: trade-off, hype cycle, boilerplate
Nota do professor: "Progress. Suspicious, but progress."

DIA 08 — {d(12)} — Tipo: D — Tema: dar direções e resolver algo por telefone
Ótima sessão! Você foi muito bem hoje, continue assim.
Nota do professor: "—"

DIA 09 — {d(9)} — Tipo: T — Tema: Kafka vs RabbitMQ
Erros: [gram] "depends of" → "depends on"; [pron] queue
Acertos: [gram] esqueci o -s na terceira pessoa
Palavras novas: at-least-once, to retry, backoff, partition key
Reusou: trade-off, to roll out
Nota do professor: "Your grammar has a dead letter queue too."

DIA 10 — {d(4)} — Tipo: D — Tema: viagem, check-in e problema no voo
Erros: [gram] ordem de adjetivos; [flu] travei em "atrasado"
Acertos: [pron] architecture; [gram] "I want" em vez de "I'd like"
Palavras novas: to check in, boarding pass, delayed, overbooked
Reusou: a heads-up, to catch up
Nota do professor: "The airline would have upgraded you out of pity."

DIA 45 — {d(3)} — Tipo: D — Tema: número de dia digitado errado
Erros: este erro não deve entrar em estatística nenhuma
Palavras novas: nem esta palavra
Nota do professor: "Dia que não existe no plano."

DIA 11 — {d(1)} — Tipo: T — Tema: idempotência e dead letter queue
Erros: [gram] esqueci o -s na terceira pessoa; [gram] "the informations" → "the information"
Acertos: [gram] "depends of" → "depends on"; [pron] queue
Palavras novas: exactly-once, deduplication
Reusou: backoff, to retry, trade-off
Nota do professor: "One day you will pluralize correctly. Not today."
"""

if __name__ == "__main__":
    print(LOG, end="")
