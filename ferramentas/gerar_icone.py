r"""Gera recursos\icone.ico (e uma prévia .png) com as cores da identidade ACME.

Desenho: quadrado arredondado vermelho ACME, uma pasta branca e um selo verde com visto
(arquivos conferidos), no mesmo estilo do ícone do AutomacoesACME.
Uso: python ferramentas\gerar_icone.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

VERMELHO, VERMELHO_ESCURO, VERDE, BRANCO = "#A50008", "#6E0005", "#1E7F45", "#FFFFFF"
ESCALA = 4  # desenha grande e reduz: bordas suaves
L = 256 * ESCALA


def desenhar() -> Image.Image:
    img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m, r = int(L * 0.04), int(L * 0.20)
    d.rounded_rectangle((m, m + int(L * 0.02), L - m, L - m), r, fill=VERMELHO_ESCURO)  # sombra
    d.rounded_rectangle((m, m, L - m, L - m - int(L * 0.02)), r, fill=VERMELHO)
    # pasta: aba em cima à esquerda e corpo
    x0, y0, x1, y1 = int(L * 0.18), int(L * 0.30), int(L * 0.78), int(L * 0.72)
    raio = int(L * 0.04)
    d.rounded_rectangle((x0, y0 - int(L * 0.06), x0 + int(L * 0.24), y0 + int(L * 0.04)), raio, fill=BRANCO)
    d.rounded_rectangle((x0, y0, x1, y1), raio, fill=BRANCO)
    d.line([(x0 + int(L * 0.04), y0 + int(L * 0.09)), (x1 - int(L * 0.04), y0 + int(L * 0.09))],
           fill=VERMELHO, width=int(L * 0.015))
    # selo verde com visto
    cx, cy, rr = int(L * 0.74), int(L * 0.70), int(L * 0.17)
    borda = int(L * 0.025)
    d.ellipse((cx - rr - borda, cy - rr - borda, cx + rr + borda, cy + rr + borda), fill=BRANCO)
    d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=VERDE)
    d.line([(cx - rr * 0.48, cy + rr * 0.02), (cx - rr * 0.10, cy + rr * 0.40), (cx + rr * 0.50, cy - rr * 0.35)],
           fill=BRANCO, width=int(L * 0.035), joint="curve")
    return img.resize((256, 256), Image.LANCZOS)


if __name__ == "__main__":
    pasta = Path(__file__).resolve().parent.parent / "recursos"
    pasta.mkdir(exist_ok=True)
    img = desenhar()
    img.save(pasta / "icone.png")
    img.save(pasta / "icone.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(pasta / "icone.ico")
