"""Planejamento da organização: calcula para onde cada arquivo iria, sem mover nada.

O plano é a prévia que o usuário revisa. Só o executor (executor.py) move arquivos, e apenas
depois da confirmação.
"""

from __future__ import annotations

import json
import os
import threading
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .categories import category_for
from .config import data_dir
from .scanner import Cancelled, FileEntry, ScanResult, Skipped, scan

MODE_EXTENSION = "extensao"
MODE_PERIOD = "periodo"
MODE_RULES = "regras"
MODE_NAMES = {
    MODE_EXTENSION: "Por tipo de arquivo",
    MODE_PERIOD: "Por período (ano e mês)",
    MODE_RULES: "Por regras personalizadas",
}

DATE_MODIFIED = "modificacao"
DATE_CREATED = "criacao"

MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
          "Outubro", "Novembro", "Dezembro"]

# Caracteres proibidos em nomes de pasta no Windows.
_FORBIDDEN = set('<>:"|?*')


@dataclass(frozen=True)
class Rule:
    keyword: str
    destination: str

    def matches(self, filename: str) -> bool:
        return bool(self.keyword.strip()) and normalize(self.keyword) in normalize(filename)


DEFAULT_RULES = [
    Rule("Admissão", "RH/Admissões"),
    Rule("Faturamento", "Financeiro/Faturamento"),
    Rule("Power BI", "BI/Projetos"),
]


@dataclass(frozen=True)
class Move:
    source: str
    destination: str
    category: str
    size: int
    mtime_ns: int
    renamed: bool = False  # o nome ganhou "(2)" porque já existia um arquivo com o mesmo nome no destino


@dataclass
class Plan:
    root: str
    mode: str
    moves: list[Move] = field(default_factory=list)
    unchanged: int = 0  # já estavam no lugar certo ou nenhuma regra se aplicou
    skipped: list[Skipped] = field(default_factory=list)
    files_considered: int = 0

    @property
    def conflicts(self) -> int:
        return sum(1 for m in self.moves if m.renamed)


def normalize(text: str) -> str:
    """Minúsculas e sem acentos, para "admissao" casar com "Admissão"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def validate_destination(destination: str) -> str:
    """Pasta de destino de uma regra: sempre relativa e dentro da pasta organizada."""
    parts = [p.strip() for p in destination.replace("\\", "/").split("/") if p.strip()]
    if not parts:
        raise ValueError("Informe a pasta de destino.")
    for part in parts:
        if part in (".", "..") or any(c in _FORBIDDEN for c in part) or part.endswith("."):
            raise ValueError(f"Nome de pasta inválido: {part}")
    if ":" in destination or destination.startswith(("/", "\\")):
        raise ValueError("Use um caminho relativo, por exemplo RH/Admissões.")
    return os.path.join(*parts)


def load_rules() -> list[Rule]:
    path = data_dir() / "regras.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Rule(r["palavra"], r["destino"]) for r in data]
    except (OSError, ValueError, KeyError, TypeError):
        return list(DEFAULT_RULES)


def save_rules(rules: list[Rule]) -> None:
    path = data_dir() / "regras.json"
    data = [{"palavra": r.keyword, "destino": r.destination} for r in rules]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _file_date(entry: FileEntry, date_kind: str) -> datetime:
    if date_kind == DATE_CREATED:
        try:
            st = os.stat(entry.path)
            created = getattr(st, "st_birthtime", None) or st.st_ctime
            return datetime.fromtimestamp(created)
        except OSError:
            pass
    return datetime.fromtimestamp(entry.mtime)


def target_folder(entry: FileEntry, mode: str, date_kind: str = DATE_MODIFIED,
                  rules: list[Rule] | None = None) -> str | None:
    """Subpasta (relativa à pasta organizada) para o arquivo, ou None se ele deve ficar onde está."""
    if mode == MODE_EXTENSION:
        return category_for(entry.name)
    if mode == MODE_PERIOD:
        when = _file_date(entry, date_kind)
        return os.path.join(str(when.year), f"{when.month:02d} - {MONTHS[when.month - 1]}")
    if mode == MODE_RULES:
        for rule in rules or []:
            if rule.matches(entry.name):
                return validate_destination(rule.destination)
        return None
    raise ValueError(f"Modo de organização desconhecido: {mode}")


def _free_name(folder: str, name: str, taken: set[str]) -> tuple[str, bool]:
    """Nome livre no destino: nunca aponta para um arquivo existente nem para outro destino do plano."""
    candidate = os.path.join(folder, name)
    if not os.path.lexists(candidate) and os.path.normcase(candidate) not in taken:
        return candidate, False
    stem, ext = os.path.splitext(name)
    n = 2
    while True:
        candidate = os.path.join(folder, f"{stem} ({n}){ext}")
        if not os.path.lexists(candidate) and os.path.normcase(candidate) not in taken:
            return candidate, True
        n += 1


def build_plan(
    folder: str,
    mode: str,
    include_subfolders: bool = False,
    date_kind: str = DATE_MODIFIED,
    rules: list[Rule] | None = None,
    cancel: threading.Event | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> Plan:
    scanned: ScanResult = scan(folder, cancel, progress)
    root = scanned.root
    plan = Plan(root=root, mode=mode, skipped=list(scanned.skipped))
    taken: set[str] = set()
    files = scanned.files
    if not include_subfolders:
        files = [f for f in files if os.path.normcase(f.folder) == os.path.normcase(root)]
    plan.files_considered = len(files)
    for entry in sorted(files, key=lambda f: f.path.casefold()):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        relative = target_folder(entry, mode, date_kind, rules)
        if relative is None:
            plan.unchanged += 1
            continue
        destination_folder = os.path.join(root, relative)
        if os.path.normcase(destination_folder) == os.path.normcase(entry.folder):
            plan.unchanged += 1
            continue
        if Path(destination_folder).is_file():
            plan.skipped.append(Skipped(entry.path, f"Existe um arquivo com o nome da pasta de destino: {relative}"))
            continue
        destination, renamed = _free_name(destination_folder, entry.name, taken)
        taken.add(os.path.normcase(destination))
        plan.moves.append(Move(
            source=entry.path,
            destination=destination,
            category=relative,
            size=entry.size,
            mtime_ns=entry.mtime_ns,
            renamed=renamed,
        ))
    return plan
