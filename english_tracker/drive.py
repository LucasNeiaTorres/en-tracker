"""Acesso ao Google Drive.

O Drive é a fonte da verdade: o professor escreve lá, e este módulo lê.
Se as credenciais não estiverem configuradas, tudo continua funcionando
contra o cache local, e a interface avisa que está trabalhando offline.

Como quem escreve o arquivo é outra IA, escrever aqui é a operação perigosa do
programa, e ela obedece a quatro regras:

1. **Alvo fixo.** Resolvido o arquivo uma vez, o id é gravado e reusado. Busca
   por `name contains` acha parecido, e `files().update` substitui o conteúdo
   inteiro do que achar: com nome aproximado dá para zerar arquivo alheio.
2. **Nunca sobrescrever o que não se reconhece.** Antes de escrever, o conteúdo
   atual do alvo é baixado e tem de parsear como english-log.
3. **Funde, não substitui.** O remoto é a base; o local só acrescenta o que falta
   nele. Assim um `add` offline não apaga a sessão que o professor escreveu no
   meio.
4. **Backup antes de cada escrita**, dos dois lados. É o único dano irreversível
   do sistema.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config
from .parser import parse_log, render_entry


class DriveUnavailable(RuntimeError):
    """Drive não configurado ou bibliotecas ausentes."""


class DriveRefused(RuntimeError):
    """Escrita recusada por segurança — o alvo não é claramente o log."""


@dataclass
class RemoteFile:
    file_id: str
    name: str
    modified: datetime | None
    text: str
    fuzzy: bool = False


@dataclass
class LoadResult:
    """Conteúdo do log mais o que o usuário precisa saber sobre a origem dele."""

    text: str
    source: str
    warnings: list[str] = field(default_factory=list)
    name: str = ""
    modified: datetime | None = None

    def __iter__(self):
        """Compatibilidade com `text, source = load()`."""
        return iter((self.text, self.source))


def _service(write: bool = False):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover
        raise DriveUnavailable(
            "Bibliotecas do Google ausentes. Rode: pip install -r requirements.txt"
        ) from exc

    scopes = config.DRIVE_SCOPES_WRITE if write else config.DRIVE_SCOPES_READONLY
    token_path = config.TOKEN_WRITE_PATH if write else config.TOKEN_PATH

    config.ensure_app_dir()
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not config.CREDENTIALS_PATH.exists():
                raise DriveUnavailable(
                    f"Falta o arquivo de credenciais em {config.CREDENTIALS_PATH}. "
                    "Veja o README, seção 'Conectar o Drive'."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.CREDENTIALS_PATH), scopes
            )
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def check_auth(write: bool = False) -> tuple[bool, str]:
    """Diz se a autorização está de pé — SEM abrir navegador.

    Existe porque o app fica com status "Em teste" no Google, e nesse status o
    refresh token **expira em 7 dias**. Descobrir isso quando o pacote da semana
    silenciosamente parou de atualizar é tarde: o painel tem de avisar antes.

    Devolve (está_ok, motivo em português).
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        return False, "as bibliotecas do Google não estão instaladas"

    if not config.CREDENTIALS_PATH.exists():
        return False, f"falta o credentials.json em {config.CREDENTIALS_PATH}"

    escopos = config.DRIVE_SCOPES_WRITE if write else config.DRIVE_SCOPES_READONLY
    token_path = config.TOKEN_WRITE_PATH if write else config.TOKEN_PATH
    if not token_path.exists():
        return False, "ainda não autorizado" + (" para escrita" if write else "")

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), escopos)
    except Exception:
        return False, "o arquivo de token está ilegível"

    if creds.valid:
        return True, "ok"
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            return False, ("a autorização expirou — o app está com status "
                           "\"Em teste\" no Google, e nesse status ela vale 7 dias")
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return True, "renovada automaticamente"
    return False, "a autorização não é mais válida"


def renew_auth(write: bool = False) -> None:
    """Refaz o consentimento no navegador. Bloqueia até você autorizar."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise DriveUnavailable("bibliotecas do Google ausentes") from exc

    if not config.CREDENTIALS_PATH.exists():
        raise DriveUnavailable(f"falta o credentials.json em {config.CREDENTIALS_PATH}")

    escopos = config.DRIVE_SCOPES_WRITE if write else config.DRIVE_SCOPES_READONLY
    token_path = config.TOKEN_WRITE_PATH if write else config.TOKEN_PATH
    flow = InstalledAppFlow.from_client_secrets_file(str(config.CREDENTIALS_PATH), escopos)
    creds = flow.run_local_server(port=0)
    config.ensure_app_dir()
    token_path.write_text(creds.to_json(), encoding="utf-8")


_FIELDS = "id, name, mimeType, modifiedTime, trashed"


def _by_id(service, file_id: str) -> dict | None:
    try:
        meta = service.files().get(fileId=file_id, fields=_FIELDS).execute()
    except Exception:
        return None
    return None if meta.get("trashed") else meta


def _query(service, query: str, page_size: int = 20) -> list[dict]:
    result = (
        service.files()
        .list(
            q=query,
            spaces="drive",
            fields=f"files({_FIELDS})",
            orderBy="modifiedTime desc",
            pageSize=page_size,
        )
        .execute()
    )
    return result.get("files", [])


def _find(service, name: str) -> dict | None:
    """Resolve o arquivo: id fixado > nome exato > nome aproximado (marcado)."""
    pinned = config.read_file_id()
    if pinned:
        meta = _by_id(service, pinned)
        if meta is not None:
            return meta
        config.clear_file_id()

    safe = name.replace("\\", "\\\\").replace("'", "\\'")
    exact = _query(
        service, f"(name = '{safe}' or name = '{safe}.md') and trashed = false"
    )
    if exact:
        return exact[0]

    fuzzy = _query(service, f"name contains '{safe}' and trashed = false")
    if not fuzzy:
        return None
    meta = dict(fuzzy[0])
    meta["_fuzzy"] = True
    meta["_candidates"] = [f.get("name", "?") for f in fuzzy]
    return meta


def _download(service, meta: dict) -> str:
    if meta.get("mimeType") == "application/vnd.google-apps.document":
        data = service.files().export(fileId=meta["id"], mimeType="text/plain").execute()
    else:
        from googleapiclient.http import MediaIoBaseDownload

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(
            buffer, service.files().get_media(fileId=meta["id"])
        )
        done = False
        while not done:
            _, done = downloader.next_chunk()
        data = buffer.getvalue()
    return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)


def fetch(name: str | None = None) -> RemoteFile:
    """Baixa o log do Drive. Levanta DriveUnavailable se não der."""
    name = name or config.DRIVE_FILE_NAME
    service = _service(write=False)
    meta = _find(service, name)
    if meta is None:
        raise DriveUnavailable(
            f'Nenhum arquivo parecido com "{name}" no seu Drive. '
            "O professor pode não ter conseguido escrever - registre a sessão com "
            "`english-tracker add`."
        )

    text = _download(service, meta)
    modified = None
    if meta.get("modifiedTime"):
        modified = datetime.fromisoformat(meta["modifiedTime"].replace("Z", "+00:00"))

    # Alvo confirmado por leitura: fixa o id para a escrita não ter de adivinhar.
    if not meta.get("_fuzzy") or parse_log(text):
        config.write_file_id(meta["id"])

    return RemoteFile(
        file_id=meta["id"],
        name=meta.get("name", name),
        modified=modified,
        text=text,
        fuzzy=bool(meta.get("_fuzzy")),
    )


def merge_logs(remote_text: str, local_text: str) -> str:
    """Funde os dois lados sem reescrever o que já está lá.

    O remoto é a base — é o que o professor escreveu, com as palavras dele. Do
    local só se acrescenta o dia que falta no remoto, ou o dia cujo conteúdo
    local difere (foi editado no `add` depois). Nada é removido, nunca.
    """
    if not remote_text.strip():
        return local_text
    if not local_text.strip():
        return remote_text

    remote_entries = {e.day: e for e in parse_log(remote_text)}
    additions: list[str] = []
    for entry in parse_log(local_text):
        remote = remote_entries.get(entry.day)
        if remote is not None and _content_key(remote) == _content_key(entry):
            continue
        additions.append((entry.raw or render_entry(entry)).strip())

    if not additions:
        return remote_text
    return remote_text.rstrip() + "\n\n" + "\n\n".join(additions) + "\n"


def _content_key(entry) -> tuple:
    return (tuple(entry.errors), tuple(entry.vocab), entry.note.strip())


def push(text: str, name: str | None = None, force: bool = False) -> str:
    """Funde o texto local no arquivo do Drive e sobe o resultado.

    `force=True` sobe o texto local como está, sem fundir — só para desfazer uma
    bagunça de propósito, com o usuário sabendo o que está descartando.
    """
    from googleapiclient.http import MediaIoBaseUpload

    name = name or config.DRIVE_FILE_NAME
    service = _service(write=True)
    meta = _find(service, name)

    if meta is None:
        media = MediaIoBaseUpload(
            io.BytesIO(text.encode("utf-8")), mimetype="text/plain", resumable=False
        )
        created = (
            service.files()
            .create(body={"name": f"{name}.md"}, media_body=media, fields="id")
            .execute()
        )
        config.write_file_id(created["id"])
        return created["id"]

    if meta.get("mimeType") == "application/vnd.google-apps.document":
        raise DriveUnavailable(
            f'"{meta["name"]}" é um Google Doc; este script não sobrescreve Docs. '
            "Deixe o log como arquivo de texto simples."
        )

    if meta.get("_fuzzy") and not force:
        candidatos = ", ".join(meta.get("_candidates", [])[:5])
        raise DriveRefused(
            f'O nome "{name}" não casou exatamente com nenhum arquivo; o mais '
            f'parecido é "{meta["name"]}" (candidatos: {candidatos}). Não vou '
            "sobrescrever um arquivo achado por aproximação. Rode "
            "`english-tracker pull` para confirmar o alvo, renomeie o arquivo no "
            "Drive, ou repita com --force."
        )

    current = _download(service, meta)
    if current.strip() and not parse_log(current) and not force:
        raise DriveRefused(
            f'"{meta["name"]}" tem conteúdo que não parece um english-log '
            "(nenhuma entrada DIA reconhecida). Não vou substituí-lo. Confirme o "
            "arquivo no Drive ou repita com --force."
        )

    backup(current, "drive")
    merged = text if force else merge_logs(current, text)

    media = MediaIoBaseUpload(
        io.BytesIO(merged.encode("utf-8")), mimetype="text/plain", resumable=False
    )
    service.files().update(fileId=meta["id"], media_body=media).execute()
    config.write_file_id(meta["id"])
    write_cache(merged, backup_tag="pos-push")
    return meta["id"]


PROMPT_FILE_NAME = "english-prompt"
MARCA_PACOTE = "PROMPTS DOS DIAS"


def publish_prompt(texto: str, name: str | None = None) -> str:
    """Sobe o pacote de prompts para um arquivo PRÓPRIO no Drive.

    É um arquivo gerado, separado do log: o log é a fonte da verdade e nunca
    recebe conteúdo do programa sem fusão; este aqui é descartável e sobrescrito
    a cada geração. Mesmo assim não se sobrescreve às cegas — se o alvo existir e
    não começar com a marca do pacote, a escrita é recusada, porque um arquivo
    com nome parecido pode ser outra coisa.
    """
    from googleapiclient.http import MediaIoBaseUpload

    name = name or PROMPT_FILE_NAME
    service = _service(write=True)
    safe = name.replace("\\", "\\\\").replace("'", "\\'")
    achados = _query(
        service, f"(name = '{safe}' or name = '{safe}.md') and trashed = false"
    )

    media = MediaIoBaseUpload(
        io.BytesIO(texto.encode("utf-8")), mimetype="text/plain", resumable=False
    )
    if not achados:
        criado = (
            service.files()
            .create(body={"name": f"{name}.md"}, media_body=media, fields="id")
            .execute()
        )
        return criado["id"]

    alvo = achados[0]
    if alvo.get("mimeType") == "application/vnd.google-apps.document":
        raise DriveRefused(
            f'"{alvo["name"]}" é um Google Doc; este script não sobrescreve Docs.'
        )
    atual = _download(service, alvo)
    if atual.strip() and MARCA_PACOTE not in atual[:400]:
        raise DriveRefused(
            f'"{alvo["name"]}" não parece o pacote de prompts (não tem a marca '
            f'"{MARCA_PACOTE}"). Não vou sobrescrevê-lo — renomeie o arquivo no '
            "Drive ou escolha outro nome."
        )
    service.files().update(fileId=alvo["id"], media_body=media).execute()
    return alvo["id"]


def backup(text: str, tag: str) -> Path | None:
    """Guarda uma cópia datada antes de qualquer sobrescrita."""
    if not text.strip():
        return None
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = config.BACKUP_DIR / f"{stamp}-{tag}.md"
    path.write_text(text, encoding="utf-8")
    _prune_backups()
    return path


def _prune_backups() -> None:
    arquivos = sorted(config.BACKUP_DIR.glob("*.md"))
    excedente = max(len(arquivos) - config.BACKUP_KEEP, 0)
    for velho in arquivos[:excedente]:
        velho.unlink(missing_ok=True)


def read_cached() -> str:
    if config.CACHE_PATH.exists():
        return config.CACHE_PATH.read_text(encoding="utf-8")
    return ""


def write_cache(text: str, backup_tag: str = "cache") -> None:
    config.ensure_app_dir()
    anterior = read_cached()
    if anterior.strip() and anterior != text:
        backup(anterior, backup_tag)
    config.CACHE_PATH.write_text(text, encoding="utf-8")


def load(prefer_remote: bool = True, strict: bool = False) -> LoadResult:
    """Devolve o log e a origem, sem nunca perder dado local em silêncio.

    Se o remoto tiver menos dias que o cache — o professor pode ter reescrito o
    arquivo em vez de acrescentar —, o cache NÃO é substituído pelo remoto: os
    dois são fundidos e o usuário é avisado.
    """
    if not prefer_remote:
        return LoadResult(read_cached(), "cache")

    try:
        remote = fetch()
    except DriveUnavailable:
        if strict:
            raise
        return LoadResult(read_cached(), "cache")

    avisos: list[str] = []
    local = read_cached()
    remote_days = {e.day for e in parse_log(remote.text)}
    local_days = {e.day for e in parse_log(local)}
    perdidos = sorted(local_days - remote_days)

    if remote.fuzzy:
        avisos.append(
            f'O arquivo foi achado por nome aproximado ("{remote.name}"). '
            "Confirme se é o log certo."
        )

    if perdidos:
        avisos.append(
            f"O Drive não tem mais {'o dia' if len(perdidos) == 1 else 'os dias'} "
            f"{', '.join(map(str, perdidos))}, que estão no cache local. O professor "
            "pode ter reescrito o arquivo em vez de acrescentar. Nada foi apagado "
            "aqui: os dois lados foram fundidos. Rode `english-tracker push` para "
            "devolver ao Drive."
        )
        texto = merge_logs(remote.text, local)
        write_cache(texto, backup_tag="pre-merge")
        config.mark_sync()
        return LoadResult(texto, "drive+cache", avisos, remote.name, remote.modified)

    write_cache(remote.text, backup_tag="pre-pull")
    config.mark_sync()
    return LoadResult(remote.text, "drive", avisos, remote.name, remote.modified)
