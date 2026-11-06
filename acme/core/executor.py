"""Executa um plano confirmado e desfaz operações. Única parte do app que move arquivos.

Regras de segurança:
- nada é excluído e nada é sobrescrito: se o destino já existe, o arquivo ganha um nome livre "(2)";
- origem e destino precisam estar dentro da pasta organizada;
- um arquivo alterado depois da prévia não é movido;
- o plano é gravado no histórico antes do primeiro movimento e cada passo é marcado ao terminar;
- o Desfazer só devolve um arquivo se ele não mudou desde a organização e o local original está livre.
"""

from __future__ import annotations

import errno
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from . import history as h
from .paths import IS_WINDOWS, long_path
from .planner import Plan, _free_name

ProgressCallback = Callable[[str, int, int], None]


@dataclass
class ExecutionResult:
    operation_id: int
    moved: int = 0
    failed: int = 0
    renamed: int = 0
    cancelled: bool = False


@dataclass
class UndoResult:
    restored: int = 0
    blocked: list[tuple[str, str]] = field(default_factory=list)


class UndoNotAllowed(Exception):
    pass


def _inside(root: str, path: str) -> bool:
    root_n = os.path.normcase(os.path.abspath(root))
    path_n = os.path.normcase(os.path.abspath(path))
    try:
        return os.path.commonpath([root_n, path_n]) == root_n and path_n != root_n
    except ValueError:  # unidades diferentes no Windows
        return False


def _move_no_overwrite(source: str, destination: str) -> None:
    """Move sem jamais substituir um arquivo existente."""
    src, dst = long_path(source), long_path(destination)
    if IS_WINDOWS:
        os.rename(src, dst)  # no Windows, rename falha com FileExistsError se o destino existir
        return
    try:
        os.link(src, dst)  # atômico: falha se o destino existir
    except FileExistsError:
        raise
    except OSError:
        if os.path.lexists(dst):
            raise FileExistsError(errno.EEXIST, "Destino já existe", destination) from None
        os.rename(src, dst)
        return
    os.unlink(src)


def _make_folders(folder: str, op_id: int, hist: h.History) -> None:
    missing = []
    current = folder
    while not os.path.isdir(long_path(current)):
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    for path in reversed(missing):
        os.mkdir(long_path(path))
        hist.record_folder(op_id, path)


def _error_text(exc: OSError) -> str:
    if isinstance(exc, PermissionError):
        return "Arquivo em uso ou sem permissão (feche o arquivo e tente de novo)"
    if isinstance(exc, FileNotFoundError):
        return "Arquivo não encontrado"
    if getattr(exc, "errno", None) == errno.EXDEV:
        return "Destino em outra unidade; o app não copia arquivos entre unidades"
    return f"Erro: {exc.strerror or exc}"


def _same_file_state(path: str, size: int, mtime_ns: int) -> bool:
    try:
        st = os.stat(long_path(path))
    except OSError:
        return False
    return st.st_size == size and st.st_mtime_ns == mtime_ns


def execute_plan(
    plan: Plan,
    hist: h.History,
    cancel: threading.Event | None = None,
    progress: ProgressCallback | None = None,
) -> ExecutionResult:
    op_id = hist.start_operation(plan.root, plan.mode, plan.moves)
    result = ExecutionResult(op_id)
    records = hist.moves(op_id)
    total = len(records)
    for done, record in enumerate(records, start=1):
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            hist.finish_operation(op_id, h.INTERRUPTED)
            return result
        error = None
        destination = record.destination
        if not (_inside(plan.root, record.source) and _inside(plan.root, destination)):
            error = "Fora da pasta autorizada"
        elif not os.path.lexists(long_path(record.source)):
            error = "Arquivo não encontrado (foi movido ou excluído depois da prévia)"
        elif not _same_file_state(record.source, record.size, record.mtime_ns):
            error = "Arquivo alterado depois da prévia; não foi movido"
        if error is None:
            try:
                folder = os.path.dirname(destination)
                _make_folders(folder, op_id, hist)
                if os.path.lexists(long_path(destination)):
                    destination, _ = _free_name(folder, os.path.basename(destination), set())
                    result.renamed += 1
                _move_no_overwrite(record.source, destination)
            except FileExistsError:
                error = "Um arquivo com o mesmo nome apareceu no destino; nada foi substituído"
            except OSError as exc:
                error = _error_text(exc)
        if error is None:
            hist.mark(record.id, h.MOVED, destination=destination)
            result.moved += 1
        else:
            hist.mark(record.id, h.FAILED, error)
            result.failed += 1
        if progress is not None:
            progress("Organizando", done, total)
    hist.finish_operation(op_id, h.DONE_WITH_ERRORS if result.failed else h.DONE)
    return result


def undo_operation(hist: h.History, op_id: int, progress: ProgressCallback | None = None) -> UndoResult:
    operation = next((o for o in hist.operations(10_000) if o.id == op_id), None)
    if operation is None:
        raise UndoNotAllowed("Operação não encontrada.")
    if operation.status in (h.UNDONE, h.RUNNING):
        raise UndoNotAllowed(f"Esta operação não pode ser desfeita (situação: {operation.status}).")
    result = UndoResult()
    records = [r for r in reversed(hist.moves(op_id)) if r.status in (h.MOVED, h.PENDING, h.RESTORE_BLOCKED)]
    total = len(records)
    for done, record in enumerate(records, start=1):
        if progress is not None:
            progress("Desfazendo", done, total)
        at_destination = os.path.lexists(long_path(record.destination))
        at_source = os.path.lexists(long_path(record.source))
        if record.status == h.PENDING and not (at_destination and not at_source):
            continue  # nunca chegou a ser movido
        reason = None
        if not at_destination:
            reason = "O arquivo não está mais no local organizado"
        elif not _same_file_state(record.destination, record.size, record.mtime_ns):
            reason = "O arquivo foi modificado depois da organização; não foi restaurado para não perder alterações"
        elif at_source:
            reason = "Já existe um arquivo no local original; nada foi substituído"
        elif not (_inside(operation.root, record.source) and _inside(operation.root, record.destination)):
            reason = "Fora da pasta autorizada"
        if reason is None:
            try:
                os.makedirs(long_path(os.path.dirname(record.source)), exist_ok=True)
                _move_no_overwrite(record.destination, record.source)
            except FileExistsError:
                reason = "Já existe um arquivo no local original; nada foi substituído"
            except OSError as exc:
                reason = _error_text(exc)
        if reason is None:
            hist.mark(record.id, h.RESTORED)
            result.restored += 1
        else:
            hist.mark(record.id, h.RESTORE_BLOCKED, reason)
            result.blocked.append((record.destination, reason))
    for folder in reversed(hist.created_folders(op_id)):
        try:
            os.rmdir(long_path(folder))  # só remove pastas que ficaram vazias
        except OSError:
            pass
    hist.finish_operation(op_id, h.PARTIALLY_UNDONE if result.blocked else h.UNDONE)
    return result
