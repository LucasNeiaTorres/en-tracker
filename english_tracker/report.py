"""Gera o painel HTML a partir do relatório."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import plan, prompt as prompt_mod
from .analytics import Report, deck

TEMPLATE_DIR = Path(__file__).parent / "templates"


@dataclass
class Cell:
    day: int
    kind: str
    kind_label: str
    topic: str
    state: str  # done | illegible | missing | next | future


def _cells(report: Report) -> list[Cell]:
    done = set(report.done_days)
    illegible = set(report.illegible_days)
    missing = set(report.missing_days)
    out: list[Cell] = []
    for day in range(1, plan.TOTAL_DAYS + 1):
        pd = plan.PLAN[day]
        if day in done:
            state = "done"
        elif day in illegible:
            # Registrado e inaproveitável: não é feito nem buraco.
            state = "illegible"
        elif day in missing:
            state = "missing"
        elif day == report.next_day:
            state = "next"
        else:
            state = "future"
        out.append(Cell(day, pd.kind, pd.kind_label, pd.topic, state))
    return out


def _detalhes(report: Report) -> str:
    """Dados de cada dia registrado, para o painel mostrar ao clicar na célula.

    Vai embutido na página como JSON: ver um dia não precisa de servidor, então
    funciona também no arquivo estático do `report`. O `</` escapado evita que um
    texto do log feche a tag `script` — o conteúdo é escrito por um modelo, não
    se confia no formato.
    """
    dados = {}
    for entrada in report.entries:
        pd = plan.get(entrada.day)
        dados[str(entrada.day)] = {
            "dia": entrada.day,
            "data": entrada.when.strftime("%d/%m/%Y") if entrada.when else "",
            "tipo": (pd.kind_label if pd else "") or "",
            "tema": entrada.topic or (pd.topic if pd else ""),
            "erros": entrada.errors,
            "vocab": entrada.vocab,
            "nota": entrada.note,
            "extra": entrada.extra,
            "status": entrada.status,
            "no_plano": pd is not None,
        }
    bruto = json.dumps(dados, ensure_ascii=False)
    return bruto.replace("</", "<\\/").replace("\u2028", "").replace("\u2029", "")


def _sincronizacao(quando: datetime | None) -> str:
    if quando is None:
        return ""
    minutos = int((datetime.now() - quando).total_seconds() // 60)
    if minutos < 1:
        return "agora"
    if minutos < 60:
        return f"há {minutos} min"
    horas = minutos // 60
    if horas < 24:
        return f"há {horas}h"
    return quando.strftime("%d/%m %H:%M")


TAREFAS = {
    "pronúncia": "Diga a palavra 3x, devagar, som por som — e depois numa frase sua.",
    "gramática": "Diga uma frase sua aplicando a regra certa. Depois outra, diferente.",
    "vocabulário": "Use a palavra certa numa frase sua — e diga o que a errada significa.",
    "fluência": "Diga em inglês, sem parar, o que você travou para dizer.",
}
TAREFA_PALAVRA = "Use esta palavra numa frase sua, sem consultar nada."
TAREFA_ERRO = "Diga a forma certa numa frase sua."


def cards_json(report: Report, tamanho: int = 12) -> str:
    """Os cartões do dia: a agenda vencida, com verso quando existe.

    O verso vem do log — forma certa, frase-modelo ou gloss que o professor
    escreveu, ou que o aluno preencheu depois. Quando não existe, o cartão diz
    isso na cara: inventar a correção aqui seria o programa palpitando inglês.
    """
    de_onde = {}
    for entrada in report.entries:
        for rotulo in list(entrada.errors) + list(entrada.vocab):
            registro = de_onde.setdefault(rotulo, {"temas": [], "nota": ""})
            if entrada.topic and entrada.topic not in registro["temas"]:
                registro["temas"].append(entrada.topic)
            if entrada.note:
                registro["nota"] = entrada.note

    cartoes = []
    # Mesma seleção do `deck` do terminal — inclusive as vagas reservadas para
    # gramática e pronúncia. Duas ordenações para o mesmo conceito seria defeito.
    for item in deck(report, tamanho=tamanho):
        contexto = de_onde.get(item.rotulo, {"temas": [], "nota": ""})
        if item.tipo == "palavra":
            tarefa = TAREFA_PALAVRA
        else:
            tarefa = TAREFAS.get(item.classe, TAREFA_ERRO)
        cartoes.append({
            "chave": item.chave,
            "rotulo": item.rotulo,
            "frente": item.rotulo,
            "verso": item.verso,
            "tipo": item.tipo,
            "classe": item.classe,
            "caixa": item.caixa,
            "caixas": len(item.escala),
            "atraso": item.atraso(report.generated_at),
            "aparicoes": item.aparicoes,
            "dias": item.dias,
            "temas": ", ".join(contexto["temas"][:3]),
            "nota": contexto["nota"],
            "tarefa": tarefa,
        })

    bruto = json.dumps(cartoes, ensure_ascii=False)
    return bruto.replace("</", "<\\/").replace("\u2028", "").replace("\u2029", "")


def render_semana(
    report: Report,
    token: str = "",
    whatsapp: str = "",
    dias: int = 7,
    drive_file: str = "english-log",
) -> str:
    return _env().get_template("semana.html").render(
        blocos=prompt_mod.pacote_dias(report, dias, drive_file),
        token=token,
        whatsapp=whatsapp,
    )


def render_login(erro: str = "", destino: str = "/") -> str:
    """A tela de senha. Não recebe `Report` porque não pode: ela é o que se vê
    ANTES de ter direito de ler o log."""
    return _env().get_template("login.html").render(erro=erro, destino=destino)


def render_cards(report: Report, token: str = "") -> str:
    return _env().get_template("cards.html").render(
        cards=cards_json(report), token=token
    )


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _pendencia_pacote(report: Report, info: dict) -> dict:
    """O pacote da semana ainda serve? Decidido só com informação local.

    Três motivos para republicar: nunca foi publicado, o dia de hoje passou do
    último dia coberto, ou já faz uma semana — que é quando o histórico e a
    agenda dentro dos prompts ficam velhos demais para valerem.
    """
    if not info:
        return {"estado": "ausente", "texto": "A semana ainda não foi publicada no Drive."}

    ultimo = int(info.get("ultimo") or 0)
    primeiro = int(info.get("primeiro") or 0)
    try:
        quando = date.fromisoformat(info.get("em", ""))
    except ValueError:
        quando = None
    idade = (date.today() - quando).days if quando else None
    proximo = report.next_day

    if proximo is not None and proximo > ultimo:
        return {
            "estado": "vencido",
            "texto": f"O pacote cobre os dias {primeiro} a {ultimo} e você já está "
                     f"no dia {proximo}: o celular está sem prompt.",
        }
    if idade is not None and idade >= 7:
        return {
            "estado": "velho",
            "texto": f"O pacote foi publicado há {idade} dias. O tema de cada dia "
                     f"continua certo, mas o histórico e a lista de revisão dentro "
                     f"dos prompts são daquele dia.",
        }
    return {
        "estado": "ok",
        "texto": f"Semana publicada{' há ' + str(idade) + 'd' if idade else ' hoje'}, "
                 f"cobrindo os dias {primeiro} a {ultimo}.",
    }


def render(
    report: Report,
    source: str = "cache",
    drive_file: str = "english-log",
    whatsapp: str = "",
    interactive: bool = False,
    token: str = "",
    warnings: list[str] | None = None,
    last_sync: datetime | None = None,
    pacote: dict | None = None,
) -> str:
    """Renderiza o painel.

    `interactive=True` só é usado pelo `serve`: acrescenta a barra de ações e o
    token das chamadas de API. O arquivo gerado pelo `report` continua inerte —
    um HTML que você pode guardar ou mandar por e-mail sem carregar botões que
    não funcionariam fora do servidor.
    """
    template = _env().get_template("dashboard.html")

    next_plan = plan.get(report.next_day) if report.next_day else None
    next_prompt = (
        prompt_mod.build(report.next_day, report, drive_file) if next_plan else ""
    )

    return template.render(
        report=report,
        days=_cells(report),
        plan_total=plan.TOTAL_DAYS,
        source=source,
        # Só sessão aproveitável entra em "Últimas sessões": dia fora do plano
        # ou registrado-e-ilegível não é sessão, e apareceria como bloco vazio.
        recent=list(reversed(
            [e for e in report.entries if e.ok and e.day in plan.PLAN][-6:]
        )),
        next_plan=next_plan,
        next_prompt=next_prompt,
        whatsapp=whatsapp,
        interactive=interactive,
        token=token,
        warnings=warnings or [],
        detalhes=_detalhes(report),
        sincronizado=_sincronizacao(last_sync),
        pacote=_pendencia_pacote(report, pacote or {}),
    )


def write(
    report: Report,
    path: Path,
    source: str = "cache",
    drive_file: str = "english-log",
    whatsapp: str = "",
    last_sync: datetime | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render(report, source, drive_file, whatsapp, last_sync=last_sync),
        encoding="utf-8",
    )
    return path
