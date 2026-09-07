"""Testes da tranca de senha do painel.

Existem por causa de um defeito real, e o teste que importa mais aqui é o que
reproduz ele: no iPhone, com o painel instalado na tela inicial e fora do Wi-Fi,
a tela mostrava a frase "Senha necessaria." e **mais nada**. Nenhum campo,
nenhum botão, nenhuma saída.

A causa não era rede: era HTTP Basic. Um app em tela cheia no iOS **não exibe o
diálogo nativo de credencial** — ele renderiza o corpo do 401, que era aquela
frase. A correção foi trocar Basic por sessão com formulário, e o que se garante
abaixo é que nenhuma resposta a uma navegação sem sessão volte a ser um beco sem
saída: ou é a tela com o campo de senha, ou é um desvio para ela.
"""

from __future__ import annotations

import http.client
import json
import pathlib
import threading
from http.server import ThreadingHTTPServer

import pytest

from english_tracker import config, drive, server

LOG = """DIA 01 — 02/09 — Tipo: D — Tema: um
Erros: esqueci o -s na terceira pessoa
Nota do professor: "Barely."
"""

TOKEN = "token-de-teste"
SENHA = "senha-de-teste"


@pytest.fixture
def servidor(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_PATH", tmp_path / "english-log.md")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(config, "WHATSAPP_ENV", "")
    drive.write_cache(LOG)

    server.Handler.estado = server.Estado(token=TOKEN, offline=True, senha=SENHA)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def pedir(porta, caminho, metodo="GET", corpo=None, tipo=None, cabecalhos=None):
    """Um pedido cru, SEM seguir desvio.

    `urllib` segue redirecionamento sozinho, e é exatamente o 303 que precisa ser
    inspecionado aqui — inclusive o `Set-Cookie` que viaja nele.
    """
    conexao = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    cabecalhos = dict(cabecalhos or {})
    if tipo:
        cabecalhos["Content-Type"] = tipo
    conexao.request(metodo, caminho, body=corpo, headers=cabecalhos)
    resposta = conexao.getresponse()
    dados = resposta.read().decode("utf-8", "replace")
    saida = (resposta.status, dict(resposta.getheaders()), dados)
    conexao.close()
    return saida


def entrar(porta, senha=SENHA, destino="/"):
    """Faz o login e devolve o valor do cookie de sessão."""
    corpo = f"senha={senha}&destino={destino}"
    status, cabecalhos, _ = pedir(
        porta, "/login", "POST", corpo, "application/x-www-form-urlencoded"
    )
    assert status == 303, cabecalhos
    return cabecalhos["Set-Cookie"].split(";")[0]


# --- o defeito que originou tudo isto ---------------------------------------


def test_navegacao_sem_sessao_nunca_termina_em_texto_cru(servidor):
    """O sintoma no iPhone: 401 com corpo de texto e nenhuma saída.

    Toda navegação sem sessão tem de terminar numa página com campo de senha —
    direto ou depois de um desvio. Nunca num 401 de texto puro, porque é isso
    que o app instalado no iOS mostra em vez de pedir a credencial.
    """
    for caminho in ("/", "/cards", "/semana", "/index.html"):
        status, cabecalhos, corpo = pedir(servidor, caminho)
        assert status == 303, f"{caminho} respondeu {status}: {corpo!r}"
        assert cabecalhos["Location"].startswith("/login"), caminho
        assert "Senha necessaria" not in corpo

    status, _, corpo = pedir(servidor, "/login")
    assert status == 200
    assert 'type="password"' in corpo
    assert "<form" in corpo


def test_o_formulario_nao_exige_senha_para_ser_visto(servidor):
    """Senão a tela que pede a senha pediria a senha: laço fechado."""
    status, _, corpo = pedir(servidor, "/login")
    assert status == 200 and "<form" in corpo


def test_desvio_leva_de_volta_a_pagina_pedida(servidor):
    _, cabecalhos, _ = pedir(servidor, "/cards")
    assert "destino=%2Fcards" in cabecalhos["Location"]

    cookie = entrar(servidor, destino="/cards")
    status, _, corpo = pedir(servidor, "/cards", cabecalhos={"Cookie": cookie})
    assert status == 200 and "flashcard" in corpo.lower()


# --- o fluxo de entrada ------------------------------------------------------


def test_senha_certa_abre_sessao_que_serve_o_painel(servidor):
    cookie = entrar(servidor)
    status, _, corpo = pedir(servidor, "/", cabecalhos={"Cookie": cookie})
    assert status == 200
    assert "DIA 01" in corpo or "class=\"bar\"" in corpo


def test_senha_errada_devolve_o_formulario_com_o_erro(servidor):
    """Errar tem de dar outra chance na mesma tela, não um beco."""
    status, _, corpo = pedir(
        servidor, "/login", "POST", "senha=errada&destino=/",
        "application/x-www-form-urlencoded",
    )
    assert status == 401
    assert "Senha incorreta" in corpo
    assert 'type="password"' in corpo, "sem campo, o usuário não tem como tentar de novo"


def test_cookie_de_outra_sessao_nao_vale(servidor):
    status, _, _ = pedir(servidor, "/", cabecalhos={"Cookie": "en_sessao=inventado"})
    assert status == 303


def test_sair_invalida_a_sessao_no_servidor(servidor):
    """Apagar o cookie no navegador não basta: quem copiou o valor continuaria
    entrando. A sessão morre do lado do servidor."""
    cookie = entrar(servidor)
    status, cabecalhos, _ = pedir(servidor, "/sair", cabecalhos={"Cookie": cookie})
    assert status == 303
    assert "Max-Age=0" in cabecalhos["Set-Cookie"]

    status, _, _ = pedir(servidor, "/", cabecalhos={"Cookie": cookie})
    assert status == 303, "o cookie antigo ainda abria o painel"


# --- propriedades do cookie --------------------------------------------------


def test_cookie_tem_httponly_e_samesite(servidor):
    _, cabecalhos, _ = pedir(
        servidor, "/login", "POST", f"senha={SENHA}&destino=/",
        "application/x-www-form-urlencoded",
    )
    biscoito = cabecalhos["Set-Cookie"]
    assert "HttpOnly" in biscoito
    assert "SameSite=Lax" in biscoito
    assert "Path=/" in biscoito


def test_secure_acompanha_o_esquema_da_requisicao(servidor):
    """`Secure` sempre quebraria o acesso por HTTP na LAN — o navegador
    descartaria o cookie e o login pareceria não funcionar."""
    _, sem_tls, _ = pedir(
        servidor, "/login", "POST", f"senha={SENHA}&destino=/",
        "application/x-www-form-urlencoded",
    )
    assert "Secure" not in sem_tls["Set-Cookie"]

    _, com_tls, _ = pedir(
        servidor, "/login", "POST", f"senha={SENHA}&destino=/",
        "application/x-www-form-urlencoded",
        cabecalhos={"X-Forwarded-Proto": "https"},
    )
    assert "Secure" in com_tls["Set-Cookie"], "atrás do tailscale serve o cookie vai por HTTPS"


# --- as rotas de API se comportam diferente ----------------------------------


def test_api_sem_sessao_responde_json_e_nao_desvio(servidor):
    """Redirecionar um `fetch` para o HTML de login faria o JavaScript engasgar
    tentando ler JSON de uma página."""
    status, cabecalhos, corpo = pedir(servidor, "/api/ping")
    assert status == 401
    assert "json" in cabecalhos["Content-Type"]
    assert json.loads(corpo)["ok"] is False


def test_basic_continua_valendo_para_a_linha_de_comando(servidor):
    """Trocar Basic por sessão não pode ter matado o `curl -u`."""
    import base64

    cru = base64.b64encode(f":{SENHA}".encode()).decode()
    status, _, _ = pedir(servidor, "/", cabecalhos={"Authorization": f"Basic {cru}"})
    assert status == 200


# --- abusos ------------------------------------------------------------------


def test_destino_externo_e_ignorado(servidor):
    """`/login?destino=https://…` seria um redirecionamento aberto: a tela de
    login de um endereço confiável empurrando quem entra para outro site."""
    for veneno in ("https://exemplo.invalido", "//exemplo.invalido", "sem-barra"):
        _, cabecalhos, _ = pedir(
            servidor, "/login", "POST", f"senha={SENHA}&destino={veneno}",
            "application/x-www-form-urlencoded",
        )
        assert cabecalhos["Location"] == "/", veneno


def test_forca_bruta_para_no_freio(servidor):
    corpo = "senha=errada&destino=/"
    tipo = "application/x-www-form-urlencoded"
    for _ in range(server.MAX_TENTATIVAS):
        pedir(servidor, "/login", "POST", corpo, tipo)
    status, _, texto = pedir(servidor, "/login", "POST", corpo, tipo)
    assert status == 429
    assert "Tentativas demais" in texto


def test_senha_certa_depois_do_freio_tambem_espera(servidor):
    """O freio é por origem, não por tentativa: acertar não pode ser a saída,
    senão o robô que varre a senha ganha assim que acerta."""
    corpo = "senha=errada&destino=/"
    tipo = "application/x-www-form-urlencoded"
    for _ in range(server.MAX_TENTATIVAS):
        pedir(servidor, "/login", "POST", corpo, tipo)
    status, _, _ = pedir(
        servidor, "/login", "POST", f"senha={SENHA}&destino=/", tipo
    )
    assert status == 429


# --- o service worker não pode guardar a tela de login -----------------------


def test_service_worker_nao_cacheia_login_nem_resposta_desviada():
    """O pior defeito possível aqui: o formulário de login gravado no cache sob
    a chave do painel. Offline, o app abriria um campo de senha sem servidor
    para responder — nenhuma saída, de novo."""
    sw = (
        pathlib.Path(__file__).resolve().parent.parent
        / "english_tracker" / "static" / "sw.js"
    ).read_text(encoding="utf-8")
    assert "'/login'" in sw, "a tela de login tem de ser excluída do cache"
    assert "!resposta.redirected" in sw, "resposta desviada não pode ser guardada"
