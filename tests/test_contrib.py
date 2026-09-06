"""Testes das unidades do systemd em `contrib/`.

Existem porque o padrão dos defeitos deste projeto é sempre o mesmo: **funciona
na máquina onde o código foi escrito e falha na máquina onde ele roda**. As
unidades são o pior caso disso — elas só executam num computador que talvez
esteja a quilômetros, sem ninguém olhando, e o erro aparece como "o painel parou
de atualizar", dias depois.

O que se verifica aqui:

- os argumentos de cada `ExecStart` **passam pelo argparse de verdade** da CLI.
  Renomear ou remover uma opção (`--somente-leitura`, digamos) passaria em todos
  os outros testes e quebraria o serviço remoto em silêncio;
- os arquivos que uma unidade copia existem no repositório;
- as combinações perigosas continuam onde devem: o painel do servidor é somente
  leitura, e o ciclo de deploy tem o portão de testes antes do restart.
"""

from __future__ import annotations

import pathlib
import shlex

import pytest

from english_tracker import cli

CONTRIB = pathlib.Path(__file__).resolve().parent.parent / "contrib"
UNIDADES = sorted(CONTRIB.glob("*.service"))


def execstarts(caminho: pathlib.Path) -> list[str]:
    """Os comandos de um `ExecStart=`, já com as continuações de linha juntadas."""
    texto = caminho.read_text(encoding="utf-8").replace("\\\n", " ")
    return [
        linha[len("ExecStart="):].lstrip("-").strip()
        for linha in texto.splitlines()
        if linha.startswith("ExecStart=")
    ]


def argumentos_do_tracker(comando: str) -> list[str] | None:
    """Os argumentos passados ao english-tracker, ou None se for outro programa."""
    partes = shlex.split(comando.replace("%h", "/home/usuario"))
    if not partes:
        return None
    # Comparar o NOME do executável, não o caminho: o venv mora dentro de
    # .../english-tracker/.venv/bin/, então "contém english-tracker" casaria
    # também com o pip e o python de lá.
    if pathlib.PurePosixPath(partes[0]).name != "english-tracker":
        return None
    return partes[1:]


def opcoes_conhecidas(parser) -> set[str]:
    """Toda opção longa aceita, inclusive as dos subcomandos.

    Comparar nome exato importa: o argparse aceita ABREVIAÇÃO, então uma opção
    renomeada de `--somente-leitura` para `--somente-leituraX` continuaria
    casando pelo prefixo, e o teste passaria enquanto o serviço remoto perderia
    a trava.
    """
    import argparse

    achadas: set[str] = set()
    pilha = [parser]
    while pilha:
        atual = pilha.pop()
        for acao in atual._actions:
            achadas.update(o for o in acao.option_strings if o.startswith("--"))
            if isinstance(acao, argparse._SubParsersAction):
                pilha.extend(acao.choices.values())
    return achadas


def test_ha_unidades_para_testar():
    assert UNIDADES, "nenhuma unidade encontrada em contrib/"


@pytest.mark.parametrize("unidade", UNIDADES, ids=lambda p: p.name)
def test_argumentos_das_unidades_passam_no_argparse(unidade):
    """Uma opção renomeada na CLI quebraria o serviço remoto sem ninguém ver."""
    parser = cli.build_parser()
    encontrou = False
    for comando in execstarts(unidade):
        args = argumentos_do_tracker(comando)
        if args is None:
            continue
        encontrou = True
        parser.parse_args(args)   # levanta SystemExit se a opção não existir mais
        conhecidas = opcoes_conhecidas(parser)
        for argumento in args:
            if argumento.startswith("--"):
                nome = argumento.split("=", 1)[0]
                assert nome in conhecidas, (
                    f"{unidade.name} usa {nome}, que não existe mais na CLI "
                    f"(o argparse aceitou por abreviação, mas o nome mudou)"
                )
    if unidade.name == "english-tracker-atualiza.service":
        return   # esta só chama git, pip, install e systemctl
    assert encontrou, f"{unidade.name} não chama o english-tracker"


def test_o_painel_do_servidor_exige_senha():
    """Ouvir na rede sem senha é o erro que não pode passar despercebido.

    O painel do servidor é COMPLETO (decisão do Lucas: a senha é a tranca), então
    a senha deixou de ser conforto e virou o único obstáculo entre a rede e o
    log — sem ela, qualquer um na LAN apaga um dia.
    """
    comandos = execstarts(CONTRIB / "english-tracker-painel.service")
    args = next(a for a in map(argumentos_do_tracker, comandos) if a)
    opcoes = cli.build_parser().parse_args(args)
    assert opcoes.host == "0.0.0.0", "o painel do servidor ouve na rede"
    assert opcoes.com_senha is True, "ouvir na rede sem senha, nunca"


def test_o_deploy_testa_antes_de_reiniciar():
    """Sem o portão, um commit quebrado chega ao ar em 15 minutos."""
    comandos = execstarts(CONTRIB / "english-tracker-atualiza.service")
    posicao_pytest = next(i for i, c in enumerate(comandos) if "pytest" in c)
    posicao_restart = next(
        i for i, c in enumerate(comandos) if "restart" in c and "painel" in c
    )
    assert posicao_pytest < posicao_restart, "o teste tem de vir antes do restart"


def test_o_deploy_nao_ignora_a_falha_do_portao():
    """`ExecStart=-` faria o systemd seguir mesmo com o teste vermelho."""
    texto = (CONTRIB / "english-tracker-atualiza.service").read_text(encoding="utf-8")
    for linha in texto.splitlines():
        if "pytest" in linha or "restart" in linha:
            assert not linha.startswith("ExecStart=-"), f"não pode ignorar falha: {linha}"


def test_arquivos_copiados_pelo_deploy_existem():
    """A linha de install cita unidades pelo nome; nome errado só falha em produção."""
    for comando in execstarts(CONTRIB / "english-tracker-atualiza.service"):
        if not comando.startswith("/usr/bin/install"):
            continue
        for parte in shlex.split(comando):
            if parte.startswith("contrib/"):
                assert (CONTRIB.parent / parte).exists(), f"não existe: {parte}"


def test_toda_unidade_referenciada_no_guia_existe():
    guia = (CONTRIB / "README.md").read_text(encoding="utf-8")
    for unidade in UNIDADES + sorted(CONTRIB.glob("*.timer")):
        assert unidade.name in guia, f"{unidade.name} não aparece no contrib/README.md"
