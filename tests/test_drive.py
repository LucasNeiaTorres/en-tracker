"""Testes da escrita — o único dano irreversível do sistema.

Nada aqui fala com a rede: o que se testa é a decisão de fundir, o que se
preserva e o que se recusa. `push` sobrescrevia o arquivo do Drive com o cache
local, então uma sessão que o professor escreveu entre o último `pull` e o `add`
desaparecia sem aviso.
"""

from __future__ import annotations

import pytest

from english_tracker import config, drive
from english_tracker.parser import parse_log

REMOTO = """DIA 01 — 02/09 — Tipo: D — Tema: um
Erros: erro do dia 1
Palavras novas: to figure out

DIA 02 — 03/09 — Tipo: T — Tema: dois
Erros: erro do dia 2
Palavras novas: boilerplate
"""

LOCAL_COM_DIA_NOVO = REMOTO + """
DIA 03 — 04/09 — Tipo: D — Tema: três
Erros: erro do dia 3
"""


def test_merge_acrescenta_o_dia_que_falta_no_remoto():
    merged = drive.merge_logs(REMOTO, LOCAL_COM_DIA_NOVO)
    assert [e.day for e in parse_log(merged)] == [1, 2, 3]


def test_merge_preserva_o_que_so_existe_no_remoto():
    """O professor escreveu o dia 2 depois do último pull: não se perde."""
    local_sem_dia_2 = """DIA 01 — 02/09 — Tipo: D — Tema: um
Erros: erro do dia 1
Palavras novas: to figure out
"""
    merged = drive.merge_logs(REMOTO, local_sem_dia_2)
    assert [e.day for e in parse_log(merged)] == [1, 2]
    assert "erro do dia 2" in merged


def test_merge_e_idempotente():
    """Dois pushes seguidos não duplicam entrada."""
    uma_vez = drive.merge_logs(REMOTO, LOCAL_COM_DIA_NOVO)
    duas_vezes = drive.merge_logs(uma_vez, LOCAL_COM_DIA_NOVO)
    assert uma_vez == duas_vezes


def test_merge_com_remoto_vazio_usa_o_local():
    assert drive.merge_logs("", LOCAL_COM_DIA_NOVO) == LOCAL_COM_DIA_NOVO


def test_merge_com_local_vazio_preserva_o_remoto():
    assert drive.merge_logs(REMOTO, "") == REMOTO


def test_merge_leva_a_versao_local_quando_o_conteudo_do_dia_mudou():
    corrigido = """DIA 01 — 02/09 — Tipo: D — Tema: um
Erros: erro do dia 1; erro que faltava
Palavras novas: to figure out
"""
    merged = drive.merge_logs(REMOTO, corrigido)
    entradas = {e.day: e for e in parse_log(merged)}
    assert "erro que faltava" in entradas[1].errors
    assert entradas[2].errors == ["erro do dia 2"], "o dia 2 continua lá"


def test_backup_guarda_o_conteudo_anterior(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_PATH", tmp_path / "english-log.md")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")

    drive.write_cache(REMOTO)
    drive.write_cache("DIA 09 — 10/09 — Tipo: T — Tema: só isto\nErros: a\n")

    copias = list((tmp_path / "backups").glob("*.md"))
    assert len(copias) == 1
    assert "erro do dia 2" in copias[0].read_text(encoding="utf-8")


def test_backup_respeita_o_teto(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(config, "BACKUP_KEEP", 3)
    for i in range(6):
        drive.backup(f"conteudo {i}", f"t{i}")
    assert len(list((tmp_path / "backups").glob("*.md"))) <= 3


def test_load_result_desempacota_como_tupla():
    """Compatibilidade com o `text, source = load()` de antes."""
    texto, origem = drive.LoadResult("x", "cache")
    assert (texto, origem) == ("x", "cache")


# ——— publicação do pacote de prompts (arquivo separado do log) ———

class _ServicoFalso:
    """Um Drive de mentira: o suficiente para exercitar a guarda de sobrescrita."""

    def __init__(self, arquivos):
        self.arquivos = arquivos
        self.atualizou = None
        self.criou = None

    def files(self):
        return self

    def list(self, **kwargs):
        self._resposta = {"files": list(self.arquivos)}
        return self

    def update(self, fileId=None, media_body=None, **kwargs):
        self.atualizou = fileId
        self._resposta = {"id": fileId}
        return self

    def create(self, body=None, media_body=None, **kwargs):
        self.criou = body.get("name")
        self._resposta = {"id": "novo"}
        return self

    def execute(self):
        return self._resposta


def test_publish_prompt_cria_quando_nao_existe(monkeypatch):
    pytest.importorskip("googleapiclient")
    servico = _ServicoFalso([])
    monkeypatch.setattr(drive, "_service", lambda write=False: servico)
    assert drive.publish_prompt("PROMPTS DOS DIAS 1 A 7\n...") == "novo"
    assert servico.criou == "english-prompt.md"


def test_publish_prompt_sobrescreve_o_proprio_pacote(monkeypatch):
    pytest.importorskip("googleapiclient")
    servico = _ServicoFalso([{"id": "abc", "name": "english-prompt.md", "mimeType": "text/plain"}])
    monkeypatch.setattr(drive, "_service", lambda write=False: servico)
    monkeypatch.setattr(drive, "_download", lambda s, m: "PROMPTS DOS DIAS 1 A 7\nvelho")
    assert drive.publish_prompt("PROMPTS DOS DIAS 8 A 14\nnovo") == "abc"
    assert servico.atualizou == "abc"


def test_publish_prompt_recusa_arquivo_que_nao_e_o_pacote(monkeypatch):
    """Nome parecido pode ser outra coisa: não se sobrescreve às cegas."""
    pytest.importorskip("googleapiclient")
    servico = _ServicoFalso([{"id": "xyz", "name": "english-prompt.md", "mimeType": "text/plain"}])
    monkeypatch.setattr(drive, "_service", lambda write=False: servico)
    monkeypatch.setattr(drive, "_download", lambda s, m: "minhas anotações pessoais")
    with pytest.raises(drive.DriveRefused):
        drive.publish_prompt("PROMPTS DOS DIAS 1 A 7")
    assert servico.atualizou is None
