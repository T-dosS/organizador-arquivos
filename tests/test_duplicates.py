"""Testes do detector de duplicados exatos.

Cobrem os cenários obrigatórios do item 11 da especificação que se aplicam ao MVP.
"""

from __future__ import annotations

import hashlib
import os
import threading

import pytest

from acme.core import duplicates as dup
from acme.core.paths import PathNotAllowed, long_path, validate_root
from acme.core.report import export_csv, format_size
from acme.core.scanner import Cancelled, scan


def write(path, data: bytes, mtime: float | None = None):
    # long_path: no Windows sem caminhos longos liberados, o próprio teste não conseguiria criar as pastas.
    os.makedirs(long_path(str(path.parent)), exist_ok=True)
    with open(long_path(str(path)), "wb") as fh:
        fh.write(data)
    if mtime is not None:
        os.utime(long_path(str(path)), (mtime, mtime))
    return path


def analyze(folder, strict=False):
    result = scan(folder)
    return result, dup.find_duplicates(result.files, strict=strict)


def snapshot(folder):
    """Hash, tamanho e data de todos os arquivos, para provar que a análise não altera nada."""
    state = {}
    for dirpath, _, names in os.walk(folder):
        for name in names:
            p = os.path.join(dirpath, name)
            st = os.stat(p)
            with open(p, "rb") as fh:
                state[p] = (hashlib.sha256(fh.read()).hexdigest(), st.st_size, st.st_mtime_ns)
    return state


def test_pasta_vazia(tmp_path):
    result, report = analyze(tmp_path)
    assert result.files == [] and result.folder_count == 0
    assert report.groups == [] and report.recoverable_bytes == 0


def test_nomes_diferentes_conteudo_identico(tmp_path):
    content = b"planilha de faturamento" * 1000
    write(tmp_path / "Relatorio_Final.xlsx", content)
    write(tmp_path / "Relatorio_Final_2.xlsx", content)
    write(tmp_path / "sub" / "Copia_Relatorio.xlsx", content)
    _, report = analyze(tmp_path)
    assert len(report.groups) == 1
    group = report.groups[0]
    assert group.copies == 3
    assert group.classification == dup.EXACT_DUPLICATE
    assert group.sha256 == hashlib.sha256(content).hexdigest()
    assert group.recoverable_bytes == len(content) * 2
    assert {f.name for f in group.files} == {"Relatorio_Final.xlsx", "Relatorio_Final_2.xlsx", "Copia_Relatorio.xlsx"}


def test_mesmo_nome_conteudo_diferente(tmp_path):
    write(tmp_path / "a" / "Relatorio.xlsx", b"versao A")
    write(tmp_path / "b" / "Relatorio.xlsx", b"versao B")
    _, report = analyze(tmp_path)
    assert report.groups == []
    assert report.unique_files == 2


def test_mesmo_tamanho_hash_diferente(tmp_path):
    write(tmp_path / "x.bin", b"A" * 4096)
    write(tmp_path / "y.bin", b"B" * 4096)
    _, report = analyze(tmp_path)
    assert report.groups == []
    assert report.files_hashed == 0  # descartados já no hash parcial


def test_arquivo_grande_difere_so_no_fim(tmp_path):
    big = os.urandom(3 * 1024 * 1024 + 17)
    write(tmp_path / "grande1.dat", big)
    write(tmp_path / "grande2.dat", big)
    write(tmp_path / "grande3.dat", big[:-1] + bytes([big[-1] ^ 0xFF]))
    _, report = analyze(tmp_path)
    assert len(report.groups) == 1
    assert {f.name for f in report.groups[0].files} == {"grande1.dat", "grande2.dat"}


def test_modo_rigoroso_confirma_byte_a_byte(tmp_path):
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        write(tmp_path / name, b"%PDF-1.7 conteudo" * 500)
    _, report = analyze(tmp_path, strict=True)
    assert len(report.groups) == 1
    assert report.groups[0].byte_verified
    assert report.groups[0].copies == 3


def test_modo_rigoroso_separa_colisao(tmp_path, monkeypatch):
    """Simula uma colisão de hash: o modo rigoroso não pode agrupar arquivos diferentes."""
    write(tmp_path / "a.txt", b"conteudo um")
    write(tmp_path / "b.txt", b"conteudo 2!")
    monkeypatch.setattr(dup._Hasher, "sha256", lambda self, path, limit=None: "0" * 64)
    _, normal = analyze(tmp_path)
    assert len(normal.groups) == 1  # sem confirmação, a colisão simulada passaria
    _, strict = analyze(tmp_path, strict=True)
    assert strict.groups == []


def test_arquivos_vazios_nao_sao_duplicados(tmp_path):
    write(tmp_path / "vazio1.txt", b"")
    write(tmp_path / "vazio2.txt", b"")
    _, report = analyze(tmp_path)
    assert report.groups == []
    assert len(report.empty_files) == 2


def test_analise_nao_altera_originais(tmp_path):
    content = os.urandom(200_000)
    write(tmp_path / "um.docx", content, mtime=1_600_000_000)
    write(tmp_path / "dois.docx", content, mtime=1_600_000_000)
    write(tmp_path / "tres.docx", b"outro", mtime=1_600_000_000)
    before = snapshot(tmp_path)
    analyze(tmp_path, strict=True)
    assert snapshot(tmp_path) == before
    assert sorted(os.listdir(tmp_path)) == ["dois.docx", "tres.docx", "um.docx"]


def test_caracteres_especiais(tmp_path):
    content = b"admissao"
    write(tmp_path / "Admissão João – férias (cópia) №1.docx", content)
    write(tmp_path / "pasta com espaços" / "ação 😀.docx", content)
    _, report = analyze(tmp_path)
    assert len(report.groups) == 1 and report.groups[0].copies == 2


def test_caminho_longo(tmp_path):
    folder = tmp_path
    for i in range(6):
        folder = folder / (f"subpasta_{i}_" + "x" * 40)
    content = b"caminho longo"
    write(folder / ("arquivo_" + "y" * 60 + ".txt"), content)
    write(tmp_path / "curto.txt", content)
    _, report = analyze(tmp_path)
    assert len(report.groups) == 1


def test_arquivo_bloqueado_nao_interrompe(tmp_path, monkeypatch):
    for name in ("a.txt", "b.txt", "c.txt"):
        write(tmp_path / name, b"mesmo conteudo")
    real_open = open

    def fake_open(path, *args, **kwargs):
        if str(path).endswith("b.txt"):
            raise PermissionError(13, "bloqueado")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    _, report = analyze(tmp_path)
    assert len(report.groups) == 1 and report.groups[0].copies == 2
    assert [s.reason for s in report.not_analyzed] == ["Arquivo bloqueado ou sem permissão"]


def test_arquivo_somente_na_nuvem_nao_e_lido(tmp_path, monkeypatch):
    write(tmp_path / "local.xlsx", b"dados")
    write(tmp_path / "nuvem.xlsx", b"dados")
    result = scan(tmp_path)
    files = [f if f.name == "local.xlsx" else dup.FileEntry(f.path, f.name, f.size, f.mtime, cloud_only=True)
             for f in result.files]
    opened = []
    real_sha = dup._Hasher.sha256
    monkeypatch.setattr(dup._Hasher, "sha256", lambda self, p, limit=None: opened.append(p) or real_sha(self, p, limit))
    report = dup.find_duplicates(files)
    assert report.groups == []
    assert not any(p.endswith("nuvem.xlsx") for p in opened)
    assert report.not_analyzed[0].reason.startswith("Disponível somente na nuvem")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="sem suporte a links")
def test_links_nao_sao_seguidos(tmp_path):
    outside = tmp_path / "fora"
    write(outside / "segredo.txt", b"fora do escopo")
    root = tmp_path / "escopo"
    write(root / "dentro.txt", b"fora do escopo")
    try:
        os.symlink(outside, root / "link_pasta", target_is_directory=True)
        os.symlink(outside / "segredo.txt", root / "link_arquivo.txt")
    except OSError:
        pytest.skip("criação de links não permitida neste sistema")
    result, report = analyze(root)
    assert [f.name for f in result.files] == ["dentro.txt"]
    assert report.groups == []
    assert len(result.skipped) == 2


def test_cancelamento(tmp_path):
    for i in range(20):
        write(tmp_path / f"f{i}.bin", b"x" * 1000)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        scan(tmp_path, cancel=cancel)
    result = scan(tmp_path)
    with pytest.raises(Cancelled):
        dup.find_duplicates(result.files, cancel=cancel)


def test_milhares_de_arquivos(tmp_path):
    for i in range(3000):
        write(tmp_path / f"p{i % 30}" / f"arquivo_{i}.txt", f"conteudo {i % 1000}".encode())
    result, report = analyze(tmp_path)
    assert len(result.files) == 3000
    assert result.folder_count == 30
    assert len(report.groups) == 1000
    assert report.duplicate_files == 3000


def test_pastas_protegidas(tmp_path):
    with pytest.raises(PathNotAllowed):
        validate_root(os.path.abspath(os.sep))
    with pytest.raises(PathNotAllowed):
        validate_root(tmp_path / "nao_existe")
    write(tmp_path / "arquivo.txt", b"x")
    with pytest.raises(PathNotAllowed):
        validate_root(tmp_path / "arquivo.txt")


def test_pasta_do_sistema_windows_bloqueada(tmp_path, monkeypatch):
    system = tmp_path / "Windows"
    system.mkdir()
    monkeypatch.setenv("SystemRoot", str(system))
    with pytest.raises(PathNotAllowed):
        validate_root(system / ".")


def test_exportar_csv_sem_sobrescrever(tmp_path):
    write(tmp_path / "dados" / "a.csv", b"1;2;3")
    write(tmp_path / "dados" / "b.csv", b"1;2;3")
    _, report = analyze(tmp_path / "dados")
    out = tmp_path / "relatorio.csv"
    export_csv(report, str(out))
    text = out.read_text(encoding="utf-8-sig")
    assert "Duplicado exato" in text and "a.csv" in text and "b.csv" in text
    with pytest.raises(FileExistsError):
        export_csv(report, str(out))


def test_formato_tamanho():
    assert format_size(0) == "0 bytes"
    assert format_size(1536) == "1,5 KB"
    assert format_size(5 * 1024**3) == "5,0 GB"
