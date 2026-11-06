"""Detecção de duplicados exatos com SHA-256.

Etapas, da mais barata para a mais cara:
1. agrupar por tamanho (tamanho único = arquivo único, nada é lido);
2. SHA-256 dos primeiros 64 KB, para descartar rápido arquivos grandes diferentes;
3. SHA-256 do arquivo inteiro, lido em blocos de 1 MB;
4. opcional: comparação byte a byte dentro de cada grupo (modo rigoroso).

Os arquivos são abertos apenas em modo "rb". Nada é movido, renomeado ou apagado.
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .paths import long_path
from .scanner import Cancelled, FileEntry, Skipped

PARTIAL_BYTES = 64 * 1024
CHUNK_BYTES = 1024 * 1024

EXACT_DUPLICATE = "Duplicado exato"
UNIQUE = "Arquivo único"

ProgressCallback = Callable[[str, int, int], None]


@dataclass
class DuplicateGroup:
    sha256: str
    size: int
    files: list[FileEntry]
    byte_verified: bool = False
    classification: str = EXACT_DUPLICATE

    @property
    def copies(self) -> int:
        return len(self.files)

    @property
    def recoverable_bytes(self) -> int:
        """Espaço potencialmente recuperável: mantém um arquivo de referência e conta o restante."""
        return self.size * (self.copies - 1)


@dataclass
class DuplicateReport:
    groups: list[DuplicateGroup] = field(default_factory=list)
    not_analyzed: list[Skipped] = field(default_factory=list)
    empty_files: list[FileEntry] = field(default_factory=list)
    files_considered: int = 0
    files_hashed: int = 0
    bytes_hashed: int = 0
    strict: bool = False

    @property
    def duplicate_files(self) -> int:
        return sum(g.copies for g in self.groups)

    @property
    def recoverable_bytes(self) -> int:
        return sum(g.recoverable_bytes for g in self.groups)

    @property
    def unique_files(self) -> int:
        """Arquivos lidos sem nenhuma cópia idêntica (vazios e não analisados ficam de fora)."""
        return self.files_considered - self.duplicate_files - len(self.not_analyzed) - len(self.empty_files)


class _Hasher:
    def __init__(self, cancel: threading.Event | None):
        self.cancel = cancel
        self.bytes_read = 0

    def _check(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled()

    def sha256(self, path: str, limit: int | None = None) -> str:
        digest = hashlib.sha256()
        remaining = limit
        with open(long_path(path), "rb") as fh:
            while True:
                self._check()
                size = CHUNK_BYTES if remaining is None else min(CHUNK_BYTES, remaining)
                if size <= 0:
                    break
                block = fh.read(size)
                if not block:
                    break
                digest.update(block)
                self.bytes_read += len(block)
                if remaining is not None:
                    remaining -= len(block)
        return digest.hexdigest()

    def same_bytes(self, a: str, b: str) -> bool:
        with open(long_path(a), "rb") as fa, open(long_path(b), "rb") as fb:
            while True:
                self._check()
                ba, bb = fa.read(CHUNK_BYTES), fb.read(CHUNK_BYTES)
                if ba != bb:
                    return False
                if not ba:
                    return True


def _read_error(entry: FileEntry, exc: OSError) -> Skipped:
    if isinstance(exc, PermissionError):
        reason = "Arquivo bloqueado ou sem permissão"
    elif isinstance(exc, FileNotFoundError):
        reason = "Arquivo removido durante a análise"
    else:
        reason = f"Erro de leitura: {exc.strerror or exc}"
    return Skipped(entry.path, reason)


def _changed_since_scan(entry: FileEntry) -> bool:
    try:
        st = os.stat(long_path(entry.path))
    except OSError:
        return True
    return st.st_size != entry.size or st.st_mtime != entry.mtime


def find_duplicates(
    files: Iterable[FileEntry],
    strict: bool = False,
    cancel: threading.Event | None = None,
    progress: ProgressCallback | None = None,
) -> DuplicateReport:
    files = list(files)
    report = DuplicateReport(files_considered=len(files), strict=strict)
    hasher = _Hasher(cancel)

    by_size: dict[int, list[FileEntry]] = defaultdict(list)
    for entry in files:
        if entry.cloud_only:
            report.not_analyzed.append(Skipped(entry.path, "Disponível somente na nuvem (não baixado)"))
        elif entry.size == 0:
            report.empty_files.append(entry)
        else:
            by_size[entry.size].append(entry)

    candidates = [group for group in by_size.values() if len(group) > 1]
    total = sum(len(g) for g in candidates)
    done = 0

    def tick(stage: str) -> None:
        nonlocal done
        done += 1
        if progress is not None:
            progress(stage, done, total)

    for same_size in candidates:
        size = same_size[0].size
        by_partial: dict[str, list[FileEntry]] = defaultdict(list)
        for entry in same_size:
            try:
                by_partial[hasher.sha256(entry.path, PARTIAL_BYTES)].append(entry)
            except OSError as exc:
                report.not_analyzed.append(_read_error(entry, exc))
            tick("Comparando conteúdo")

        for partial_hash, same_start in by_partial.items():
            if len(same_start) < 2:
                continue
            by_full: dict[str, list[FileEntry]] = defaultdict(list)
            for entry in same_start:
                try:
                    full = partial_hash if size <= PARTIAL_BYTES else hasher.sha256(entry.path)
                except OSError as exc:
                    report.not_analyzed.append(_read_error(entry, exc))
                    continue
                if _changed_since_scan(entry):
                    report.not_analyzed.append(Skipped(entry.path, "Arquivo alterado durante a análise"))
                    continue
                by_full[full].append(entry)
                report.files_hashed += 1

            for full_hash, identical in by_full.items():
                if len(identical) < 2:
                    continue
                if strict:
                    report.groups.extend(_split_by_bytes(full_hash, size, identical, hasher, report))
                else:
                    report.groups.append(DuplicateGroup(full_hash, size, _sorted(identical)))

    report.bytes_hashed = hasher.bytes_read
    report.groups.sort(key=lambda g: (g.recoverable_bytes, g.copies), reverse=True)
    return report


def _split_by_bytes(
    sha: str, size: int, entries: list[FileEntry], hasher: _Hasher, report: DuplicateReport
) -> list[DuplicateGroup]:
    """Confirma byte a byte; arquivos que divergirem (colisão de hash) formam grupos separados."""
    pending = list(entries)
    groups: list[DuplicateGroup] = []
    while len(pending) > 1:
        reference, rest = pending[0], pending[1:]
        same, different = [reference], []
        for entry in rest:
            try:
                (same if hasher.same_bytes(reference.path, entry.path) else different).append(entry)
            except OSError as exc:
                report.not_analyzed.append(_read_error(entry, exc))
        if len(same) > 1:
            groups.append(DuplicateGroup(sha, size, _sorted(same), byte_verified=True))
        pending = different
    return groups


def _sorted(entries: list[FileEntry]) -> list[FileEntry]:
    return sorted(entries, key=lambda e: (e.mtime, e.path))
