"""Executa a análise fora da thread da interface, para a janela não travar."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal

from acme.core.duplicates import DuplicateReport, find_duplicates
from acme.core.scanner import Cancelled, ScanResult, scan


@dataclass
class AnalysisResult:
    scan: ScanResult
    duplicates: DuplicateReport
    seconds: float


class AnalysisWorker(QObject):
    progress = Signal(str, int, int)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, folder: str, strict: bool):
        super().__init__()
        self.folder = folder
        self.strict = strict
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        start = time.monotonic()
        try:
            scanned = scan(self.folder, self.cancel_event, self.progress.emit)
            report = find_duplicates(scanned.files, self.strict, self.cancel_event, self.progress.emit)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - a interface mostra a mensagem; nada foi alterado em disco
            self.failed.emit(str(exc))
        else:
            self.finished.emit(AnalysisResult(scanned, report, time.monotonic() - start))


class TaskWorker(QObject):
    """Roda uma função fn(cancel, progress) fora da thread da interface."""

    progress = Signal(str, int, int)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            result = self.fn(self.cancel_event, self.progress.emit)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - a interface mostra a mensagem
            self.failed.emit(str(exc))
        else:
            self.finished.emit(result)


def start_in_thread(parent, worker: QObject, on_finished, on_failed, on_cancelled, on_progress=None) -> QThread:
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    if on_progress is not None:
        worker.progress.connect(on_progress)
    worker.finished.connect(on_finished)
    worker.failed.connect(on_failed)
    worker.cancelled.connect(on_cancelled)
    for signal in (worker.finished, worker.failed, worker.cancelled):
        signal.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.start()
    return thread
