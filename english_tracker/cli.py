"""Linha de comando do English Tracker.

    english-tracker status          resumo no terminal, com dias faltando
    english-tracker report          gera e abre o painel HTML
    english-tracker prompt [--day]  imprime o prompt pronto para colar
    english-tracker add             registra uma sessão na mão
    english-tracker push            funde o cache local no arquivo do Drive
    english-tracker deck            revisão espaçada do dia, em voz alta
    english-tracker remove --day N  apaga um dia do log
    english-tracker serve           painel interativo: as ações viram botões
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import date
from pathlib import Path

from . import analytics, config, drive, parser as log_parser, plan, prompt as prompt_mod, report as report_mod, server as server_mod

BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
DIM = "\033[2m"
OFF = "\033[0m"


def _destino(args) -> Path:
    """Onde o `add` escreve. Com --file, é o próprio arquivo passado.

    Antes o `add --file X` lia X e gravava no cache, o que deixava o cache com
    uma entrada só — e o `push` seguinte levava isso para o Drive.
    """
    return Path(args.file).expanduser() if args.file else config.CACHE_PATH


def _load(args) -> tuple[analytics.Report, drive.LoadResult]:
    if args.file:
        path = Path(args.file).expanduser()
        texto = path.read_text(encoding="utf-8") if path.exists() else ""
        resultado = drive.LoadResult(texto, "arquivo")
    else:
        resultado = drive.load(prefer_remote=not args.offline)
    entries = log_parser.parse_log(resultado.text)
    return analytics.build_report(entries), resultado


def _avisos(resultado: drive.LoadResult) -> None:
    for aviso in resultado.warnings:
        print(f"\n{RED}Atenção:{OFF} {aviso}")


def _anomalias(rep: analytics.Report) -> None:
    """Dia registrado que não deu para aproveitar. Some tão pouco quanto buraco."""
    if rep.illegible_days:
        dias = ", ".join(map(str, rep.illegible_days))
        print(f"\n{RED}Registrado, mas ilegível: {dias}{OFF}")
        print(f"{DIM}Tem cabeçalho DIA no log, mas nenhum erro, palavra ou nota "
              f"que o parser tenha aproveitado. Confira o texto do professor e "
              f"reescreva com `english-tracker add`.{OFF}")
    if rep.unknown_days:
        dias = ", ".join(map(str, rep.unknown_days))
        print(f"\n{RED}Fora do plano de {plan.TOTAL_DAYS} dias: {dias}{OFF}")
        print(f"{DIM}Número de dia provavelmente errado no log. Não conta como "
              f"sessão e não entra nas estatísticas.{OFF}")


def cmd_status(args) -> int:
    rep, resultado = _load(args)
    print(f"\n{BOLD}English log{OFF} {DIM}({resultado.source}){OFF}")
    dia = "dia seguido" if rep.current_streak == 1 else "dias seguidos"
    print(f"{rep.total_sessions}/{plan.TOTAL_DAYS} sessões · "
          f"{rep.current_streak} {dia} (recorde {rep.longest_streak}) · "
          f"{rep.total_errors} correç{'ão' if rep.total_errors == 1 else 'ões'} · "
          f"{rep.vocab_count} palavra{'' if rep.vocab_count == 1 else 's'}")

    _avisos(resultado)

    if rep.missing_days:
        rotulo = "Dia sem registro" if len(rep.missing_days) == 1 else "Dias sem registro"
        print(f"\n{RED}{rotulo}: {', '.join(map(str, rep.missing_days))}{OFF}")
        print(f"{DIM}Se você fez a sessão, o professor não salvou no Drive. "
              f"Use `english-tracker add`.{OFF}")
    elif not rep.has_anomalies:
        print(f"\n{GREEN}Nenhum buraco no log.{OFF}")

    _anomalias(rep)

    if rep.top_errors:
        print(f"\n{BOLD}Erros que mais voltam{OFF}")
        for group in rep.top_errors[:6]:
            print(f"  {group.count}x  {group.label}  {DIM}dias {group.days}{OFF}")

    if rep.next_day:
        pd = plan.get(rep.next_day)
        print(f"\n{BOLD}Próxima: dia {pd.day} ({pd.kind_label}){OFF}\n  {pd.topic}")
    else:
        print(f"\n{GREEN}Plano concluído.{OFF}")
    print()
    return 0


def cmd_report(args) -> int:
    rep, resultado = _load(args)
    out = Path(args.output).expanduser().resolve()
    report_mod.write(
        rep, out,
        source=resultado.source,
        drive_file=config.DRIVE_FILE_NAME,
        whatsapp=config.whatsapp_number(),
        last_sync=config.read_sync(),
    )
    _avisos(resultado)
    print(f"Painel gerado: {out}")
    if not args.no_open:
        webbrowser.open(out.as_uri())
    return 0


def cmd_prompt(args) -> int:
    rep, _ = _load(args)
    day = args.day or rep.next_day
    if day is None:
        print("Plano concluído — não há próximo dia.", file=sys.stderr)
        return 1
    completo = None
    if args.completo:
        completo = True
    elif args.curto:
        completo = False

    if args.pacote:
        texto = prompt_mod.pacote(rep, dias=args.pacote, drive_file=config.DRIVE_FILE_NAME)
        if args.para_o_drive:
            try:
                drive.publish_prompt(texto)
            except (drive.DriveUnavailable, drive.DriveRefused) as exc:
                print(f"{RED}Pacote não publicado: {exc}{OFF}", file=sys.stderr)
                return 1
            dias = [b["dia"] for b in prompt_mod.pacote_dias(rep, args.pacote)]
            print(f'{GREEN}Pacote dos dias {dias[0]} a {dias[-1]} publicado como '
                  f'"{drive.PROMPT_FILE_NAME}.md" no seu Drive.{OFF}')
            print(f"{DIM}Abra pelo app do Drive no celular; não precisa do "
                  f"notebook até a próxima geração.{OFF}")
            return 0
        print(texto)
        return 0

    print(prompt_mod.build(day, rep, config.DRIVE_FILE_NAME, completo=completo))
    return 0


def cmd_deck(args) -> int:
    """O baralho do dia: dois minutos de recuperação, em voz alta, fora da sessão."""
    rep, resultado = _load(args)
    itens = analytics.deck(rep, tamanho=args.tamanho)

    if not itens:
        _avisos(resultado)
        if rep.revisao:
            proximo = min((i for i in rep.revisao if i.vence), key=lambda i: i.vence, default=None)
            quando = proximo.vence.strftime("%d/%m") if proximo else "?"
            print(f"\n{GREEN}Nada vencido hoje.{OFF} {DIM}Próximo item em {quando}.{OFF}\n")
        else:
            print(f"\n{DIM}Nada na agenda ainda — ela se monta a partir do log.{OFF}\n")
        return 0

    atrasados = sum(1 for i in itens if i.atraso(rep.generated_at) > 0)
    print(f"\n{BOLD}Revisão de hoje{OFF} {DIM}— {len(itens)} "
          f"{'item' if len(itens) == 1 else 'itens'}, em voz alta{OFF}")
    print(f"{DIM}Diga uma frase completa com cada um. Errar aqui é o objetivo: "
          f"é o que faz o item voltar mais cedo.{OFF}\n")

    for numero, item in enumerate(itens, 1):
        atraso = item.atraso(rep.generated_at)
        quando = f"vencido há {atraso}d" if atraso > 0 else "vence hoje"
        marca = RED if atraso > 3 else DIM
        if item.classe == "pronúncia":
            tarefa = "diga a palavra 3x e depois numa frase — devagar, som por som"
        elif item.tipo == "erro":
            tarefa = "diga a forma certa numa frase sua"
        else:
            tarefa = "use numa frase sua"
        etiqueta = f"{item.tipo}·{item.classe}" if item.classe else item.tipo
        print(f"  {numero}. {item.rotulo}")
        print(f"     {marca}{etiqueta} · {quando} · caixa {item.caixa}"
              f"/{len(item.escala)} · dias {item.dias}{OFF}")
        print(f"     {DIM}{tarefa}{OFF}\n")

    if atrasados:
        print(f"{DIM}{atrasados} de {len(itens)} já passaram do prazo. "
              f"A fila inteira tem {len(rep.vencidos)} vencidos.{OFF}")
    pron = [i for i in itens if i.classe == "pronúncia"]
    if pron:
        print(f"{DIM}{len(pron)} de pronúncia — intervalos mais curtos, porque "
              f"pronúncia decai mais rápido e só a sessão de voz corrige.{OFF}")
    if rep.dominados:
        print(f"{GREEN}Dominados até agora: {len(rep.dominados)}{OFF} "
              f"{DIM}({', '.join(i.rotulo for i in rep.dominados[:3])}"
              f"{'…' if len(rep.dominados) > 3 else ''}){OFF}")
    print()
    return 0


def cmd_add(args) -> int:
    rep, resultado = _load(args)
    day = args.day or rep.next_day
    if day is None:
        print("Plano concluído.", file=sys.stderr)
        return 1
    pd = plan.get(day)
    if pd is None:
        print(f"Dia {day} não existe no plano (1 a {plan.TOTAL_DAYS}).", file=sys.stderr)
        return 1

    print(f"Registrando o dia {day} ({pd.kind_label}: {pd.topic}).")
    print(f"Cole o resumo do professor e termine com {BOLD}Ctrl-D{OFF}.\n", flush=True)
    colado = sys.stdin.read()

    if not colado.strip():
        # Registrar sessão vazia é o erro que este programa existe para evitar.
        print(f"\n{RED}Nada colado — nada foi registrado.{OFF}", file=sys.stderr)
        return 1

    entrada = log_parser.parse_session(colado, day)
    if entrada is not None:
        entry = entrada
        entry.kind = entry.kind or pd.kind
        entry.topic = entry.topic or pd.topic
    else:
        # Não deu para ler o formato: o texto vai para o log como prosa, em vez
        # de ser descartado e virar uma entrada vazia.
        entry = log_parser.Entry(
            day=day, when=date.today(), kind=pd.kind, topic=pd.topic,
            extra=colado.strip(),
        )
        print(f"\n{RED}Não entendi o formato do resumo.{OFF}")
        print(f"{DIM}Guardei o texto colado no log, em 'Resumo colado', para não "
              f"perdê-lo. Os erros e as palavras não foram extraídos — se quiser "
              f"contabilizados, cole no formato do contrato de dados.{OFF}")
    entry.when = entry.when or date.today()

    destino = _destino(args)
    atual = destino.read_text(encoding="utf-8") if destino.exists() else ""
    bloco = log_parser.render_entry(entry)
    juntado = (atual.rstrip() + "\n\n" + bloco + "\n") if atual.strip() else bloco + "\n"

    if args.file:
        drive.backup(atual, "arquivo")
        destino.write_text(juntado, encoding="utf-8")
        print(f"\nRegistrado em {destino}:\n\n{bloco}\n")
        print(f"{DIM}--file não fala com o Drive. Para subir, rode sem --file.{OFF}")
        return 0

    drive.write_cache(juntado, backup_tag="pre-add")
    print(f"\nRegistrado localmente:\n\n{bloco}\n")

    if not args.offline:
        try:
            drive.push(juntado)
            print(f"{GREEN}Enviado para o Drive.{OFF}")
        except (drive.DriveUnavailable, drive.DriveRefused) as exc:
            print(f"{RED}Drive não atualizado: {exc}{OFF}")
            print(f"{DIM}O registro local está salvo. Rode `english-tracker push` "
                  f"depois.{OFF}")
    return 0


def cmd_remove(args) -> int:
    """Apaga um dia do log. Precisa substituir o remoto: fusão não remove nada."""
    destino = _destino(args)
    atual = destino.read_text(encoding="utf-8") if destino.exists() else ""

    # Apagar SUBSTITUI o arquivo do Drive; partir de um cache velho levaria junto
    # o que tivesse chegado depois da última sincronização.
    if not args.file and not args.offline:
        try:
            atual = drive.fetch().text
            drive.write_cache(atual, backup_tag="pre-remove-sync")
        except drive.DriveUnavailable as exc:
            print(f"{RED}Não deu para conferir o Drive antes de apagar: {exc}{OFF}",
                  file=sys.stderr)
            return 1

    novo, removidas = log_parser.remove_day(atual, args.day)
    if not removidas:
        print(f"O dia {args.day} não está no log.", file=sys.stderr)
        return 1

    if args.file:
        drive.backup(atual, "arquivo")
        destino.write_text(novo, encoding="utf-8")
        print(f"Dia {args.day} apagado de {destino}. Cópia do anterior em backups/.")
        return 0

    drive.write_cache(novo, backup_tag=f"pre-remove-dia{args.day}")
    print(f"Dia {args.day} apagado do log local. Cópia do anterior em backups/.")

    if args.offline:
        print(f"{DIM}Modo offline: o Drive ainda tem o dia. Rode `push` depois.{OFF}")
        return 0

    print(f"{DIM}Remoção não se propaga por fusão: o arquivo do Drive será "
          f"SUBSTITUÍDO pelo log local.{OFF}")
    try:
        drive.push(novo, force=True)
        print(f"{GREEN}Drive atualizado sem o dia {args.day}.{OFF}")
    except (drive.DriveUnavailable, drive.DriveRefused) as exc:
        print(f"{RED}Drive não atualizado: {exc}{OFF}", file=sys.stderr)
        print(f"{DIM}O log local já está sem o dia. Rode `push --force` quando resolver.{OFF}")
        return 1
    return 0


def cmd_push(args) -> int:
    text = drive.read_cached()
    if not text.strip():
        print("Cache local vazio — nada para enviar.", file=sys.stderr)
        return 1
    try:
        drive.push(text, force=args.force)
    except (drive.DriveUnavailable, drive.DriveRefused) as exc:
        print(f"{RED}{exc}{OFF}", file=sys.stderr)
        return 1
    if args.force:
        print("Cache local enviado com --force: o conteúdo do Drive foi substituído.")
    else:
        print("Cache local fundido no arquivo do Drive.")
    return 0


def cmd_pull(args) -> int:
    try:
        resultado = drive.load(prefer_remote=True, strict=True)
    except drive.DriveUnavailable as exc:
        print(f"{RED}{exc}{OFF}", file=sys.stderr)
        return 1
    when = resultado.modified.strftime("%d/%m %H:%M") if resultado.modified else "?"
    print(f'Baixado "{resultado.name}" (modificado em {when}).')
    _avisos(resultado)
    return 0


def cmd_serve(args) -> int:
    """Painel interativo: as ações do terminal viram botões na própria página."""
    if args.com_senha and not config.senha_do_painel():
        print(f"{RED}--com-senha pedido, mas não há senha configurada.{OFF}",
              file=sys.stderr)
        print(f"{DIM}Defina em ENGLISH_TRACKER_SENHA ou em "
              f"~/.english-tracker/senha (chmod 600). Nunca por argumento: "
              f"argv aparece no `ps` e no histórico do shell.{OFF}", file=sys.stderr)
        return 1
    server_mod.servir(
        porta=args.porta,
        abrir=not args.sem_abrir,
        offline=args.offline,
        host=args.host,
        hosts_extra=args.host_extra or [],
        somente_leitura=args.somente_leitura,
        senha=config.senha_do_painel() if args.com_senha else "",
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="english-tracker", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="usar um arquivo de log local em vez do Drive "
                                   "(no `add`, é também o destino da escrita)")
    ap.add_argument("--offline", action="store_true", help="não tentar falar com o Drive")
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="resumo no terminal").set_defaults(func=cmd_status)

    p_report = sub.add_parser("report", help="gerar o painel HTML")
    p_report.add_argument("-o", "--output", default="dashboard.html")
    p_report.add_argument("--no-open", action="store_true")
    p_report.set_defaults(func=cmd_report)

    p_prompt = sub.add_parser("prompt", help="prompt pronto para colar no Gemini")
    p_prompt.add_argument("--day", type=int)
    p_prompt.add_argument("--curto", action="store_true",
                          help="inventário só com os seus erros registrados")
    p_prompt.add_argument("--completo", action="store_true",
                          help="inventário genérico completo (mais longo)")
    p_prompt.add_argument("--pacote", type=int, metavar="N",
                          help="gerar os próximos N dias de uma vez")
    p_prompt.add_argument("--para-o-drive", action="store_true", dest="para_o_drive",
                          help="publicar o pacote no Drive, para ler do celular")
    p_prompt.set_defaults(func=cmd_prompt)

    p_deck = sub.add_parser("deck", help="revisão espaçada do dia, para dizer em voz alta")
    p_deck.add_argument("--tamanho", type=int, default=5)
    p_deck.set_defaults(func=cmd_deck)

    p_add = sub.add_parser("add", help="registrar uma sessão manualmente")
    p_add.add_argument("--day", type=int)
    p_add.set_defaults(func=cmd_add)

    p_remove = sub.add_parser("remove", help="apagar um dia do log (substitui o remoto)")
    p_remove.add_argument("--day", type=int, required=True)
    p_remove.set_defaults(func=cmd_remove)

    p_push = sub.add_parser("push", help="fundir o cache local no arquivo do Drive")
    p_push.add_argument("--force", action="store_true",
                        help="substituir o conteúdo do Drive em vez de fundir")
    p_push.set_defaults(func=cmd_push)

    sub.add_parser("pull", help="baixar o log do Drive").set_defaults(func=cmd_pull)

    p_serve = sub.add_parser("serve", help="painel interativo, com as ações em botões")
    p_serve.add_argument("--porta", type=int, default=8765)
    p_serve.add_argument("--sem-abrir", action="store_true", dest="sem_abrir",
                         help="não abrir o navegador")
    p_serve.add_argument("--host", default="127.0.0.1",
                         help="onde ouvir. O padrão só aceita esta máquina; mudar "
                              "abre para a rede (use só em rede privada)")
    p_serve.add_argument("--host-extra", action="append", dest="host_extra",
                         metavar="NOME",
                         help="nome de host adicional aceito no cabeçalho Host "
                              "(ex.: o nome da máquina no Tailscale). Repetível")
    p_serve.add_argument("--somente-leitura", action="store_true",
                         dest="somente_leitura",
                         help="mostra tudo e recusa qualquer ação que mude algo")
    p_serve.add_argument("--com-senha", action="store_true", dest="com_senha",
                         help="exigir senha (formulário de login). A senha vem de "
                              "ENGLISH_TRACKER_SENHA ou ~/.english-tracker/senha")
    p_serve.set_defaults(func=cmd_serve)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
