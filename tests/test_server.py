"""Testes do modo interativo.

O servidor expõe endpoints que **escrevem no Drive**. Os testes de segurança
daqui não são zelo formal: sem o token, qualquer página aberta no navegador
poderia disparar um `push`; sem a checagem de `Host`, um site externo apontando
um domínio para 127.0.0.1 conversaria com o servidor local.

Nada aqui toca a rede: o servidor sobe em modo offline, numa porta efêmera.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from english_tracker import config, drive, server

LOG = """DIA 01 — 02/09 — Tipo: D — Tema: um
Erros: esqueci o -s na terceira pessoa
Palavras novas: to figure out
Nota do professor: "Barely."
"""

TOKEN = "token-de-teste"


@pytest.fixture
def servidor(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_PATH", tmp_path / "english-log.md")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(config, "WHATSAPP_ENV", "")
    drive.write_cache(LOG)

    server.Handler.estado = server.Estado(token=TOKEN, offline=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def chamar(base, rota, corpo=None, token=TOKEN, host=None):
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(
        base + rota, data=dados, method="POST" if corpo is not None else "GET"
    )
    req.add_header("Content-Type", "application/json")
    if token is not None:
        req.add_header("X-Token", token)
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def test_painel_vem_com_a_barra_de_acoes(servidor):
    status, html = chamar(servidor, "/")
    assert status == 200
    assert 'class="bar"' in html
    assert 'id="form-add"' in html
    assert TOKEN in html, "a página precisa do token para chamar a API"


def test_api_sem_token_e_recusada(servidor):
    status, corpo = chamar(servidor, "/api/push", {}, token=None)
    assert status == 403
    assert "token" in corpo


def test_api_com_token_errado_e_recusada(servidor):
    assert chamar(servidor, "/api/push", {}, token="chute")[0] == 403


def test_host_estranho_e_recusado(servidor):
    """Defesa contra DNS rebinding: só 127.0.0.1 e localhost."""
    assert chamar(servidor, "/api/push", {}, host="evil.example.com")[0] == 403


def test_rota_inexistente(servidor):
    assert chamar(servidor, "/api/qualquer", {})[0] == 404


def test_offline_nao_fala_com_o_drive(servidor):
    for rota in ("/api/pull", "/api/push"):
        dados = json.loads(chamar(servidor, rota, {})[1])
        assert dados["ok"] is False
        assert "offline" in dados["erro"]


def test_add_pela_api_registra_e_conta(servidor):
    corpo = {"dia": 2, "texto": 'Erros: a; b\nPalavras novas: x, y'}
    dados = json.loads(chamar(servidor, "/api/add", corpo)[1])
    assert dados["ok"] is True
    assert "DIA 02" in dados["bloco"]

    cache = config.CACHE_PATH.read_text(encoding="utf-8")
    assert "DIA 01" in cache and "DIA 02" in cache, "o dia novo é acrescentado"

    status, html = chamar(servidor, "/")
    assert "2 de 30" in html


def test_add_sem_texto_nao_registra(servidor):
    antes = config.CACHE_PATH.read_text(encoding="utf-8")
    dados = json.loads(chamar(servidor, "/api/add", {"dia": 2, "texto": "   "})[1])
    assert dados["ok"] is False
    assert config.CACHE_PATH.read_text(encoding="utf-8") == antes


def test_add_em_dia_fora_do_plano_e_recusado(servidor):
    dados = json.loads(chamar(servidor, "/api/add", {"dia": 99, "texto": "Erros: a"})[1])
    assert dados["ok"] is False
    assert "não existe no plano" in dados["erro"]


def test_prompt_pela_api(servidor):
    dados = json.loads(chamar(servidor, "/api/prompt?dia=7")[1])
    assert dados["ok"] is True
    assert dados["dia"] == 7
    assert "You are my English teacher" in dados["prompt"]


def test_erro_na_acao_nao_derruba_o_servidor(servidor, monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(server, "parse_session", explode)
    status, corpo = chamar(servidor, "/api/add", {"dia": 2, "texto": "Erros: a"})
    assert status == 500
    assert "falha simulada" in corpo
    # e o servidor continua atendendo
    assert chamar(servidor, "/")[0] == 200


def test_remove_apaga_o_dia_e_guarda_backup(servidor):
    """O caso real: registrou e enviou sem querer, e precisa desfazer."""
    chamar(servidor, "/api/add", {"dia": 2, "texto": "Erros: engano"})
    assert "DIA 02" in config.CACHE_PATH.read_text(encoding="utf-8")

    dados = json.loads(chamar(servidor, "/api/remove", {"dia": 2})[1])
    assert dados["ok"] is True
    assert "backups/" in dados["mensagem"]

    cache = config.CACHE_PATH.read_text(encoding="utf-8")
    assert "engano" not in cache
    assert "DIA 01" in cache, "o resto do log continua lá"
    assert list(config.BACKUP_DIR.glob("*.md")), "tem de haver cópia do anterior"


def test_remove_de_dia_que_nao_esta_no_log(servidor):
    dados = json.loads(chamar(servidor, "/api/remove", {"dia": 20})[1])
    assert dados["ok"] is False
    assert "não está no log" in dados["erro"]


def test_remove_com_dia_invalido(servidor):
    for valor in ("abc", 0, None):
        dados = json.loads(chamar(servidor, "/api/remove", {"dia": valor})[1])
        assert dados["ok"] is False


def test_painel_renderiza_do_cache_sem_ir_a_rede(servidor, monkeypatch):
    """Carregar a página não pode puxar do Drive: senão "Atualizar" viraria "Puxar"."""
    def nao_deveria(*a, **k):
        raise AssertionError("o painel foi à rede")

    monkeypatch.setattr(drive, "fetch", nao_deveria)
    assert chamar(servidor, "/")[0] == 200


def test_painel_embute_o_detalhe_dos_dias(servidor):
    _, html = chamar(servidor, "/")
    assert 'id="dados-dias"' in html
    assert 'id="detalhe"' in html
    assert "esqueci o -s na terceira pessoa" in html, "o detalhe do dia 1 vai na página"


def test_pagina_de_cards_serve(servidor):
    status, html = chamar(servidor, "/cards")
    assert status == 200
    assert 'id="dados-cards"' in html
    assert 'id="palco"' in html
    assert TOKEN in html


def test_errei_traz_o_item_de_volta(servidor):
    """Autorrelato de falha é confiável: rebaixa o item."""
    from english_tracker.analytics import build_report
    from english_tracker.parser import parse_log

    def agenda():
        rep = build_report(parse_log(config.CACHE_PATH.read_text(encoding="utf-8")))
        return {i.chave: i for i in rep.revisao}

    alvo = next(c for c in agenda() if c.startswith("erro:"))
    dados = json.loads(chamar(servidor, "/api/falha", {"chave": alvo})[1])
    assert dados["ok"] is True
    assert agenda()[alvo].caixa == 0


def test_ja_revisei_tira_do_dia_sem_promover(servidor):
    """Prática não é evidência: só o `Acertos:` do professor promove."""
    from datetime import date, timedelta

    from english_tracker import drive as drive_mod
    from english_tracker.analytics import build_report
    from english_tracker.parser import parse_log

    # log com data antiga, para haver algo REALMENTE vencido
    antiga = (date.today() - timedelta(days=10)).strftime("%d/%m")
    drive_mod.write_cache(
        f"DIA 01 — {antiga} — Tipo: D — Tema: um\nErros: [gram] erro antigo\n"
    )

    def agenda():
        return build_report(parse_log(config.CACHE_PATH.read_text(encoding="utf-8")))

    rep = agenda()
    alvo = rep.vencidos[0]
    caixa_antes = alvo.caixa

    dados = json.loads(chamar(servidor, "/api/revisado", {"chave": alvo.chave})[1])
    assert dados["ok"] is True

    depois = agenda()
    item = next(i for i in depois.revisao if i.chave == alvo.chave)
    assert item.caixa == caixa_antes, "a caixa NÃO pode avançar"
    assert item.revisado_hoje is True
    assert alvo.chave not in [i.chave for i in depois.vencidos], "sai do baralho de hoje"


def test_verso_escrito_pelo_aluno_vai_para_o_log(servidor):
    dados = json.loads(chamar(
        servidor, "/api/verso",
        {"rotulo": "esqueci o -s na terceira pessoa", "verso": "He works here"},
    )[1])
    assert dados["ok"] is True
    assert "He works here" in config.CACHE_PATH.read_text(encoding="utf-8")


def test_verso_de_item_inexistente_e_recusado(servidor):
    dados = json.loads(chamar(
        servidor, "/api/verso", {"rotulo": "item que não existe", "verso": "x"}
    )[1])
    assert dados["ok"] is False


def test_acoes_de_revisao_exigem_token(servidor):
    for rota in ("/api/falha", "/api/revisado", "/api/verso"):
        assert chamar(servidor, rota, {"chave": "x"}, token=None)[0] == 403


def test_pagina_da_semana_lista_os_dias(servidor):
    status, html = chamar(servidor, "/semana")
    assert status == 200
    assert "A semana" in html
    assert "Enviar ao WhatsApp" in html
    assert html.count('class="dia"') >= 5, "um cartão por dia do pacote"
    assert "Publicar a semana no Drive" in html


def test_publicar_pacote_offline_e_recusado(servidor):
    dados = json.loads(chamar(servidor, "/api/pacote", {"dias": 7})[1])
    assert dados["ok"] is False
    assert "offline" in dados["erro"]


def test_publicar_pacote_exige_token(servidor):
    assert chamar(servidor, "/api/pacote", {"dias": 7}, token=None)[0] == 403


# ——— pendências: o painel avisa o que precisa da sua atenção ———

def test_saude_offline_nao_vai_a_rede(servidor):
    dados = json.loads(chamar(servidor, "/api/saude")[1])
    assert dados["ok"] is True
    assert dados["offline"] is True


def test_saude_relata_autorizacao_quebrada(servidor, monkeypatch):
    """O token do Google expira em 7 dias: o painel tem de anunciar antes."""
    monkeypatch.setattr(server.Handler.estado, "offline", False)
    monkeypatch.setattr(
        server.drive, "check_auth",
        lambda write=False: (False, "a autorização expirou"),
    )
    dados = json.loads(chamar(servidor, "/api/saude")[1])
    assert dados["leitura"]["ok"] is False
    assert dados["escrita"]["ok"] is False
    assert "expirou" in dados["leitura"]["motivo"]
    monkeypatch.setattr(server.Handler.estado, "offline", True)


def test_autorizar_offline_e_recusado(servidor):
    dados = json.loads(chamar(servidor, "/api/autorizar", {"escrita": False})[1])
    assert dados["ok"] is False
    assert "offline" in dados["erro"]


def test_saude_e_autorizar_exigem_token(servidor):
    assert chamar(servidor, "/api/saude", token=None)[0] == 403
    assert chamar(servidor, "/api/autorizar", {}, token=None)[0] == 403


def test_painel_mostra_a_pendencia_do_pacote(servidor):
    _, html = chamar(servidor, "/")
    assert "Semana no Drive" in html
    assert "ainda não foi publicada" in html, "sem pacote publicado, tem de cobrar"
    assert "publicar-semana" in html


# ——— expor o painel na rede: o que continua valendo ———

@pytest.fixture
def servidor_leitura(tmp_path, monkeypatch):
    """Painel em modo somente leitura, como se estivesse exposto na rede."""
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_PATH", tmp_path / "english-log.md")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(config, "WHATSAPP_ENV", "")
    drive.write_cache(LOG)

    server.Handler.estado = server.Estado(
        token=TOKEN, offline=True, somente_leitura=True
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_somente_leitura_mostra_o_painel(servidor_leitura):
    status, html = chamar(servidor_leitura, "/")
    assert status == 200
    assert "Folha de chamada" in html
    assert 'class="bar"' not in html, "sem barra de ações no modo leitura"


def test_somente_leitura_recusa_toda_escrita(servidor_leitura):
    """A trava do caso remoto: ver de qualquer lugar, agir só onde o log mora."""
    escritas = {
        "/api/push": {},
        "/api/pull": {},
        "/api/add": {"dia": 2, "texto": "Erros: a"},
        "/api/remove": {"dia": 1},
        "/api/falha": {"chave": "erro:x"},
        "/api/revisado": {"chave": "erro:x"},
        "/api/verso": {"rotulo": "x", "verso": "y"},
        "/api/pacote": {"dias": 7},
        "/api/autorizar": {"escrita": False},
    }
    for rota, corpo in escritas.items():
        status, resposta = chamar(servidor_leitura, rota, corpo)
        assert status == 403, f"{rota} deveria ser recusada"
        assert "somente leitura" in resposta, rota

    assert config.CACHE_PATH.read_text(encoding="utf-8") == LOG, "nada mudou"


def test_somente_leitura_ainda_deixa_ler(servidor_leitura):
    assert chamar(servidor_leitura, "/cards")[0] == 200
    assert chamar(servidor_leitura, "/semana")[0] == 200
    dados = json.loads(chamar(servidor_leitura, "/api/prompt?dia=3")[1])
    assert dados["ok"] is True


def test_host_extra_e_aceito_e_o_resto_recusado(tmp_path, monkeypatch):
    """Exposto na rede, o cabeçalho Host continua sendo conferido."""
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_PATH", tmp_path / "english-log.md")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    drive.write_cache(LOG)

    server.Handler.estado = server.Estado(
        token=TOKEN, offline=True, hosts={"note.tailnet.ts.net"}
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert chamar(base, "/", host="note.tailnet.ts.net")[0] == 200
        assert chamar(base, "/", host="localhost")[0] == 200, "loopback nunca sai"
        assert chamar(base, "/", host="evil.example.com")[0] == 403
    finally:
        httpd.shutdown()
        httpd.server_close()


# ——— senha: a tranca do acesso remoto ———

@pytest.fixture
def servidor_com_senha(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_PATH", tmp_path / "english-log.md")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(config, "WHATSAPP_ENV", "")
    drive.write_cache(LOG)

    server.Handler.estado = server.Estado(
        token=TOKEN, offline=True, senha="abre-te-sesamo"
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _com_basic(base, rota, senha, corpo=None):
    import base64

    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(
        base + rota, data=dados, method="POST" if corpo is not None else "GET"
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Token", TOKEN)
    if senha is not None:
        cru = base64.b64encode(f"lucas:{senha}".encode()).decode()
        req.add_header("Authorization", f"Basic {cru}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def test_sem_senha_o_painel_pede_autenticacao(servidor_com_senha):
    status, _ = _com_basic(servidor_com_senha, "/", senha=None)
    assert status == 401


def test_senha_errada_e_recusada(servidor_com_senha):
    assert _com_basic(servidor_com_senha, "/", senha="chute")[0] == 401


def test_senha_certa_abre_o_painel(servidor_com_senha):
    status, html = _com_basic(servidor_com_senha, "/", senha="abre-te-sesamo")
    assert status == 200
    assert "Folha de chamada" in html


def test_senha_protege_tambem_a_api(servidor_com_senha):
    """Não adianta trancar a página e deixar a API aberta."""
    assert _com_basic(servidor_com_senha, "/api/push", None, {})[0] == 401
    assert _com_basic(servidor_com_senha, "/api/prompt?dia=2", "chute")[0] == 401


def test_tentativas_demais_travam_a_origem(servidor_com_senha):
    """Painel exposto é varrido por robô: sem freio, a senha cai por tempo."""
    for _ in range(server.MAX_TENTATIVAS):
        _com_basic(servidor_com_senha, "/", senha="chute")
    status, corpo = _com_basic(servidor_com_senha, "/", senha="abre-te-sesamo")
    assert status == 429, "depois do limite, nem a senha certa passa na hora"
    assert "tentativas demais" in corpo
