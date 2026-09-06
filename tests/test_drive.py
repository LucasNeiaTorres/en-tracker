"""Testes da escrita — o único dano irreversível do sistema.

Nada aqui fala com a rede: o que se testa é a decisão de fundir, o que se
preserva e o que se recusa. `push` sobrescrevia o arquivo do Drive com o cache
local, então uma sessão que o professor escreveu entre o último `pull` e o `add`
desaparecia sem aviso.
"""

from __future__ import annotations

import json

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


# ——— conta de serviço: sem navegador, sem expiração de 7 dias ———

CHAVE_FALSA = {
    "type": "service_account",
    "client_email": "painel@projeto.iam.gserviceaccount.com",
    "private_key_id": "x",
    "project_id": "projeto",
}


def test_sem_chave_nao_ha_conta_de_servico(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "SA_ENV", "")
    assert config.service_account_info() is None
    assert drive.conta_de_servico_email() == ""


def test_chave_pela_variavel_de_ambiente(monkeypatch):
    """É assim que um serviço hospedado recebe a chave: o JSON numa variável."""
    monkeypatch.setattr(config, "SA_ENV", json.dumps(CHAVE_FALSA))
    assert config.service_account_info()["client_email"] == CHAVE_FALSA["client_email"]
    assert drive.conta_de_servico_email() == CHAVE_FALSA["client_email"]


def test_chave_pelo_arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "SA_ENV", "")
    (tmp_path / "service-account.json").write_text(json.dumps(CHAVE_FALSA), encoding="utf-8")
    assert config.service_account_info()["client_email"] == CHAVE_FALSA["client_email"]


def test_json_invalido_ou_de_outro_tipo_e_ignorado(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "SA_ENV", "isto não é json")
    assert config.service_account_info() is None
    monkeypatch.setattr(config, "SA_ENV", json.dumps({"type": "authorized_user"}))
    assert config.service_account_info() is None, "só aceita type=service_account"


def test_check_auth_com_conta_de_servico_nao_fala_em_expiracao(monkeypatch):
    monkeypatch.setattr(config, "SA_ENV", json.dumps(CHAVE_FALSA))
    ok, motivo = drive.check_auth(write=True)
    assert ok is True
    assert "conta de serviço" in motivo
    assert "expir" not in motivo, "conta de serviço não expira em 7 dias"


def test_push_com_conta_de_servico_nao_cria_arquivo(monkeypatch):
    """Arquivo criado por conta de serviço pertence a ela, não ao usuário."""
    pytest.importorskip("googleapiclient")
    monkeypatch.setattr(config, "SA_ENV", json.dumps(CHAVE_FALSA))
    servico = _ServicoFalso([])
    monkeypatch.setattr(drive, "_service", lambda write=False: servico)
    with pytest.raises(drive.DriveRefused) as erro:
        drive.push("DIA 01 — 02/09 — Tipo: D — Tema: x\nErros: a\n")
    assert CHAVE_FALSA["client_email"] in str(erro.value)
    assert servico.criou is None


def test_id_fixado_e_por_nome(tmp_path, monkeypatch):
    """Sem isto, pedir o pacote de prompts devolvia o arquivo do log."""
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    config.write_file_id("id-do-log", "english-log")
    config.write_file_id("id-do-pacote", "english-prompt")

    assert config.read_file_id("english-log") == "id-do-log"
    assert config.read_file_id("english-prompt") == "id-do-pacote"
    assert config.read_file_id("outro-arquivo") is None


def test_formato_antigo_do_file_id_continua_valendo(tmp_path, monkeypatch):
    """Quem já tinha o arquivo com um id solto não pode quebrar."""
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    (tmp_path / "file-id").write_text("id-antigo", encoding="utf-8")
    assert config.read_file_id("english-log") == "id-antigo"
    assert config.read_file_id("english-prompt") is None, "id solto é só do log"


def test_limpar_um_nome_nao_derruba_o_outro(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    config.write_file_id("a", "english-log")
    config.write_file_id("b", "english-prompt")
    config.clear_file_id("english-log")
    assert config.read_file_id("english-log") is None
    assert config.read_file_id("english-prompt") == "b"
