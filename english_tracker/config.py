"""Configuração do English Tracker.

Tudo que muda de máquina para máquina fica aqui ou em variáveis de ambiente.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

APP_DIR = Path(os.environ.get("ENGLISH_TRACKER_HOME", Path.home() / ".english-tracker"))
TOKEN_PATH = APP_DIR / "token.json"
TOKEN_WRITE_PATH = APP_DIR / "token-write.json"
CREDENTIALS_PATH = Path(
    os.environ.get("ENGLISH_TRACKER_CREDENTIALS", APP_DIR / "credentials.json")
)
CACHE_PATH = APP_DIR / "english-log.md"

# Id do arquivo do Drive, gravado na primeira resolução bem-sucedida. Buscar por
# nome a cada vez é o que permitia escrever no arquivo errado.
FILE_ID_PATH = APP_DIR / "file-id"

# O que o ALUNO relata sobre a revisão de hoje, que não está no log porque o log
# é o que o PROFESSOR escreveu. Duas coisas, e nenhuma delas promove item:
#   falhas    -> "errei este" : traz o item de volta amanhã
#   revisados -> "já revisei" : tira do baralho de hoje, sem mexer na caixa
# Autorrelato de falha é confiável (ninguém alega errar sem ter errado); de
# acerto, na própria pronúncia, é justamente o que este sistema não aceita.
REVISAO_LOCAL_PATH = APP_DIR / "revisao-local.json"

# Quando houve a última leitura efetiva do Drive. O painel mostra isso: sem esse
# carimbo, "lido do cache" não diz se o cache é de agora ou da semana passada.
LAST_SYNC_PATH = APP_DIR / "last-sync"

# Cópia do que havia antes de cada escrita — no cache e no Drive. O arquivo é o
# projeto inteiro; perdê-lo por sobrescrita é o único dano irreversível daqui.
BACKUP_DIR = APP_DIR / "backups"
BACKUP_KEEP = 40

# Número de WhatsApp para o botão do painel: só dígitos, com código do país
# (ex.: 5551999998888). Vazio faz o botão abrir o seletor de conversa do próprio
# WhatsApp, o que também serve — é lá que fica "Conversar comigo mesmo".
WHATSAPP_ENV = os.environ.get("ENGLISH_TRACKER_WHATSAPP", "")

# Nome do arquivo no Google Drive que o professor escreve ao fim de cada sessão.
DRIVE_FILE_NAME = os.environ.get("ENGLISH_TRACKER_DRIVE_FILE", "english-log")

# Conta de serviço: a alternativa ao OAuth de usuário. Ela não pede navegador e
# NÃO expira em 7 dias — é o que permite automação desatendida e hospedagem. E o
# acesso dela é mais estreito que o do OAuth atual: ela só enxerga os arquivos
# que você compartilhar com o e-mail dela, não o Drive inteiro.
# A chave vem do arquivo, ou da variável (que é como um serviço hospedado a
# recebe: o JSON inteiro numa variável de ambiente).
SA_ENV = os.environ.get("ENGLISH_TRACKER_SA_JSON", "")


def service_account_info() -> dict | None:
    """A chave da conta de serviço, se houver. Variável primeiro, depois arquivo."""
    bruto = SA_ENV.strip()
    if not bruto:
        arquivo = caminho("service-account.json")
        if not arquivo.exists():
            return None
        bruto = arquivo.read_text(encoding="utf-8")
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError:
        return None
    return dados if dados.get("type") == "service_account" else None


# Escopo separado por fluxo: ler não precisa de permissão de escrita, e a
# permissão de escrita no Drive inteiro é justamente o que torna caro um push
# apontado para o arquivo errado. Cada escopo tem seu próprio token.
DRIVE_SCOPES_READONLY = ["https://www.googleapis.com/auth/drive.readonly"]
DRIVE_SCOPES_WRITE = ["https://www.googleapis.com/auth/drive"]
# Mantido pelo nome antigo para não quebrar quem importava daqui.
DRIVE_SCOPES = DRIVE_SCOPES_WRITE


@dataclass(frozen=True)
class Settings:
    """Parâmetros do plano de estudo."""

    start_date: date
    total_days: int = 30
    session_minutes: int = 15
    # Dias da semana em que você aceita não estudar (0 = segunda ... 6 = domingo).
    rest_weekdays: tuple[int, ...] = ()

    @classmethod
    def load(cls) -> "Settings":
        raw = os.environ.get("ENGLISH_TRACKER_START")
        if raw:
            start = date.fromisoformat(raw)
        else:
            start = _read_start_file() or date.today()
        return cls(start_date=start)


def _read_start_file() -> date | None:
    marker = caminho("start-date")
    if marker.exists():
        try:
            return date.fromisoformat(marker.read_text(encoding="utf-8").strip())
        except ValueError:
            return None
    return None


def set_start_date(value: date) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    (APP_DIR / "start-date").write_text(value.isoformat(), encoding="utf-8")


def whatsapp_number() -> str:
    """Número do botão do painel: variável de ambiente, senão arquivo, senão vazio."""
    bruto = WHATSAPP_ENV
    if not bruto:
        arquivo = caminho("whatsapp")
        if arquivo.exists():
            bruto = arquivo.read_text(encoding="utf-8")
    return "".join(c for c in bruto if c.isdigit())


def set_whatsapp_number(value: str) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    (APP_DIR / "whatsapp").write_text(value.strip(), encoding="utf-8")


def read_revisao_local() -> dict[str, list[dict[str, str]]]:
    arquivo = caminho("revisao-local.json")
    if arquivo.exists():
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"falhas": [], "revisados": []}
        return {
            "falhas": dados.get("falhas", []),
            "revisados": dados.get("revisados", []),
        }
    return {"falhas": [], "revisados": []}


def registrar_revisao_local(tipo: str, chave: str, quando: date | None = None) -> None:
    """Guarda um relato do aluno: `tipo` é "falhas" ou "revisados"."""
    if tipo not in ("falhas", "revisados"):
        raise ValueError(f"tipo inválido: {tipo}")
    dados = read_revisao_local()
    dia = (quando or date.today()).isoformat()
    lista = dados[tipo]
    if not any(r.get("chave") == chave and r.get("data") == dia for r in lista):
        lista.append({"chave": chave, "data": dia})
    # Relato velho não serve para nada e o arquivo não deve crescer sem fim.
    corte = (date.today() - timedelta(days=120)).isoformat()
    for nome in ("falhas", "revisados"):
        dados[nome] = [r for r in dados[nome] if r.get("data", "") >= corte]
    ensure_app_dir()
    caminho("revisao-local.json").write_text(
        json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def senha_do_painel() -> str:
    """Senha do painel, quando ele é exposto na rede.

    Vem de variável de ambiente ou de arquivo — **nunca de argumento de linha de
    comando**: argv aparece no `ps` de qualquer processo da máquina e fica no
    histórico do shell.
    """
    bruta = os.environ.get("ENGLISH_TRACKER_SENHA", "")
    if not bruta:
        arquivo = caminho("senha")
        if arquivo.exists():
            bruta = arquivo.read_text(encoding="utf-8")
    return bruta.strip()


def read_pacote() -> dict:
    """Quando o pacote de prompts foi publicado, e que dias ele cobre."""
    arquivo = caminho("pacote.json")
    if arquivo.exists():
        try:
            return json.loads(arquivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def write_pacote(primeiro: int, ultimo: int) -> None:
    ensure_app_dir()
    caminho("pacote.json").write_text(
        json.dumps(
            {"em": date.today().isoformat(), "primeiro": primeiro, "ultimo": ultimo},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def mark_sync() -> None:
    ensure_app_dir()
    caminho("last-sync").write_text(
        datetime.now().isoformat(timespec="seconds"), encoding="utf-8"
    )


def read_sync() -> datetime | None:
    arquivo = caminho("last-sync")
    if arquivo.exists():
        try:
            return datetime.fromisoformat(arquivo.read_text(encoding="utf-8").strip())
        except ValueError:
            return None
    return None


def ensure_app_dir() -> Path:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    return APP_DIR


def caminho(nome: str) -> Path:
    """Resolve um arquivo do APP_DIR **na hora da chamada**.

    As constantes no topo do módulo são calculadas no import, então quem
    redireciona `APP_DIR` depois (um teste, por exemplo) não as afeta — e o
    resultado é teste escrevendo na pasta real do usuário. Todo estado novo passa
    por aqui.
    """
    return APP_DIR / nome


def read_file_id() -> str | None:
    arquivo = caminho("file-id")
    if arquivo.exists():
        value = arquivo.read_text(encoding="utf-8").strip()
        return value or None
    return None


def write_file_id(file_id: str) -> None:
    ensure_app_dir()
    caminho("file-id").write_text(file_id, encoding="utf-8")


def clear_file_id() -> None:
    caminho("file-id").unlink(missing_ok=True)
