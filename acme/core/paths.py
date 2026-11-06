"""Validação de caminhos e atributos de arquivos do Windows.

Tudo aqui é somente leitura: nenhuma função altera arquivos ou pastas.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"

# Atributos de arquivo do Windows (winnt.h). Arquivos do OneDrive que estão
# somente na nuvem carregam um destes; lê-los forçaria o download.
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
CLOUD_ONLY_MASK = (
    FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
)

_MAX_PATH = 260


class PathNotAllowed(ValueError):
    """A pasta escolhida não pode ser analisada (sistema, raiz de unidade, inexistente)."""


def _protected_roots() -> list[Path]:
    names = ["SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData"]
    roots = [Path(os.environ[n]) for n in names if os.environ.get(n)]
    local_appdata = os.environ.get("LOCALAPPDATA")
    appdata = os.environ.get("APPDATA")
    roots += [Path(p) for p in (local_appdata, appdata) if p]
    if not IS_WINDOWS:
        roots += [Path(p) for p in ("/bin", "/boot", "/dev", "/etc", "/lib", "/proc", "/sbin", "/sys", "/usr")]
    return roots


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_root(folder: str | os.PathLike) -> Path:
    """Confirma que a pasta pode ser analisada e devolve o caminho absoluto resolvido."""
    path = Path(folder).expanduser()
    if not path.exists():
        raise PathNotAllowed(f"A pasta não existe: {path}")
    if not path.is_dir():
        raise PathNotAllowed(f"O caminho não é uma pasta: {path}")
    path = path.resolve()
    if path.parent == path:
        raise PathNotAllowed("Não é permitido analisar a raiz de uma unidade inteira. Escolha uma pasta.")
    for protected in _protected_roots():
        try:
            protected = protected.resolve()
        except OSError:
            continue
        if _is_within(path, protected):
            raise PathNotAllowed(f"Pasta protegida do sistema: {protected}")
    return path


def is_cloud_only(st: os.stat_result) -> bool:
    """True quando o arquivo está somente na nuvem (OneDrive) e lê-lo dispararia um download."""
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & CLOUD_ONLY_MASK)


def long_path(path: str) -> str:
    """Prefixo de caminho estendido do Windows para caminhos acima de 260 caracteres."""
    if IS_WINDOWS and len(path) >= _MAX_PATH - 12 and not path.startswith("\\\\?\\"):
        if path.startswith("\\\\"):
            return "\\\\?\\UNC\\" + path[2:]
        return "\\\\?\\" + path
    return path


def shared_location_warning(folder: str) -> str | None:
    """Aviso quando mover arquivos pode afetar outras pessoas (pasta de rede ou biblioteca do SharePoint)."""
    if folder.startswith("\\\\"):
        return "esta é uma pasta de rede. Outras pessoas podem estar usando estes arquivos."
    commercial = os.environ.get("OneDriveCommercial")
    profile = os.environ.get("USERPROFILE")
    if commercial and profile:
        tenant = os.path.basename(commercial).replace("OneDrive - ", "", 1)
        shared_root = os.path.join(profile, tenant)
        if tenant and os.path.normcase(folder).startswith(os.path.normcase(shared_root + os.sep)):
            return ("esta pasta é uma biblioteca compartilhada do SharePoint/Teams. A mudança aparece para todos "
                    "que têm acesso, e links para estes arquivos podem parar de funcionar.")
    if commercial and os.path.normcase(folder).startswith(os.path.normcase(commercial)):
        return ("arquivos do seu OneDrive que você compartilhou com outras pessoas mudam de lugar para elas também, "
                "e links já enviados podem parar de funcionar.")
    return None
