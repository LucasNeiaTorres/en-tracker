"""Testes da linha de comando.

O `add` é o mecanismo que existe porque o professor falha em escrever no Drive —
e era ele que tinha os dois defeitos mais desagradáveis: com `--file` gravava no
cache em vez do arquivo pedido, e quando o texto colado não casava o formato o
texto era descartado, deixando registrada uma sessão vazia com cara de sessão
feita.
"""

from __future__ import annotations

import io

from english_tracker import cli, config, drive

CANONICO = """DIA 05 — 06/09 — Tipo: D — Tema: fim de semana
Erros: "I have 28 years" → "I'm 28"; esqueci o -s
Palavras novas: to figure out, kind of
Nota do professor: "Barely."
"""


def _isola(tmp_path, monkeypatch):
    """Nada de tocar no ~/.english-tracker de verdade."""
    monkeypatch.setattr(config, "APP_DIR", tmp_path / "app")
    monkeypatch.setattr(config, "CACHE_PATH", tmp_path / "app" / "english-log.md")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "app" / "backups")


def _roda(argv, entrada, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(entrada))
    args = cli.build_parser().parse_args(argv)
    return args.func(args)


def test_add_com_file_escreve_no_arquivo_e_nao_no_cache(tmp_path, monkeypatch):
    _isola(tmp_path, monkeypatch)
    log = tmp_path / "meu-log.md"
    log.write_text("DIA 01 — 02/09 — Tipo: D — Tema: um\nErros: a\n", encoding="utf-8")

    codigo = _roda(["--file", str(log), "--offline", "add", "--day", "5"],
                   CANONICO, monkeypatch)

    assert codigo == 0
    conteudo = log.read_text(encoding="utf-8")
    assert "DIA 05" in conteudo and "DIA 01" in conteudo
    assert not config.CACHE_PATH.exists(), "--file não deve escrever no cache"


def test_add_preserva_o_texto_que_nao_casa_o_formato(tmp_path, monkeypatch):
    _isola(tmp_path, monkeypatch)
    log = tmp_path / "meu-log.md"
    log.write_text("", encoding="utf-8")
    prosa = "hoje falei de kafka, errei o -s de novo e travei em 'prejudicar'"

    codigo = _roda(["--file", str(log), "--offline", "add", "--day", "5"],
                   prosa, monkeypatch)

    assert codigo == 0
    assert "prejudicar" in log.read_text(encoding="utf-8")


def test_add_sem_nada_colado_nao_registra_sessao_vazia(tmp_path, monkeypatch):
    _isola(tmp_path, monkeypatch)
    log = tmp_path / "meu-log.md"
    log.write_text("DIA 01 — 02/09 — Tipo: D — Tema: um\nErros: a\n", encoding="utf-8")
    antes = log.read_text(encoding="utf-8")

    codigo = _roda(["--file", str(log), "--offline", "add", "--day", "5"],
                   "   \n\n", monkeypatch)

    assert codigo == 1
    assert log.read_text(encoding="utf-8") == antes


def test_add_offline_apenas_acrescenta_ao_cache(tmp_path, monkeypatch):
    _isola(tmp_path, monkeypatch)
    drive.write_cache("DIA 01 — 02/09 — Tipo: D — Tema: um\nErros: a\n")

    codigo = _roda(["--offline", "add", "--day", "5"], CANONICO, monkeypatch)

    assert codigo == 0
    cache = config.CACHE_PATH.read_text(encoding="utf-8")
    assert "DIA 01" in cache and "DIA 05" in cache


def test_status_roda_com_log_de_exemplo(monkeypatch, capsys):
    args = cli.build_parser().parse_args(
        ["--file", "sample/english-log.md", "--offline", "status"]
    )
    assert args.func(args) == 0
    saida = capsys.readouterr().out
    assert "5/30 sessões" in saida
    assert "Dia sem registro: 5" in saida, "o buraco proposital tem de aparecer"


def test_add_entende_resumo_sem_cabecalho_dia(tmp_path, monkeypatch):
    """O caso MAIS comum do add: ninguém digita "DIA 05" ao colar um resumo."""
    _isola(tmp_path, monkeypatch)
    log = tmp_path / "meu-log.md"
    log.write_text("", encoding="utf-8")
    colado = (
        'Erros: travei em "prejudicar"; esqueci o -s\n'
        "Palavras novas: backoff, to retry\n"
        'Nota do professor: "Ouch."\n'
    )

    assert _roda(["--file", str(log), "--offline", "add", "--day", "5"],
                 colado, monkeypatch) == 0

    from english_tracker.analytics import build_report
    from english_tracker.parser import parse_log
    rep = build_report(parse_log(log.read_text(encoding="utf-8")))
    assert rep.done_days == [5], "o dia tem de contar como feito"
    assert rep.total_errors == 2, "os erros colados têm de entrar na conta"
    assert rep.vocab_count == 2


def test_report_gera_o_arquivo(tmp_path, monkeypatch):
    """Faltava teste do `report`: um parâmetro a mais quebrou o comando em silêncio."""
    _isola(tmp_path, monkeypatch)
    saida = tmp_path / "painel.html"
    args = cli.build_parser().parse_args(
        ["--file", "sample/english-log.md", "--offline", "report",
         "-o", str(saida), "--no-open"]
    )
    assert args.func(args) == 0
    html = saida.read_text(encoding="utf-8")
    assert "Folha de chamada" in html
    assert 'id="dados-dias"' in html
    assert 'id="whats"' in html


def test_remove_pela_cli(tmp_path, monkeypatch):
    _isola(tmp_path, monkeypatch)
    log = tmp_path / "meu-log.md"
    log.write_text(
        "DIA 01 — 02/09 — Tipo: D — Tema: um\nErros: fica\n\n"
        "DIA 02 — 03/09 — Tipo: T — Tema: dois\nErros: sai\n",
        encoding="utf-8",
    )
    args = cli.build_parser().parse_args(
        ["--file", str(log), "--offline", "remove", "--day", "2"]
    )
    assert args.func(args) == 0
    conteudo = log.read_text(encoding="utf-8")
    assert "fica" in conteudo and "sai" not in conteudo


def test_remove_de_dia_inexistente_falha(tmp_path, monkeypatch):
    _isola(tmp_path, monkeypatch)
    log = tmp_path / "meu-log.md"
    log.write_text("DIA 01 — 02/09 — Tipo: D — Tema: um\nErros: a\n", encoding="utf-8")
    args = cli.build_parser().parse_args(
        ["--file", str(log), "--offline", "remove", "--day", "9"]
    )
    assert args.func(args) == 1
