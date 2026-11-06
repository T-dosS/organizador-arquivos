"""Histórico de operações em SQLite.

O plano inteiro é gravado antes do primeiro movimento, e cada passo é marcado ao terminar.
Assim, se o programa for fechado ou o computador desligar no meio, o histórico mostra
exatamente o que já foi movido e o Desfazer consegue reverter.
"""

from __future__ import annotations

import getpass
import platform
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import data_dir

# Estados de uma operação
RUNNING = "Em andamento"
DONE = "Concluída"
DONE_WITH_ERRORS = "Concluída com erros"
INTERRUPTED = "Interrompida"
UNDONE = "Desfeita"
PARTIALLY_UNDONE = "Desfeita em parte"

# Estados de um movimento
PENDING = "Pendente"
MOVED = "Movido"
FAILED = "Erro"
RESTORED = "Restaurado"
RESTORE_BLOCKED = "Não restaurado"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS operacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio TEXT NOT NULL,
    fim TEXT,
    usuario TEXT NOT NULL,
    maquina TEXT NOT NULL,
    raiz TEXT NOT NULL,
    modo TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS movimentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    ordem INTEGER NOT NULL,
    origem TEXT NOT NULL,
    destino TEXT NOT NULL,
    categoria TEXT NOT NULL,
    tamanho INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    status TEXT NOT NULL,
    erro TEXT,
    quando TEXT
);
CREATE TABLE IF NOT EXISTS pastas_criadas (
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    caminho TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mov_op ON movimentos(operacao_id, ordem);
"""


@dataclass
class Operation:
    id: int
    started: str
    finished: str | None
    user: str
    machine: str
    root: str
    mode: str
    status: str
    total: int
    moved: int
    errors: int


@dataclass
class MoveRecord:
    id: int
    order: int
    source: str
    destination: str
    category: str
    size: int
    mtime_ns: int
    status: str
    error: str | None
    when: str | None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "historico.db"
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def start_operation(self, root: str, mode: str, moves) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO operacoes (inicio, usuario, maquina, raiz, modo, status) VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), getpass.getuser(), platform.node(), root, mode, RUNNING),
            )
            op_id = cur.lastrowid
            self.conn.executemany(
                "INSERT INTO movimentos (operacao_id, ordem, origem, destino, categoria, tamanho, mtime_ns, status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(op_id, i, m.source, m.destination, m.category, m.size, m.mtime_ns, PENDING)
                 for i, m in enumerate(moves)],
            )
        return op_id

    def mark(self, move_id: int, status: str, error: str | None = None, destination: str | None = None) -> None:
        with self.conn:
            if destination is not None:
                self.conn.execute("UPDATE movimentos SET status=?, erro=?, quando=?, destino=? WHERE id=?",
                                  (status, error, _now(), destination, move_id))
            else:
                self.conn.execute("UPDATE movimentos SET status=?, erro=?, quando=? WHERE id=?",
                                  (status, error, _now(), move_id))

    def record_folder(self, op_id: int, folder: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO pastas_criadas (operacao_id, caminho) VALUES (?, ?)", (op_id, folder))

    def created_folders(self, op_id: int) -> list[str]:
        rows = self.conn.execute("SELECT caminho FROM pastas_criadas WHERE operacao_id=? ORDER BY rowid", (op_id,))
        return [r[0] for r in rows]

    def finish_operation(self, op_id: int, status: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE operacoes SET status=?, fim=? WHERE id=?", (status, _now(), op_id))

    def mark_interrupted(self) -> int:
        """Operações que ficaram 'Em andamento' (programa fechado no meio) passam a 'Interrompida'."""
        with self.conn:
            cur = self.conn.execute("UPDATE operacoes SET status=?, fim=? WHERE status=?",
                                    (INTERRUPTED, _now(), RUNNING))
        return cur.rowcount

    def operations(self, limit: int = 200) -> list[Operation]:
        rows = self.conn.execute(
            """SELECT o.id, o.inicio, o.fim, o.usuario, o.maquina, o.raiz, o.modo, o.status,
                      COUNT(m.id), SUM(m.status = ?), SUM(m.status = ?)
               FROM operacoes o LEFT JOIN movimentos m ON m.operacao_id = o.id
               GROUP BY o.id ORDER BY o.id DESC LIMIT ?""",
            (MOVED, FAILED, limit),
        )
        return [Operation(*r[:8], r[8], r[9] or 0, r[10] or 0) for r in rows]

    def moves(self, op_id: int) -> list[MoveRecord]:
        rows = self.conn.execute(
            "SELECT id, ordem, origem, destino, categoria, tamanho, mtime_ns, status, erro, quando"
            " FROM movimentos WHERE operacao_id=? ORDER BY ordem",
            (op_id,),
        )
        return [MoveRecord(*r) for r in rows]
