"""Varredura somente leitura de uma pasta e suas subpastas."""

from __future__ import annotations

import os
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from .categories import category_for
from .paths import is_cloud_only, long_path, validate_root

ProgressCallback = Callable[[str, int, int], None]


class Cancelled(Exception):
    """A análise foi cancelada pelo usuário."""


@dataclass(frozen=True)
class FileEntry:
    path: str
    name: str
    size: int
    mtime: float
    cloud_only: bool = False
    mtime_ns: int = 0

    @property
    def folder(self) -> str:
        return os.path.dirname(self.path)


@dataclass(frozen=True)
class Skipped:
    path: str
    reason: str


@dataclass
class ScanResult:
    root: str
    files: list[FileEntry] = field(default_factory=list)
    folder_count: int = 0
    skipped: list[Skipped] = field(default_factory=list)

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)

    def by_category(self) -> Counter:
        return Counter(category_for(f.name) for f in self.files)


def _is_link(entry: os.DirEntry) -> bool:
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, "is_junction", None)
    return bool(is_junction and is_junction())


def scan(
    folder: str | os.PathLike,
    cancel: threading.Event | None = None,
    progress: ProgressCallback | None = None,
) -> ScanResult:
    """Lista arquivos e subpastas sem abrir nem alterar nenhum arquivo.

    Links simbólicos e junções não são seguidos, para a análise não sair da pasta escolhida.
    Arquivos somente na nuvem são listados com cloud_only=True e não serão lidos depois.
    """
    root = validate_root(folder)
    result = ScanResult(root=str(root))
    stack = [str(root)]
    while stack:
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        current = stack.pop()
        try:
            # O prefixo \\?\ só é usado para abrir a pasta; os caminhos guardados ficam sem ele.
            with os.scandir(long_path(current)) as it:
                entries = list(it)
        except OSError as exc:
            result.skipped.append(Skipped(current, _reason(exc)))
            continue
        for entry in entries:
            path = os.path.join(current, entry.name)
            try:
                if _is_link(entry):
                    result.skipped.append(Skipped(path, "Link ou atalho de pasta (não seguido)"))
                    continue
                if entry.is_dir(follow_symlinks=False):
                    result.folder_count += 1
                    stack.append(path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                st = entry.stat(follow_symlinks=False)
            except OSError as exc:
                result.skipped.append(Skipped(path, _reason(exc)))
                continue
            result.files.append(
                FileEntry(
                    path=path,
                    name=entry.name,
                    size=st.st_size,
                    mtime=st.st_mtime,
                    cloud_only=is_cloud_only(st),
                    mtime_ns=st.st_mtime_ns,
                )
            )
            if progress is not None and len(result.files) % 500 == 0:
                progress("Listando arquivos", len(result.files), 0)
    if progress is not None:
        progress("Listando arquivos", len(result.files), len(result.files))
    return result


def _reason(exc: OSError) -> str:
    if isinstance(exc, PermissionError):
        return "Sem permissão de acesso"
    if isinstance(exc, FileNotFoundError):
        return "Arquivo removido durante a análise"
    return f"Erro de leitura: {exc.strerror or exc}"
