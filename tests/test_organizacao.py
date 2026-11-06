"""Testes da organização: prévia, execução segura, histórico e Desfazer."""

from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime

import pytest

from acme.core import executor as ex
from acme.core import history as h
from acme.core import planner as pl
from acme.core.paths import long_path


def write(path, data: bytes = b"x", when: datetime | None = None):
    os.makedirs(long_path(str(path.parent)), exist_ok=True)
    with open(long_path(str(path)), "wb") as fh:
        fh.write(data)
    if when is not None:
        ts = when.timestamp()
        os.utime(long_path(str(path)), (ts, ts))
    return path


def tree(folder):
    """Conteúdo de todos os arquivos, por caminho relativo."""
    out = {}
    for dirpath, _, names in os.walk(folder):
        for name in names:
            p = os.path.join(dirpath, name)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, folder)] = hashlib.sha256(fh.read()).hexdigest()
    return out


@pytest.fixture
def hist():
    history = h.History()
    yield history
    history.close()


def test_previa_nao_move_nada(tmp_path):
    write(tmp_path / "relatorio.pdf")
    write(tmp_path / "planilha.xlsx")
    before = tree(tmp_path)
    plan = pl.build_plan(str(tmp_path), pl.MODE_EXTENSION)
    assert len(plan.moves) == 2
    assert tree(tmp_path) == before


def test_por_extensao(tmp_path, hist):
    for name in ("a.pdf", "b.xlsx", "c.docx", "d.pptx", "e.jpg", "f.mp4", "g.zip", "h.xyz"):
        write(tmp_path / name, name.encode())
    plan = pl.build_plan(str(tmp_path), pl.MODE_EXTENSION)
    ex.execute_plan(plan, hist)
    assert set(tree(tmp_path)) == {
        os.path.join("PDFs", "a.pdf"), os.path.join("Excel", "b.xlsx"), os.path.join("Word", "c.docx"),
        os.path.join("PowerPoint", "d.pptx"), os.path.join("Imagens", "e.jpg"), os.path.join("Vídeos", "f.mp4"),
        os.path.join("Arquivos compactados", "g.zip"), os.path.join("Outros", "h.xyz"),
    }


def test_por_periodo(tmp_path, hist):
    write(tmp_path / "jan.pdf", b"1", datetime(2025, 1, 15, 10))
    write(tmp_path / "out.pdf", b"2", datetime(2026, 10, 3, 10))
    plan = pl.build_plan(str(tmp_path), pl.MODE_PERIOD)
    ex.execute_plan(plan, hist)
    assert set(tree(tmp_path)) == {os.path.join("2025", "01 - Janeiro", "jan.pdf"),
                                   os.path.join("2026", "10 - Outubro", "out.pdf")}


def test_regras_personalizadas_sem_acento(tmp_path, hist):
    write(tmp_path / "ADMISSAO Maria.pdf", b"1")
    write(tmp_path / "faturamento_outubro.xlsx", b"2")
    write(tmp_path / "Painel power bi.pbix", b"3")
    write(tmp_path / "sem regra.txt", b"4")
    plan = pl.build_plan(str(tmp_path), pl.MODE_RULES, rules=pl.DEFAULT_RULES)
    assert plan.unchanged == 1
    ex.execute_plan(plan, hist)
    assert set(tree(tmp_path)) == {
        os.path.join("RH", "Admissões", "ADMISSAO Maria.pdf"),
        os.path.join("Financeiro", "Faturamento", "faturamento_outubro.xlsx"),
        os.path.join("BI", "Projetos", "Painel power bi.pbix"),
        "sem regra.txt",
    }


@pytest.mark.parametrize("destino", ["../fora", "C:\\Windows", "/etc", "a/../../b", "RH/Adm?ssões", ""])
def test_regra_nao_sai_da_pasta(destino):
    with pytest.raises(ValueError):
        pl.validate_destination(destino)


def test_subpastas_so_quando_pedido(tmp_path):
    write(tmp_path / "raiz.pdf", b"1")
    write(tmp_path / "sub" / "dentro.pdf", b"2")
    assert len(pl.build_plan(str(tmp_path), pl.MODE_EXTENSION).moves) == 1
    assert len(pl.build_plan(str(tmp_path), pl.MODE_EXTENSION, include_subfolders=True).moves) == 2


def test_arquivo_ja_no_lugar_fica(tmp_path):
    write(tmp_path / "PDFs" / "a.pdf")
    plan = pl.build_plan(str(tmp_path), pl.MODE_EXTENSION, include_subfolders=True)
    assert plan.moves == [] and plan.unchanged == 1


def test_conflito_de_nome_nunca_sobrescreve(tmp_path, hist):
    write(tmp_path / "PDFs" / "contrato.pdf", b"original que ja estava la")
    write(tmp_path / "contrato.pdf", b"outro contrato")
    plan = pl.build_plan(str(tmp_path), pl.MODE_EXTENSION)
    assert plan.conflicts == 1
    ex.execute_plan(plan, hist)
    assert (tmp_path / "PDFs" / "contrato.pdf").read_bytes() == b"original que ja estava la"
    assert (tmp_path / "PDFs" / "contrato (2).pdf").read_bytes() == b"outro contrato"


def test_dois_arquivos_mesmo_destino(tmp_path, hist):
    write(tmp_path / "a" / "nota.pdf", b"A")
    write(tmp_path / "b" / "nota.pdf", b"B")
    plan = pl.build_plan(str(tmp_path), pl.MODE_EXTENSION, include_subfolders=True)
    ex.execute_plan(plan, hist)
    pdfs = {(tmp_path / "PDFs" / n).read_bytes() for n in os.listdir(tmp_path / "PDFs")}
    assert pdfs == {b"A", b"B"}


def test_arquivo_criado_no_destino_depois_da_previa(tmp_path, hist):
    write(tmp_path / "a.pdf", b"novo")
    plan = pl.build_plan(str(tmp_path), pl.MODE_EXTENSION)
    write(tmp_path / "PDFs" / "a.pdf", b"apareceu depois")
    result = ex.execute_plan(plan, hist)
    assert result.moved == 1 and result.renamed == 1
    assert (tmp_path / "PDFs" / "a.pdf").read_bytes() == b"apareceu depois"
    assert (tmp_path / "PDFs" / "a (2).pdf").read_bytes() == b"novo"


def test_arquivo_alterado_depois_da_previa_nao_e_movido(tmp_path, hist):
    write(tmp_path / "a.pdf", b"v1", datetime(2025, 1, 1))
    plan = pl.build_plan(str(tmp_path), pl.MODE_EXTENSION)
    write(tmp_path / "a.pdf", b"v2 mais longo")
    result = ex.execute_plan(plan, hist)
    assert result.moved == 0 and result.failed == 1
    assert (tmp_path / "a.pdf").exists()


def test_arquivo_em_uso(tmp_path, hist, monkeypatch):
    write(tmp_path / "a.pdf", b"1")
    write(tmp_path / "b.pdf", b"2")
    plan = pl.build_plan(str(tmp_path), pl.MODE_EXTENSION)
    real = ex._move_no_overwrite

    def bloqueado(src, dst):
        if src.endswith("a.pdf"):
            raise PermissionError(13, "em uso")
        real(src, dst)

    monkeypatch.setattr(ex, "_move_no_overwrite", bloqueado)
    result = ex.execute_plan(plan, hist)
    assert (result.moved, result.failed) == (1, 1)
    erros = [m.error for m in hist.moves(result.operation_id) if m.status == h.FAILED]
    assert erros and "em uso" in erros[0]
    assert hist.operations()[0].status == h.DONE_WITH_ERRORS


def test_historico_registra_tudo(tmp_path, hist):
    write(tmp_path / "a.pdf", b"1")
    plan = pl.build_plan(str(tmp_path), pl.MODE_EXTENSION)
    result = ex.execute_plan(plan, hist)
    op = hist.operations()[0]
    assert op.id == result.operation_id and op.status == h.DONE and op.moved == 1 and op.user and op.root
    move = hist.moves(op.id)[0]
    assert move.source == str(tmp_path / "a.pdf")
    assert move.destination == str(tmp_path / "PDFs" / "a.pdf")
    assert move.status == h.MOVED and move.when


def test_desfazer_restaura_tudo(tmp_path, hist):
    for name in ("a.pdf", "b.xlsx", "c.docx"):
        write(tmp_path / name, name.encode())
    write(tmp_path / "sub" / "d.pdf", b"d")
    before = tree(tmp_path)
    result = ex.execute_plan(pl.build_plan(str(tmp_path), pl.MODE_EXTENSION, include_subfolders=True), hist)
    assert tree(tmp_path) != before
    undo = ex.undo_operation(hist, result.operation_id)
    assert undo.restored == 4 and undo.blocked == []
    assert tree(tmp_path) == before
    assert sorted(os.listdir(tmp_path)) == ["a.pdf", "b.xlsx", "c.docx", "sub"]  # pastas criadas removidas
    assert hist.operations()[0].status == h.UNDONE
    with pytest.raises(ex.UndoNotAllowed):
        ex.undo_operation(hist, result.operation_id)


def test_desfazer_nao_sobrescreve_arquivo_modificado(tmp_path, hist):
    write(tmp_path / "a.pdf", b"original")
    write(tmp_path / "b.pdf", b"outro")
    result = ex.execute_plan(pl.build_plan(str(tmp_path), pl.MODE_EXTENSION), hist)
    write(tmp_path / "PDFs" / "a.pdf", b"editado depois da organizacao")
    undo = ex.undo_operation(hist, result.operation_id)
    assert undo.restored == 1 and len(undo.blocked) == 1
    assert (tmp_path / "PDFs" / "a.pdf").read_bytes() == b"editado depois da organizacao"
    assert (tmp_path / "b.pdf").read_bytes() == b"outro"
    assert hist.operations()[0].status == h.PARTIALLY_UNDONE


def test_desfazer_nao_sobrescreve_local_original_ocupado(tmp_path, hist):
    write(tmp_path / "a.pdf", b"organizado")
    result = ex.execute_plan(pl.build_plan(str(tmp_path), pl.MODE_EXTENSION), hist)
    write(tmp_path / "a.pdf", b"novo arquivo com o mesmo nome")
    undo = ex.undo_operation(hist, result.operation_id)
    assert undo.restored == 0
    assert (tmp_path / "a.pdf").read_bytes() == b"novo arquivo com o mesmo nome"
    assert (tmp_path / "PDFs" / "a.pdf").read_bytes() == b"organizado"


def test_cancelamento_e_interrupcao(tmp_path, hist):
    for i in range(10):
        write(tmp_path / f"f{i}.pdf", str(i).encode())
    plan = pl.build_plan(str(tmp_path), pl.MODE_EXTENSION)
    cancel = threading.Event()
    moved = []

    def progress(stage, done, total):
        moved.append(done)
        if done == 4:
            cancel.set()

    result = ex.execute_plan(plan, hist, cancel, progress)
    assert result.cancelled and result.moved == 4
    assert hist.operations()[0].status == h.INTERRUPTED
    undo = ex.undo_operation(hist, result.operation_id)
    assert undo.restored == 4
    assert len(os.listdir(tmp_path)) == 10


def test_queda_no_meio_do_movimento(tmp_path, hist):
    """Simula o computador desligando depois de mover e antes de gravar no histórico."""
    write(tmp_path / "a.pdf", b"1")
    plan = pl.build_plan(str(tmp_path), pl.MODE_EXTENSION)
    op_id = hist.start_operation(plan.root, plan.mode, plan.moves)
    os.makedirs(tmp_path / "PDFs")
    os.rename(tmp_path / "a.pdf", tmp_path / "PDFs" / "a.pdf")
    reopened = h.History(hist.path)
    assert reopened.mark_interrupted() == 1
    undo = ex.undo_operation(reopened, op_id)
    reopened.close()
    assert undo.restored == 1 and (tmp_path / "a.pdf").exists()


def test_regras_salvas(tmp_path):
    regras = [pl.Rule("Contrato", "Jurídico/Contratos")]
    pl.save_rules(regras)
    assert pl.load_rules() == regras


def test_nunca_exclui_arquivos(tmp_path, hist):
    for i in range(30):
        write(tmp_path / f"sub{i % 3}" / f"arquivo{i}.{['pdf', 'xlsx', 'docx'][i % 3]}", os.urandom(100))
    conteudo_antes = sorted(tree(tmp_path).values())
    result = ex.execute_plan(pl.build_plan(str(tmp_path), pl.MODE_EXTENSION, include_subfolders=True), hist)
    assert sorted(tree(tmp_path).values()) == conteudo_antes
    ex.undo_operation(hist, result.operation_id)
    assert sorted(tree(tmp_path).values()) == conteudo_antes
