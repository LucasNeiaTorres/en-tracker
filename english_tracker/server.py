"""Modo interativo: o painel deixa de ser folha impressa e passa a ter botões.

Um arquivo estático aberto em `file://` não lê o log, não fala com o Drive e não
executa Python. Para o HTML *fazer* as coisas que o terminal faz, algo tem de
escutar do outro lado — e é só isso que este módulo é: um servidor HTTP local,
minúsculo, que expõe as mesmas funções da CLI.

Três decisões, todas por segurança, porque estes endpoints escrevem no seu Drive:

1. **Só `127.0.0.1`.** Nunca `0.0.0.0`: ninguém na rede alcança.
2. **Token por execução.** Gerado a cada `serve`, embutido na página servida e
   exigido em toda chamada de API. Sem isso, qualquer página aberta no seu
   navegador poderia disparar uma escrita no seu Drive por trás.
3. **Confere o `Host`.** Requisição que chega com outro host é recusada — é a
   defesa contra DNS rebinding, em que um site externo resolve um domínio para
   127.0.0.1 e passa a conversar com o servidor local.

Sem dependência nova: `http.server` da biblioteca padrão. O projeto tem quatro
dependências e não precisa de uma quinta para servir seis rotas.
"""

from __future__ import annotations

import base64
import json
import pathlib
import secrets
import threading
import time
import webbrowser
from collections import defaultdict
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from . import analytics, config, drive, plan, prompt as prompt_mod, report as report_mod
from .parser import (
    Entry,
    parse_log,
    parse_session,
    remove_day,
    render_entry,
    set_verso,
)

HOSTS_LOOPBACK = {"127.0.0.1", "localhost", "::1"}

# Sufixos de host aceitos sem configuração. `.ts.net` é o espaço de nomes da
# Tailscale: esses nomes são geridos por ela e resolvem apenas dentro do seu
# tailnet, então um atacante não consegue apontar um `.ts.net` para a sua
# máquina — que é exatamente o ataque (DNS rebinding) que a checagem de Host
# existe para barrar. Aceitá-los em bloco poupa o usuário de digitar um nome
# longo numa unidade do systemd, e digitar errado ali dá "host não permitido"
# sem explicação.
SUFIXOS_ACEITOS = (".ts.net",)

# Arquivos servidos como estão, da pasta do pacote. O service worker PRECISA vir
# da raiz: servido de /static/, ele só controlaria /static/, e o painel ficaria
# fora do escopo dele.
ESTATICOS = {
    "/manifest.json": ("manifest.json", "application/manifest+json"),
    "/sw.js": ("sw.js", "text/javascript"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
}
PASTA_ESTATICOS = pathlib.Path(__file__).parent / "static"
LIMITE_CORPO = 256 * 1024

# Freio de força bruta na senha: 10 erros em 5 minutos e a origem para.
MAX_TENTATIVAS = 10
JANELA_TENTATIVAS = 300

# Sessão por cookie, e não HTTP Basic, por um motivo concreto: **app instalado
# na tela inicial do iPhone não exibe o diálogo nativo de Basic auth**. Ele
# renderiza o corpo do 401, e o usuário vê a frase "Senha necessaria." e mais
# nada — sem campo, sem botão, sem saída. Um formulário é HTML comum: aparece em
# qualquer lugar que renderize página.
COOKIE_SESSAO = "en_sessao"
VALIDADE_SESSAO = 90 * 86400   # o plano dura 30 dias; relogar toda semana é atrito puro

# Rotas que MUDAM algo — no log, no Drive ou na autorização. São elas que o modo
# somente-leitura recusa, e são a razão de o painel não poder ser publicado na
# internet aberta: o token que as protege é servido dentro da própria página.
ROTAS_DE_ESCRITA = frozenset({
    "/api/pull", "/api/push", "/api/add", "/api/remove",
    "/api/falha", "/api/revisado", "/api/verso",
    "/api/pacote", "/api/autorizar",
})


class Estado:
    """O que o servidor precisa saber, e que não cabe no handler."""

    def __init__(
        self,
        token: str,
        offline: bool = False,
        somente_leitura: bool = False,
        hosts: set[str] | None = None,
        senha: str = "",
    ) -> None:
        self.token = token
        self.offline = offline
        self.somente_leitura = somente_leitura
        self.hosts = (hosts or set()) | HOSTS_LOOPBACK
        self.senha = senha
        self.lock = threading.Lock()
        # Tentativas de senha por origem. Um painel exposto é varrido por robô em
        # horas; sem freio, a senha vira questão de tempo.
        self.tentativas: dict[str, list[float]] = defaultdict(list)
        # Sessões válidas: token -> instante de criação. Em memória de propósito
        # — reiniciar o serviço desloga todo mundo, o que é o comportamento
        # seguro para um segredo que só existe enquanto o processo existe.
        self.sessoes: dict[str, float] = {}

    def abrir_sessao(self) -> str:
        token = secrets.token_urlsafe(32)
        self.sessoes[token] = time.time()
        return token

    def sessao_valida(self, token: str) -> bool:
        nascimento = self.sessoes.get(token)
        if nascimento is None:
            return False
        if time.time() - nascimento > VALIDADE_SESSAO:
            self.sessoes.pop(token, None)
            return False
        return True

    def bloqueado(self, origem: str) -> bool:
        agora = time.time()
        recentes = [t for t in self.tentativas[origem] if agora - t < JANELA_TENTATIVAS]
        self.tentativas[origem] = recentes
        return len(recentes) >= MAX_TENTATIVAS

    def errou(self, origem: str) -> None:
        self.tentativas[origem].append(time.time())

    def carregar(self, remoto: bool = False) -> tuple[analytics.Report, drive.LoadResult]:
        """Lê o log. Por padrão do CACHE, sem rede.

        O painel renderiza do cache de propósito: se cada carregamento de página
        fosse ao Drive, "Atualizar" e "Puxar do Drive" seriam a mesma coisa, e
        cada recarregamento pagaria uma ida à rede. Assim a página é instantânea
        e a sincronização é um ato explícito, com o carimbo de quando ocorreu
        visível no cabeçalho.
        """
        resultado = drive.load(prefer_remote=remoto and not self.offline)
        return analytics.build_report(parse_log(resultado.text)), resultado


class Handler(BaseHTTPRequestHandler):
    server_version = "english-tracker"
    estado: Estado

    # --- infraestrutura -------------------------------------------------

    def log_message(self, *args) -> None:  # silencia o log de acesso
        pass

    def handle_one_request(self) -> None:
        """Cliente que desiste no meio não é defeito, e não deve virar rastro.

        Acontece toda vez que a página é abandonada ou o pedido é abortado por
        falta de rede — comum no celular. Sem isto, o journal do serviço enche de
        BrokenPipeError com pilha inteira, o que parece falha grave e não é.
        """
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]").lower()
        if host in self.estado.hosts:
            return True
        return any(host.endswith(s) for s in SUFIXOS_ACEITOS)

    # --- senha e sessão -------------------------------------------------

    def _https(self) -> bool:
        """A requisição chegou por HTTPS? Decide o flag `Secure` do cookie.

        Marcar `Secure` sempre quebraria o acesso pela LAN (`http://192.168...`),
        onde o cookie simplesmente não seria guardado; nunca marcar entregaria a
        sessão a quem estivesse no caminho. Atrás do `tailscale serve`, o proxy
        informa o esquema original neste cabeçalho.
        """
        return (self.headers.get("X-Forwarded-Proto") or "").lower() == "https"

    def _cookie_sessao(self) -> str:
        cru = self.headers.get("Cookie")
        if not cru:
            return ""
        try:
            return SimpleCookie(cru).get(COOKIE_SESSAO).value  # type: ignore[union-attr]
        except Exception:
            return ""

    def _autenticado(self) -> bool:
        """Sessão por cookie, ou HTTP Basic — o segundo por causa do `curl`.

        Basic continua aceito porque é o que permite verificar o serviço da linha
        de comando (`curl -u :senha ...`) e o que um cliente sem cookie usaria.
        O que mudou é que ele deixou de ser o *único* caminho, e o navegador
        nunca mais é obrigado a exibir o diálogo nativo — que é justamente o que
        não existe em app instalado no iOS.
        """
        if not self.estado.senha:
            return True
        if self.estado.sessao_valida(self._cookie_sessao()):
            return True

        cabecalho = self.headers.get("Authorization") or ""
        if cabecalho.startswith("Basic "):
            origem = self.client_address[0]
            if self.estado.bloqueado(origem):
                return False
            try:
                cru = base64.b64decode(cabecalho[6:]).decode("utf-8")
                _, _, fornecida = cru.partition(":")
            except Exception:
                fornecida = ""
            if secrets.compare_digest(fornecida, self.estado.senha):
                return True
            self.estado.errou(origem)
        return False

    def _exige_senha(self) -> bool:
        """Passou pela tranca? Se não, responde e devolve False.

        A resposta muda com quem perguntou, e isso é o ponto: navegação vai para
        o formulário (uma página que qualquer contexto sabe mostrar), API recebe
        401 em JSON (o JavaScript trata; um redirecionamento só o confundiria).
        """
        if self._autenticado():
            return True

        caminho = urlparse(self.path).path
        if self.estado.bloqueado(self.client_address[0]):
            if caminho.startswith("/api/"):
                self._json({"ok": False, "erro": "tentativas demais — espere alguns minutos"}, 429)
            else:
                self._html(report_mod.render_login(
                    erro="Tentativas demais. Espere alguns minutos e tente de novo.",
                    destino="/",
                ), 429)
            return False

        if caminho.startswith("/api/"):
            self._json({"ok": False, "erro": "sessão expirada — recarregue a página"}, 401)
        else:
            # `safe=""` de propósito: com a barra fora do escape, um caminho com
            # `&` ou `#` dentro emendaria na query e o destino sairia truncado.
            self._redireciona(
                "/login?destino="
                + quote(self._destino_seguro(self.path), safe="")
            )
        return False

    def _destino_seguro(self, alvo: str) -> str:
        """Só caminho interno. Sem isto, `/login?destino=https://...` viraria
        um redirecionamento aberto — a página de login de um domínio confiável
        empurrando a vítima para outro site depois de entrar."""
        caminho = (alvo or "/").strip()
        if not caminho.startswith("/") or caminho.startswith("//"):
            return "/"
        return caminho

    def _redireciona(self, para: str, cookie: str = "") -> None:
        self.send_response(303)
        self.send_header("Location", para)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _login_get(self) -> None:
        destino = self._destino_seguro(
            (parse_qs(urlparse(self.path).query).get("destino") or ["/"])[0]
        )
        if self._autenticado():
            self._redireciona(destino)
            return
        self._html(report_mod.render_login(destino=destino))

    def _login_post(self) -> None:
        origem = self.client_address[0]
        tamanho = min(int(self.headers.get("Content-Length") or 0), LIMITE_CORPO)
        campos = parse_qs(self.rfile.read(tamanho).decode("utf-8", "replace")) if tamanho else {}
        destino = self._destino_seguro((campos.get("destino") or ["/"])[0])

        if self.estado.bloqueado(origem):
            self._html(report_mod.render_login(
                erro="Tentativas demais. Espere alguns minutos e tente de novo.",
                destino=destino,
            ), 429)
            return

        fornecida = (campos.get("senha") or [""])[0]
        if not secrets.compare_digest(fornecida, self.estado.senha):
            self.estado.errou(origem)
            self._html(report_mod.render_login(erro="Senha incorreta.", destino=destino), 401)
            return

        # `Secure` só sob HTTPS (ver _https). `SameSite=Lax` impede que um site
        # externo use a sessão em requisição de escrita.
        partes = [
            f"{COOKIE_SESSAO}={self.estado.abrir_sessao()}",
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
            f"Max-Age={VALIDADE_SESSAO}",
        ]
        if self._https():
            partes.append("Secure")
        self._redireciona(destino, cookie="; ".join(partes))

    def _sair(self) -> None:
        self.estado.sessoes.pop(self._cookie_sessao(), None)
        self._redireciona("/login", cookie=f"{COOKIE_SESSAO}=; Path=/; Max-Age=0")

    def _token_ok(self) -> bool:
        enviado = self.headers.get("X-Token") or ""
        return secrets.compare_digest(enviado, self.estado.token)

    def _json(self, dados: dict, status: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _html(self, texto: str, status: int = 200) -> None:
        corpo = texto.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _corpo_json(self) -> dict:
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho <= 0:
            return {}
        if tamanho > LIMITE_CORPO:
            raise ValueError("corpo grande demais")
        return json.loads(self.rfile.read(tamanho).decode("utf-8"))

    # --- rotas ----------------------------------------------------------

    def do_GET(self) -> None:
        if not self._host_ok():
            self._json({"ok": False, "erro": "host não permitido"}, 403)
            return

        caminho = urlparse(self.path).path
        # O formulário e a saída ficam FORA da tranca — senão a página que pede a
        # senha exigiria a senha para ser vista.
        if caminho == "/login":
            self._login_get()
            return
        if caminho == "/sair":
            self._sair()
            return
        if not self._exige_senha():
            return

        if caminho in ESTATICOS:
            self._estatico(*ESTATICOS[caminho])
        elif caminho in ("/", "/index.html"):
            self._painel()
        elif caminho in ("/cards", "/cards.html"):
            self._cards()
        elif caminho in ("/semana", "/semana.html"):
            self._semana()
        elif caminho == "/api/prompt":
            self._api(self._prompt)
        elif caminho == "/api/ping":
            # Sem token de propósito: é o pedido que a página usa para saber se
            # há servidor do outro lado, e ele não revela nada além disso.
            self._json({"ok": True})
        elif caminho == "/api/saude":
            self._api(self._saude)
        else:
            self._json({"ok": False, "erro": "rota inexistente"}, 404)

    def do_POST(self) -> None:
        if not self._host_ok():
            self._json({"ok": False, "erro": "host não permitido"}, 403)
            return

        if urlparse(self.path).path == "/login":
            if self.estado.senha:
                self._login_post()
            else:
                self._redireciona("/")
            return
        if not self._exige_senha():
            return

        rotas = {
            "/api/pull": self._pull,
            "/api/push": self._push,
            "/api/add": self._add,
            "/api/remove": self._remove,
            "/api/falha": self._falha,
            "/api/revisado": self._revisado,
            "/api/verso": self._verso,
            "/api/pacote": self._pacote,
            "/api/autorizar": self._autorizar,
        }
        acao = rotas.get(urlparse(self.path).path)
        if acao is None:
            self._json({"ok": False, "erro": "rota inexistente"}, 404)
            return
        self._api(acao)

    def _api(self, acao) -> None:
        """Toda rota de API passa por aqui: token, serialização e erro virado JSON."""
        if not self._token_ok():
            self._json({"ok": False, "erro": "token inválido"}, 403)
            return
        if self.estado.somente_leitura and urlparse(self.path).path in ROTAS_DE_ESCRITA:
            self._json({
                "ok": False,
                "erro": "painel em modo somente leitura — as ações só valem no "
                        "computador onde o log e a autorização moram",
            }, 403)
            return
        try:
            with self.estado.lock:
                self._json(acao())
        except Exception as exc:  # o servidor não cai por causa de uma ação
            self._json({"ok": False, "erro": f"{type(exc).__name__}: {exc}"}, 500)

    def _estatico(self, nome: str, tipo: str) -> None:
        arquivo = PASTA_ESTATICOS / nome
        if not arquivo.exists():
            self._json({"ok": False, "erro": f"{nome} não encontrado"}, 404)
            return
        corpo = arquivo.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        # O service worker não pode ficar preso em cache do navegador, senão uma
        # correção nele nunca chega. Os ícones podem.
        if nome.endswith(".js") or nome.endswith(".json"):
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(corpo)

    def _painel(self) -> None:
        rep, resultado = self.estado.carregar()
        html = report_mod.render(
            rep,
            source=resultado.source,
            drive_file=config.DRIVE_FILE_NAME,
            whatsapp=config.whatsapp_number(),
            interactive=not self.estado.somente_leitura,
            token=self.estado.token,
            warnings=resultado.warnings,
            last_sync=config.read_sync(),
            pacote=config.read_pacote(),
        )
        self._html(html)

    def _semana(self) -> None:
        rep, _ = self.estado.carregar()
        self._html(report_mod.render_semana(
            rep,
            token=self.estado.token,
            whatsapp=config.whatsapp_number(),
            drive_file=config.DRIVE_FILE_NAME,
        ))

    def _cards(self) -> None:
        rep, _ = self.estado.carregar()
        self._html(report_mod.render_cards(rep, token=self.estado.token))

    # --- ações (as mesmas da CLI) ---------------------------------------

    def _prompt(self) -> dict:
        pedido = parse_qs(urlparse(self.path).query)
        rep, _ = self.estado.carregar()
        dia = int(pedido.get("dia", [0])[0]) or rep.next_day
        if dia is None:
            return {"ok": False, "erro": "plano concluído"}
        return {"ok": True, "dia": dia, "prompt": prompt_mod.build(dia, rep, config.DRIVE_FILE_NAME)}

    def _pull(self) -> dict:
        if self.estado.offline:
            return {"ok": False, "erro": "servidor iniciado com --offline"}
        resultado = drive.load(prefer_remote=True, strict=True)  # a única rota que vai à rede por leitura
        rep = analytics.build_report(parse_log(resultado.text))
        return {
            "ok": True,
            "mensagem": f'Baixado de "{resultado.name or config.DRIVE_FILE_NAME}" '
                        f"({rep.total_sessions} sessões no log).",
            "avisos": resultado.warnings,
        }

    def _push(self) -> dict:
        if self.estado.offline:
            return {"ok": False, "erro": "servidor iniciado com --offline"}
        texto = drive.read_cached()
        if not texto.strip():
            return {"ok": False, "erro": "cache local vazio — nada para enviar"}
        drive.push(texto)
        return {"ok": True, "mensagem": "Cache local fundido no arquivo do Drive."}

    def _remove(self) -> dict:
        """Apaga um dia do log. Remoção NÃO se propaga por fusão: exige substituir.

        O `push` normal só acrescenta — é o que protege a sessão que o professor
        escreveu entre o último `pull` e o `add`. Para uma remoção chegar ao
        Drive, o arquivo remoto tem de ser substituído pelo local, e é por isso
        que esta rota é a única que usa `force`. O backup do remoto é feito pelo
        próprio `push` antes de escrever.
        """
        dados = self._corpo_json()
        try:
            dia = int(dados.get("dia") or 0)
        except (TypeError, ValueError):
            return {"ok": False, "erro": "dia inválido"}
        if dia <= 0:
            return {"ok": False, "erro": "dia inválido"}

        # Apagar é a única operação que SUBSTITUI o arquivo do Drive (fusão não
        # remove nada). Fazer isso a partir de um cache velho apagaria junto o
        # que tivesse chegado no meio — então a remoção parte do conteúdo fresco.
        atual = drive.read_cached()
        if not self.estado.offline:
            try:
                atual = drive.fetch().text
                drive.write_cache(atual, backup_tag="pre-remove-sync")
            except drive.DriveUnavailable as exc:
                return {"ok": False, "erro": f"não deu para conferir o Drive antes de apagar: {exc}"}

        novo, removidas = remove_day(atual, dia)
        if not removidas:
            return {"ok": False, "erro": f"o dia {dia} não está no log"}

        drive.write_cache(novo, backup_tag=f"pre-remove-dia{dia}")

        no_drive = "O Drive não foi tocado (modo offline)."
        if not self.estado.offline:
            try:
                drive.push(novo, force=True)
                no_drive = "O arquivo do Drive foi substituído pelo log sem esse dia."
            except (drive.DriveUnavailable, drive.DriveRefused) as exc:
                no_drive = (f"Drive não atualizado ({exc}). O log local já está sem o dia; "
                            "rode um push quando resolver.")

        return {
            "ok": True,
            "mensagem": f"Dia {dia} apagado do log local. {no_drive} "
                        f"Há cópia do estado anterior em backups/.",
        }

    def _saude(self) -> dict:
        """O que precisa da atenção do usuário. Vai à rede só para o refresh do token."""
        if self.estado.offline:
            return {"ok": True, "offline": True}
        leitura_ok, leitura = drive.check_auth(write=False)
        escrita_ok, escrita = drive.check_auth(write=True)
        return {
            "ok": True,
            "offline": False,
            "leitura": {"ok": leitura_ok, "motivo": leitura},
            "escrita": {"ok": escrita_ok, "motivo": escrita},
        }

    def _autorizar(self) -> dict:
        """Refaz o consentimento. Abre uma aba do navegador e espera."""
        if self.estado.offline:
            return {"ok": False, "erro": "servidor iniciado com --offline"}
        escrita = bool(self._corpo_json().get("escrita"))
        try:
            drive.renew_auth(write=escrita)
        except Exception as exc:
            return {"ok": False, "erro": f"{type(exc).__name__}: {exc}"}
        alvo = "escrita" if escrita else "leitura"
        return {"ok": True, "mensagem": f"Autorização de {alvo} renovada."}

    def _pacote(self) -> dict:
        """Publica a semana no Drive: é o que tira o notebook do caminho diário."""
        if self.estado.offline:
            return {"ok": False, "erro": "servidor iniciado com --offline"}
        try:
            dias = int(self._corpo_json().get("dias") or 7)
        except (TypeError, ValueError):
            dias = 7
        rep, _ = self.estado.carregar()
        blocos = prompt_mod.pacote_dias(rep, dias, config.DRIVE_FILE_NAME)
        if not blocos:
            return {"ok": False, "erro": "plano concluído — não há dias a publicar"}
        texto = prompt_mod.pacote(rep, dias=dias, drive_file=config.DRIVE_FILE_NAME)
        drive.publish_prompt(texto)
        config.write_pacote(blocos[0]["dia"], blocos[-1]["dia"])
        return {
            "ok": True,
            "mensagem": f'Dias {blocos[0]["dia"]} a {blocos[-1]["dia"]} publicados '
                        f'como "{drive.PROMPT_FILE_NAME}.md" no Drive. '
                        f"Abra pelo app do Drive no celular.",
        }

    def _falha(self) -> dict:
        """"Errei este": traz o item de volta amanhã. Rebaixa, nunca promove."""
        chave = (self._corpo_json().get("chave") or "").strip()
        if not chave:
            return {"ok": False, "erro": "item não informado"}
        config.registrar_revisao_local("falhas", chave)
        return {"ok": True, "mensagem": "Anotado como erro: volta amanhã."}

    def _revisado(self) -> dict:
        """"Já revisei hoje": tira do baralho do dia SEM mexer na caixa.

        Prática não é evidência: quem promove o item é o professor, registrando
        `Acertos:` na sessão. Isto só evita que o cartão insista no mesmo dia.
        """
        chave = (self._corpo_json().get("chave") or "").strip()
        if not chave:
            return {"ok": False, "erro": "item não informado"}
        config.registrar_revisao_local("revisados", chave)
        return {
            "ok": True,
            "mensagem": "Fora do baralho de hoje. A caixa não mudou — só o "
                        "`Acertos:` do professor promove.",
        }

    def _verso(self) -> dict:
        """O verso escrito pelo aluno, gravado no LOG (e não num arquivo à parte)."""
        dados = self._corpo_json()
        rotulo = (dados.get("rotulo") or "").strip()
        verso = (dados.get("verso") or "").strip()
        if not rotulo or not verso:
            return {"ok": False, "erro": "item ou verso vazio"}

        atual = drive.read_cached()
        novo, escreveu = set_verso(atual, rotulo, verso)
        if not escreveu:
            return {"ok": False, "erro": "não achei o item no log, ou ele já tem verso"}

        drive.write_cache(novo, backup_tag="pre-verso")
        no_drive = "O Drive não foi tocado (modo offline)."
        if not self.estado.offline:
            try:
                drive.push(novo)
                no_drive = "Enviado ao Drive."
            except (drive.DriveUnavailable, drive.DriveRefused) as exc:
                no_drive = f"Drive não atualizado ({exc}); está salvo aqui."
        return {"ok": True, "mensagem": f"Verso salvo no log. {no_drive}"}

    def _add(self) -> dict:
        dados = self._corpo_json()
        colado = (dados.get("texto") or "").strip()
        if not colado:
            return {"ok": False, "erro": "nada colado — nada foi registrado"}

        rep, _ = self.estado.carregar()
        dia = int(dados.get("dia") or 0) or rep.next_day
        pd = plan.get(dia)
        if pd is None:
            return {"ok": False, "erro": f"dia {dia} não existe no plano"}

        entrada = parse_session(colado, dia)
        if entrada is not None:
            entrada.kind = entrada.kind or pd.kind
            entrada.topic = entrada.topic or pd.topic
            aviso = ""
        else:
            entrada = Entry(day=dia, kind=pd.kind, topic=pd.topic, extra=colado)
            aviso = ("Não entendi o formato: guardei o texto em 'Resumo colado'. "
                     "Erros e palavras não foram extraídos.")

        bloco = render_entry(entrada)
        atual = drive.read_cached()
        juntado = (atual.rstrip() + "\n\n" + bloco + "\n") if atual.strip() else bloco + "\n"
        drive.write_cache(juntado, backup_tag="pre-add")

        enviado = ""
        if not self.estado.offline:
            try:
                drive.push(juntado)
                enviado = "Enviado ao Drive."
            except (drive.DriveUnavailable, drive.DriveRefused) as exc:
                enviado = f"Drive não atualizado ({exc}). O registro local está salvo."

        return {
            "ok": True,
            "mensagem": " ".join(x for x in [f"Dia {dia} registrado.", aviso, enviado] if x),
            "bloco": bloco,
        }


def _enderecos_locais() -> list[str]:
    """IPs pelos quais esta máquina é alcançável na rede.

    Descobertos abrindo um socket UDP para fora (sem enviar nada) e perguntando
    que endereço o sistema escolheu — funciona sem depender de `ip`, `ifconfig`
    nem de resolver o hostname, que em muitas máquinas devolve 127.0.1.1.
    """
    import socket

    achados: list[str] = []
    for destino in ("8.8.8.8", "192.168.1.1"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((destino, 1))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127.") and ip not in achados:
                achados.append(ip)
        except OSError:
            pass
        finally:
            s.close()
    return achados


def servir(
    porta: int = 8765,
    abrir: bool = True,
    offline: bool = False,
    host: str = "127.0.0.1",
    hosts_extra: list[str] | None = None,
    somente_leitura: bool = False,
    senha: str = "",
) -> None:
    """Sobe o painel e bloqueia até Ctrl-C.

    O padrão é `127.0.0.1`: só esta máquina alcança. Mudar o `host` abre o painel
    para a rede — e aí vale lembrar o que o token NÃO faz: ele é servido dentro
    da página, então quem consegue carregá-la consegue agir. Abrir para uma rede
    privada (Tailscale, VPN, LAN de casa) é uma coisa; para a internet aberta é
    dar escrita no seu Drive a quem achar a URL.

    `somente_leitura` é a trava para o caso remoto: o painel mostra tudo e recusa
    qualquer ação que mude algo.
    """
    # Ouvir em 0.0.0.0 e aceitar só o Host "0.0.0.0" seria inútil: navegador
    # nenhum manda isso — ele manda o endereço que você digitou. Então, ao sair
    # de loopback, os próprios endereços e o nome desta máquina entram na lista.
    # A checagem continua barrando Host estranho, que é o que ela existe para
    # barrar (um site externo resolvendo um domínio dele para este IP privado).
    aceitos = {h.lower() for h in (hosts_extra or [])} | {host}
    if host not in HOSTS_LOOPBACK:
        import socket

        aceitos |= set(_enderecos_locais())
        nome = socket.gethostname()
        if nome:
            aceitos |= {nome, nome.split(".")[0], f"{nome.split('.')[0]}.local"}

    Handler.estado = Estado(
        token=secrets.token_urlsafe(24),
        offline=offline,
        somente_leitura=somente_leitura,
        hosts=aceitos,
        senha=senha,
    )
    httpd = ThreadingHTTPServer((host, porta), Handler)
    escutando = httpd.server_address[1]
    url = f"http://{host}:{escutando}/"

    if host == "0.0.0.0":
        # "0.0.0.0" é instrução de bind, não endereço para abrir no navegador —
        # imprimir isso como URL manda o usuário para um lugar que não existe.
        print(f"Painel ouvindo em todas as interfaces, porta {escutando}.", flush=True)
        print("Abra por um destes endereços:", flush=True)
        print(f"  http://127.0.0.1:{escutando}/   (nesta máquina)", flush=True)
        for ip in _enderecos_locais():
            print(f"  http://{ip}:{escutando}/   (de outro computador da rede)", flush=True)
    else:
        print(f"Painel em {url}", flush=True)
    if somente_leitura:
        print("Modo SOMENTE LEITURA: nenhuma ação muda log, Drive ou autorização.", flush=True)
    else:
        print("As ações do terminal estão nos botões da página. Ctrl-C encerra.", flush=True)
    if offline:
        print("Modo offline: pull, push e envio ao Drive estão desligados.", flush=True)

    if host not in HOSTS_LOOPBACK:
        print(flush=True)
        print("⚠  O painel está ouvindo FORA desta máquina.", flush=True)
        print("   O token de acesso é servido dentro da própria página, então", flush=True)
        print("   quem conseguir abri-la age como você" + (
            " — mas o modo somente leitura está ligado." if somente_leitura
            else ", inclusive escrevendo no seu Drive."), flush=True)
        if senha:
            print("   Senha ligada (formulário em /login) — mas ela só protege", flush=True)
            print("   de verdade sobre HTTPS: em HTTP puro ela trafega legível.", flush=True)
        else:
            print("   SEM SENHA: qualquer um que alcance esta porta entra.", flush=True)
        print("   Use isto só em rede privada, ou atrás de um túnel com TLS.", flush=True)
        print(f"   Hosts aceitos no cabeçalho: {', '.join(sorted(Handler.estado.hosts))}", flush=True)
        print(f"   e qualquer um terminado em: {', '.join(SUFIXOS_ACEITOS)}", flush=True)
        print(flush=True)

    if abrir and host in HOSTS_LOOPBACK:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")
    finally:
        httpd.server_close()
