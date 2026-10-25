"""Monta como SVG os símbolos compostos: o círculo de elementos e o estandarte de dupla classe.

1 elemento: o símbolo inteiro.
2 elementos: círculo cortado por uma linha a 45°, um símbolo em cada metade.
3 elementos: cortes a 90°, 210° e 330°, um símbolo em cada setor.
O custo de carga, quando houver, aparece por cima, no centro, e os símbolos
ficam esmaecidos atrás dele.

Os glifos vêm de frames/icones/elementos/<chave>.svg, sem o anel externo
(o anel é redesenhado aqui, em arcos com a cor de cada elemento).
Ângulos em graus, no sentido matemático: 0° à direita, 90° para cima.

Dupla classe: um estandarte do tamanho normal, partido ao meio por uma linha
vertical: metade esquerda do glifo da 1ª classe, metade direita do da 2ª. Os glifos vêm
de frames/icones/classes/<chave>.svg, sem o pano e a haste.
"""

import math
import re
from functools import lru_cache
from pathlib import Path

from markupsafe import Markup

R_ANEL = 45          # raio do anel externo (igual ao dos símbolos)
TRACO_ANEL = 5
FUNDO = "#11131a"
PRATA = "#c3c9d4"

# cortes e posição/tamanho dos glifos para cada quantidade de elementos
CORTES = {2: [45, 225], 3: [90, 210, 330]}
GLIFO = {2: (28, 0.37), 3: (29, 0.33)}   # (distância do centro, escala)


def _ponto(angulo, raio):
    a = math.radians(angulo)
    return 50 + raio * math.cos(a), 50 - raio * math.sin(a)


def _f(x):
    return f"{x:.2f}".rstrip("0").rstrip(".")


# moldura de cada família de símbolo, removida para sobrar só o glifo
MOLDURA_ELEMENTO = r'<circle\s+cx="50"\s+cy="50"\s+r="45"[^>]*/>'
MOLDURA_ESTANDARTE = r'<path d="M(?:10 8 H70|3 7 H77)[^>]*/>'


@lru_cache(maxsize=None)
def _glifo_do_arquivo(caminho, _mtime, moldura=MOLDURA_ELEMENTO):
    """Conteúdo do símbolo sem a moldura da família."""
    texto = Path(caminho).read_text(encoding="utf-8")
    m = re.search(r"<svg[^>]*>(.*)</svg>", texto, re.S)
    corpo = m.group(1) if m else texto
    return re.sub(moldura, "", corpo)


def _glifo(e):
    caminho = e.get("icone_arquivo")
    if caminho and caminho.suffix == ".svg":
        return _glifo_do_arquivo(str(caminho), caminho.stat().st_mtime)
    # sem ícone: sigla na cor do elemento
    return (f'<text x="50" y="50" text-anchor="middle" dominant-baseline="central" '
            f'font-family="Source Sans 3, sans-serif" font-weight="700" font-size="34" '
            f'fill="{e["cor"]}">{e["sigla"]}</text>')


def _setor(a0, a1, raio):
    x0, y0 = _ponto(a0, raio)
    x1, y1 = _ponto(a1, raio)
    grande = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M50 50 L{_f(x0)} {_f(y0)} A{raio} {raio} 0 {grande} 0 {_f(x1)} {_f(y1)} Z"


def _arco(a0, a1, raio):
    x0, y0 = _ponto(a0, raio)
    x1, y1 = _ponto(a1, raio)
    grande = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M{_f(x0)} {_f(y0)} A{raio} {raio} 0 {grande} 0 {_f(x1)} {_f(y1)}"


def _numero_custo(custo):
    """Custo de carga por cima do círculo, com contorno escuro para ler sobre os símbolos."""
    return (f'<text x="50" y="52" text-anchor="middle" dominant-baseline="central" '
            f'font-family="Source Sans 3, sans-serif" font-weight="800" font-size="50" '
            f'fill="#f4f1ea" stroke="{FUNDO}" stroke-width="7" stroke-linejoin="round" '
            f'paint-order="stroke">{custo}</text>')


# com custo, os símbolos ficam esmaecidos atrás do número
OPACIDADE_COM_CUSTO = 0.4


def circulo_elementos(elementos, custo=None, classe="elementos"):
    """SVG inline (Markup) com os elementos e, se houver, o custo de carga por cima."""
    n = len(elementos)
    fundo = [f'<circle cx="50" cy="50" r="{R_ANEL + TRACO_ANEL / 2}" fill="{FUNDO}"/>']
    aneis, glifos = [], []

    if n == 0:
        aneis.append(f'<circle cx="50" cy="50" r="{R_ANEL}" fill="none" stroke="#5d647a" stroke-width="{TRACO_ANEL}"/>')
    elif n == 1:
        e = elementos[0]
        aneis.append(f'<circle cx="50" cy="50" r="{R_ANEL}" fill="none" stroke="{e["cor"]}" stroke-width="{TRACO_ANEL}"/>')
        glifos.append(_glifo(e))
    else:
        cortes = CORTES[n]
        dist, escala = GLIFO[n]
        for i, e in enumerate(elementos):
            a0 = cortes[i]
            a1 = cortes[(i + 1) % n] + (360 if i + 1 == n else 0)
            meio = (a0 + a1) / 2
            fundo.append(f'<path d="{_setor(a0, a1, R_ANEL)}" fill="{e["cor"]}" fill-opacity="0.16"/>')
            aneis.append(f'<path d="{_arco(a0, a1, R_ANEL)}" fill="none" stroke="{e["cor"]}" stroke-width="{TRACO_ANEL}"/>')
            x, y = _ponto(meio, dist)
            glifos.append(f'<g transform="translate({_f(x)} {_f(y)}) scale({escala}) translate(-50 -50)">{_glifo(e)}</g>')
        # linhas de corte, do centro até fora do anel
        for a in cortes:
            x, y = _ponto(a, R_ANEL + TRACO_ANEL)
            aneis.append(f'<path d="M50 50 L{_f(x)} {_f(y)}" stroke="{FUNDO}" stroke-width="3.5"/>')

    partes = fundo + aneis
    if custo:
        partes.append(f'<g opacity="{OPACIDADE_COM_CUSTO}">{"".join(glifos)}</g>')
        partes.append(_numero_custo(custo))
    else:
        partes += glifos

    titulo = " / ".join(e["nome"] for e in elementos) or "Sem elemento"
    if custo:
        titulo += f" · custo de carga {custo}"
    return Markup(f'<svg class="{classe}" viewBox="0 0 100 100" role="img" aria-label="{titulo}">'
                  f'<title>{titulo}</title>{"".join(partes)}</svg>')


def _estrela_pontas(n, r_ext, r_int, centro=60):
    pts = []
    for i in range(2 * n):
        x, y = _ponto(90 + i * 180 / n, r_ext if i % 2 == 0 else r_int)
        pts.append(f"{_f(x - 50 + centro)},{_f(y - 50 + centro)}")
    return " ".join(pts)


def moldura_avancada(interno, cor, titulo, classe="elementos"):
    """Moldura rúnica de carta avançada em volta de um círculo de 100 x 100 (elemento da runa,
    ícone do campo ou do retiro): estrela de 8 pontas na cor do elemento, anel fino e entalhes
    entre as pontas. viewBox 120 x 120 com o círculo no centro, no mesmo tamanho do comum."""
    entalhes = []
    for i in range(8):
        a = 90 + 22.5 + i * 45
        x0, y0 = _ponto(a, 49)
        x1, y1 = _ponto(a, 53)
        entalhes.append(f'<path d="M{_f(x0 + 10)} {_f(y0 + 10)} L{_f(x1 + 10)} {_f(y1 + 10)}"/>')
    return Markup(
        f'<svg class="{classe} moldura-avancada" viewBox="0 0 120 120" role="img" aria-label="{titulo}">'
        f'<title>{titulo}</title>'
        f'<polygon class="moldura-estrela" points="{_estrela_pontas(8, 57, 47)}" fill="{FUNDO}" stroke="{cor}"/>'
        f'<polygon class="moldura-estrela-filete" points="{_estrela_pontas(8, 52.5, 47.5)}" stroke="{cor}"/>'
        f'<circle class="moldura-anel" cx="60" cy="60" r="51" stroke="{cor}"/>'
        f'<g class="moldura-entalhes" stroke="{cor}">{"".join(entalhes)}</g>'
        f'<svg x="10" y="10" width="100" height="100" viewBox="0 0 100 100">{interno}</svg></svg>')


def circulo_runa_avancada(elementos):
    """Runa avançada: o círculo de elementos dentro da moldura rúnica."""
    cor = elementos[0]["cor"] if elementos else PRATA
    titulo = " / ".join(e["nome"] for e in elementos) + " · runa avançada"
    return moldura_avancada(circulo_elementos(elementos), cor, titulo)


def circulo_local(s, cor, avancado):
    """Campo de batalha e retiro: ícone do tipo (frames/icones/locais/) num círculo com o anel
    na cor do elemento, à esquerda da barra do nome; avançado, dentro da moldura rúnica."""
    caminho = s.get("icone_arquivo")
    if caminho and caminho.suffix == ".svg":
        glifo = re.search(r"<svg[^>]*>(.*)</svg>", _svg_do_arquivo(str(caminho), caminho.stat().st_mtime), re.S).group(1)
    else:
        glifo = (f'<text x="50" y="52" text-anchor="middle" dominant-baseline="central" '
                 f'font-family="Source Sans 3, sans-serif" font-weight="700" font-size="34" fill="#efe6d2">{s["sigla"]}</text>')
    circulo = (f'<circle cx="50" cy="50" r="{R_ANEL + TRACO_ANEL / 2}" fill="{FUNDO}"/>'
               f'<circle cx="50" cy="50" r="{R_ANEL}" fill="none" stroke="{cor}" stroke-width="{TRACO_ANEL}"/>'
               f'<g transform="translate(50 50) scale(0.66) translate(-50 -50)">{glifo}</g>')
    titulo = s["nome"] + (" · avançado" if avancado else "")
    if avancado:
        return moldura_avancada(circulo, cor, titulo, classe="icone-local")
    return Markup(f'<svg class="icone-local" viewBox="0 0 100 100" role="img" aria-label="{titulo}">'
                  f'<title>{titulo}</title>{circulo}</svg>')


def circulo_texto(texto, rotulo, classe="elementos"):
    """Círculo prateado com um texto curto no centro (slot do item, níveis da quest)."""
    tam = 44 if len(str(texto)) <= 2 else 34
    return Markup(
        f'<svg class="{classe}" viewBox="0 0 100 100" role="img" aria-label="{rotulo}"><title>{rotulo}</title>'
        f'<circle cx="50" cy="50" r="{R_ANEL + TRACO_ANEL / 2}" fill="{FUNDO}"/>'
        f'<circle cx="50" cy="50" r="{R_ANEL}" fill="none" stroke="{PRATA}" stroke-width="{TRACO_ANEL}"/>'
        f'<text x="50" y="52" text-anchor="middle" dominant-baseline="central" '
        f'font-family="Source Sans 3, sans-serif" font-weight="800" font-size="{tam}" fill="#f4f1ea">{texto}</text></svg>')


# vértices do hexágono vertical (o mesmo dos selos de palavra-chave), viewBox 100 x 110
HEX = [(50, 3), (95, 28), (95, 82), (50, 107), (5, 82), (5, 28)]
HEX_CENTRO = (50, 55)


def _hex_escala(fator):
    cx, cy = HEX_CENTRO
    return [(cx + (x - cx) * fator, cy + (y - cy) * fator) for x, y in HEX]


def _pts(pontos):
    return " ".join(f"{_f(x)},{_f(y)}" for x, y in pontos)


def hexagono_poder(valor):
    """Símbolo de poder: hexágono lapidado e preenchido na cor do tema (mesma forma dos selos de
    palavra-chave, mas cheio). Seis facetas com luz vindo de cima à esquerda, uma mesa central
    lisa com o valor, brilho diagonal, filete de bisel e contorno escuro. Cores em frame.css."""
    externo, mesa = HEX, _hex_escala(0.58)
    # facetas na ordem das arestas: cima-direita, direita, baixo-direita, baixo-esquerda, esquerda, cima-esquerda
    nomes = ["f-cd", "f-d", "f-bd", "f-be", "f-e", "f-ce"]
    facetas = "".join(
        f'<polygon class="{nomes[k]}" points="{_pts([externo[k], externo[(k + 1) % 6], mesa[(k + 1) % 6], mesa[k]])}"/>'
        for k in range(6))
    brilho = _pts([(14, 33), (50, 12), (60, 18), (22, 42)])
    return Markup(
        f'<svg class="gema gema-poder" viewBox="0 0 100 110" role="img" aria-label="poder {valor}">'
        f'<title>poder {valor}</title>'
        # luz suave na mesa (mesmo id em todas as cartas: a definição é idêntica)
        f'<defs><radialGradient id="poder-luz" cx="35%" cy="28%" r="75%">'
        f'<stop offset="0" stop-color="#fff" stop-opacity="0.38"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>'
        f'</radialGradient></defs>'
        f'<polygon class="contorno-fundo" points="{_pts(externo)}"/>'
        f'{facetas}'
        f'<polygon class="mesa" points="{_pts(mesa)}"/>'
        f'<polygon class="mesa-luz" points="{_pts(mesa)}"/>'
        f'<polygon class="reflexo" points="{brilho}"/>'
        f'<polygon class="filete" points="{_pts(_hex_escala(0.9))}"/>'
        f'<polygon class="contorno" points="{_pts(externo)}"/>'
        f'<text x="50" y="57">{valor}</text></svg>')


def selo_chave(s):
    """Palavra-chave com ícone: selo hexagonal escuro, contorno na cor do tema, glifo creme
    (frames/icones/palavras-chave/<chave>.svg) e o valor, se houver, num círculo embaixo."""
    caminho = s["icone_arquivo"]
    corpo = re.search(r"<svg[^>]*>(.*)</svg>", _svg_do_arquivo(str(caminho), caminho.stat().st_mtime), re.S).group(1)
    titulo = f'{s["nome"]} {s["valor"]}' if s.get("valor") else s["nome"]
    # com valor, o glifo sobe e diminui e o número fica dentro do hexágono, embaixo
    glifo, valor = "translate(14 19) scale(0.72)", ""
    if s.get("valor"):
        glifo = "translate(23 11) scale(0.54)"
        valor = f'<text class="chave-valor" x="50" y="83">{s["valor"]}</text>'
    return Markup(
        f'<svg class="selo-chave" viewBox="0 0 100 110" role="img" aria-label="{titulo}"><title>{titulo}</title>'
        f'<polygon class="hex-fundo" points="50,3 95,28 95,82 50,107 5,82 5,28"/>'
        f'<polygon class="hex-filete" points="50,11 88,32 88,78 50,99 12,78 12,32"/>'
        f'<g transform="{glifo}">{corpo}</g>{valor}</svg>')


MOEDA_ICONE = Path(__file__).resolve().parent.parent / "frames" / "icones" / "marcas" / "moeda.svg"


def moeda_custo(valor):
    """Custo em moedas do item, no padrão do círculo de elementos: anel prateado (o tema do item),
    o desenho das duas moedas (frames/icones/marcas/moeda.svg, redesenho do esboço do usuário)
    e o valor por cima, como o custo de carga."""
    glifo = re.search(r"<svg[^>]*>(.*)</svg>",
                      _svg_do_arquivo(str(MOEDA_ICONE), MOEDA_ICONE.stat().st_mtime), re.S).group(1)
    return Markup(
        f'<svg class="elementos moeda" viewBox="0 0 100 100" role="img" aria-label="custo {valor} moedas">'
        f'<title>custo {valor} moedas</title>'
        f'<circle cx="50" cy="50" r="{R_ANEL + TRACO_ANEL / 2}" fill="{FUNDO}"/>'
        f'<circle cx="50" cy="50" r="{R_ANEL}" fill="none" stroke="{PRATA}" stroke-width="{TRACO_ANEL}"/>'
        f'<g transform="translate(50 50) scale(0.82) translate(-50 -50)">{glifo}</g>'
        f'{_numero_custo(valor)}</svg>')


def medalhao_slot(s, lendario):
    """Item: um único medalhão no centro da carta diz tudo. Glifo do slot no meio; lendário com
    contorno duplo, losangos nos pontos cardeais e halo; comum (ficha) com um anel simples."""
    caminho = s.get("icone_arquivo")
    if caminho and caminho.suffix == ".svg":
        glifo = re.search(r"<svg[^>]*>(.*)</svg>", _svg_do_arquivo(str(caminho), caminho.stat().st_mtime), re.S).group(1)
    else:
        glifo = (f'<text x="50" y="52" text-anchor="middle" dominant-baseline="central" '
                 f'font-family="Source Sans 3, sans-serif" font-weight="700" font-size="34" fill="#efe6d2">{s["sigla"]}</text>')
    titulo = f'{"Item lendário" if lendario else "Item comum"} · {s["nome"]}'
    enfeite = ""
    if lendario:
        losango = lambda x, y: f'<polygon class="med-losango" points="{x},{y - 7} {x + 6},{y} {x},{y + 7} {x - 6},{y}"/>'
        enfeite = ('<circle class="med-anel-ext" cx="60" cy="60" r="56"/>'
                   + losango(60, 4) + losango(116, 60) + losango(60, 116) + losango(4, 60))
    return Markup(
        f'<svg class="medalhao{" lendario" if lendario else ""}" viewBox="0 0 120 120" role="img" aria-label="{titulo}">'
        f'<title>{titulo}</title>{enfeite}'
        f'<circle class="med-fundo" cx="60" cy="60" r="46"/>'
        f'<circle class="med-filete" cx="60" cy="60" r="40"/>'
        f'<g transform="translate(29 29) scale(0.62)">{glifo}</g></svg>')


# ---------- tema de cor da carta ----------
# Sem elemento: prateado. Com elementos: a cor de cada um, em partes iguais da
# esquerda para a direita, na mesma ordem do círculo.

TEXTO_ESCURO, TEXTO_CLARO = "#15181f", "#f4f1ea"


def _luminancia(cor):
    r, g, b = (int(cor.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def cor_do_texto(fundo):
    """Texto escuro ou claro, o que contrastar mais com a cor de fundo."""
    l = _luminancia(fundo)
    return TEXTO_ESCURO if (l + 0.05) / 0.05 >= 1.05 / (l + 0.05) else TEXTO_CLARO


def escurecer(cor, quanto=0.35):
    r, g, b = (int(cor.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return "#" + "".join(f"{round(c * (1 - quanto)):02x}" for c in (r, g, b))


def _contorno_estrela(cores):
    """Paradas do gradiente do contorno da estrela, que fica no centro do trapézio:
    com 2 cores ela está sobre a divisão (metade de cada); com 3, dentro da do meio."""
    escuras = [escurecer(c) for c in cores]
    if len(escuras) == 2:
        return [(escuras[0], 0, 50), (escuras[1], 50, 100)]
    meio = escuras[len(escuras) // 2]
    return [(meio, 0, 100)]


def tema(elementos):
    cores = [e["cor"] for e in elementos] or [PRATA]
    n = len(cores)
    if n == 1:
        grad = f"linear-gradient({cores[0]}, {cores[0]})"
    else:
        paradas = ", ".join(f"{c} {i * 100 / n:.2f}% {(i + 1) * 100 / n:.2f}%" for i, c in enumerate(cores))
        grad = f"linear-gradient(90deg, {paradas})"
    paradas_svg = [(c, round(i * 100 / n, 2), round((i + 1) * 100 / n, 2)) for i, c in enumerate(cores)]
    return {"a": cores[0], "z": cores[-1], "grad": grad, "estrela": _contorno_estrela(cores), "paradas": paradas_svg,
            "texto_esq": cor_do_texto(cores[0]), "texto_dir": cor_do_texto(cores[-1])}


# ---------- estandartes de classe ----------

@lru_cache(maxsize=None)
def _svg_do_arquivo(caminho, _mtime):
    return Path(caminho).read_text(encoding="utf-8")


def estandarte(s, cor=PRATA):
    """Estandarte da classe inline, na cor do tema. None se a classe não tiver ícone SVG."""
    caminho = s.get("icone_arquivo")
    if not (caminho and caminho.suffix == ".svg"):
        return None
    svg = _svg_do_arquivo(str(caminho), caminho.stat().st_mtime).replace(PRATA, cor)
    svg = svg.replace("<svg ", f'<svg class="estandarte" role="img" aria-label="{s["nome"]}" ', 1)
    return Markup(svg)


# ---------- estandarte de dupla classe ----------

# mesmo tamanho do estandarte simples (80 x 100): cada glifo fica no lugar e no
# tamanho original, mas só aparece a metade esquerda da 1ª classe e a direita da 2ª
PANO = "M10 8 H70 V72 L40 96 L10 72 Z"
MEIO = 40


def _glifo_classe(s, cor):
    caminho = s.get("icone_arquivo")
    if caminho and caminho.suffix == ".svg":
        return _glifo_do_arquivo(str(caminho), caminho.stat().st_mtime, MOLDURA_ESTANDARTE).replace(PRATA, cor)
    return (f'<text x="40" y="43" text-anchor="middle" dominant-baseline="central" '
            f'font-family="Source Sans 3, sans-serif" font-weight="700" font-size="30" '
            f'fill="{cor}">{s["sigla"]}</text>')


def estandarte_duplo(a, b, cor=PRATA):
    """SVG inline (Markup) de um estandarte com meia classe de cada lado."""
    ident = f'{a["chave"]}-{b["chave"]}-{cor.lstrip("#")}'  # ids iguais entre cartas iguais não conflitam: o recorte é o mesmo
    partes = [
        f'<defs><clipPath id="meia-esq-{ident}"><rect x="0" y="0" width="{MEIO}" height="100"/></clipPath>'
        f'<clipPath id="meia-dir-{ident}"><rect x="{MEIO}" y="0" width="{80 - MEIO}" height="100"/></clipPath></defs>',
        f'<path d="{PANO}" fill="{FUNDO}"/>',
        f'<g clip-path="url(#meia-esq-{ident})">{_glifo_classe(a, cor)}</g>',
        f'<g clip-path="url(#meia-dir-{ident})">{_glifo_classe(b, cor)}</g>',
        f'<path d="M{MEIO} 8 V96" stroke="{cor}" stroke-width="3"/>',
        f'<path d="{PANO}" fill="none" stroke="{cor}" stroke-width="4.5" stroke-linejoin="round"/>',
        f'<path d="M3 7 H77" stroke="{cor}" stroke-width="5" stroke-linecap="round"/>',
    ]
    titulo = f'{a["nome"]} / {b["nome"]}'
    return Markup(f'<svg class="estandarte duplo" viewBox="0 0 80 100" role="img" aria-label="{titulo}">'
                  f'<title>{titulo}</title>{"".join(partes)}</svg>')


# ---------- estandarte (todas as cartas) ----------
# Pendurado no canto de cima à direita, desce do topo da carta (o pano sobe pela sangria).
# No alto, centralizado, o medalhão (círculo de elementos, ou o slot do item) com anel externo,
# entalhes e losangos; avançado (campo, retiro, runa), com a estrela rúnica no lugar do anel.
# Um círculo menor fica preso ao medalhão, embaixo à direita e por trás dele (coroa de único,
# ato da ação, ícone de campo/retiro, custo em moedas). Abaixo, a classe centralizada direto no
# pano; com 2 ou mais, menores, lado a lado. Sem medalhão (aliado comum): estandarte estreito
# só com a(s) classe(s), empilhadas.

COROA_ICONE = Path(__file__).resolve().parent.parent / "frames" / "icones" / "marcas" / "unico.svg"
PANO_LARGO, PANO_ESTREITO = 180, 120   # larguras do estandarte (dados.py corta a moldura por elas)


def _glifo_classe_em(s, cor, x, y, escala):
    return (f'<g transform="translate({_f(x - 40 * escala)} {_f(y - 43 * escala)}) scale({_f(escala)})">'
            f'{_glifo_classe(s, cor)}</g>')


def _classes_no_pano(classes, cor, cx, cy, k):
    """Glifo(s) de classe centrados em (cx, cy), na escala k do estandarte (80 x 100, centro 40,43).
    Uma classe: no centro. Duas ou mais: menores, cada uma para um lado."""
    if len(classes) == 1:
        return _glifo_classe_em(classes[0], cor, cx, cy, k)
    k2 = k * (0.8 if len(classes) == 2 else 0.6)
    passo = 66 * k2
    x0 = cx - passo * (len(classes) - 1) / 2
    return "".join(_glifo_classe_em(s, cor, x0 + i * passo, cy, k2) for i, s in enumerate(classes))


def _medalhao(interno, cor, cx, cy, avancado=False, detalhe=True):
    """Medalhão do estandarte: o conteúdo (SVG de 100 x 100) maior, num disco escuro. Com detalhe,
    anel externo fino, entalhes e 4 losangos; avançado, a estrela rúnica de 8 pontas no lugar."""
    r_ext = 60
    partes = []
    if avancado:
        def estrela(r1, r2):
            pts = []
            for i in range(16):
                x, y = _ponto(90 + i * 22.5, r1 if i % 2 == 0 else r2)
                pts.append(f"{_f(x - 50 + cx)},{_f(y - 50 + cy)}")
            return " ".join(pts)
        partes.append(f'<polygon class="pano-estrela" points="{estrela(74, 60)}" fill="{FUNDO}" stroke="{cor}"/>'
                      f'<polygon class="pano-estrela-filete" points="{estrela(68, 60)}" stroke="{cor}"/>'
                      f'<circle class="pano-anel-fino" cx="{cx}" cy="{cy}" r="{r_ext}" stroke="{cor}"/>')
    else:
        partes.append(f'<circle cx="{cx}" cy="{cy}" r="{r_ext + 2}" fill="{FUNDO}"/>')
        if detalhe:
            entalhes = []
            for i in range(24):
                if i % 6 == 0:
                    continue  # nos pontos cardeais ficam os losangos
                x0, y0 = _ponto(90 + i * 15, 54.5)
                x1, y1 = _ponto(90 + i * 15, 58)
                entalhes.append(f'M{_f(x0 - 50 + cx)} {_f(y0 - 50 + cy)} L{_f(x1 - 50 + cx)} {_f(y1 - 50 + cy)}')
            partes.append(f'<circle class="pano-anel-fino" cx="{cx}" cy="{cy}" r="{r_ext}" stroke="{cor}"/>'
                          f'<path class="pano-entalhes" d="{" ".join(entalhes)}" stroke="{cor}"/>')
            for a in (90, 0, 270, 180):
                x, y = _ponto(a, r_ext)
                x, y = x - 50 + cx, y - 50 + cy
                partes.append(f'<polygon class="pano-losango" points="{_f(x)},{_f(y - 6)} {_f(x + 5)},{_f(y)} '
                              f'{_f(x)},{_f(y + 6)} {_f(x - 5)},{_f(y)}" fill="{cor}"/>')
    tam = 112
    partes.append(f'<svg x="{_f(cx - tam / 2)}" y="{_f(cy - tam / 2)}" width="{tam}" height="{tam}" viewBox="0 0 100 100">'
                  f'{interno}</svg>')
    if detalhe and not avancado:
        partes.append(f'<circle class="pano-filete" cx="{cx}" cy="{cy}" r="40" stroke="{cor}"/>')
    return "".join(partes)


def _anexo(conteudo, cor, cx, cy):
    """Círculo menor preso ao medalhão, embaixo à direita (desenhado antes dele: fica atrás).
    O conteúdo é um SVG de 100 x 100."""
    x, y = cx + 78 * math.cos(math.radians(45)), cy + 78 * math.sin(math.radians(45))
    return (f'<circle class="pano-anel" cx="{_f(x)}" cy="{_f(y)}" r="24" stroke="{cor}"/>'
            f'<svg x="{_f(x - 16)}" y="{_f(y - 16)}" width="32" height="32" viewBox="0 0 100 100">{conteudo}</svg>')


def _corpo_svg(caminho):
    return re.search(r"<svg[^>]*>(.*)</svg>", _svg_do_arquivo(str(caminho), caminho.stat().st_mtime), re.S).group(1)


def anexo_coroa():
    return _corpo_svg(COROA_ICONE)


def anexo_ato(ato):
    texto = ROMANO_ANEXO.get(ato, str(ato))
    tam = 60 if len(texto) <= 2 else 46
    return (f'<text x="50" y="54" text-anchor="middle" dominant-baseline="central" font-family="Cinzel, serif" '
            f'font-weight="700" font-size="{tam}" fill="#efe6d2">{texto}</text>')


ROMANO_ANEXO = {1: "I", 2: "II", 3: "III"}


def anexo_icone(s):
    """Glifo creme de um símbolo (ícone de campo/retiro), ou a sigla."""
    caminho = s.get("icone_arquivo")
    if caminho and caminho.suffix == ".svg":
        return _corpo_svg(caminho)
    return (f'<text x="50" y="52" text-anchor="middle" dominant-baseline="central" font-family="Source Sans 3, sans-serif" '
            f'font-weight="700" font-size="40" fill="#efe6d2">{s["sigla"]}</text>')


def anexo_moedas(valor):
    return (f'<g opacity="0.45">{_corpo_svg(MOEDA_ICONE)}</g>'
            f'<text x="50" y="52" text-anchor="middle" dominant-baseline="central" font-family="Source Sans 3, sans-serif" '
            f'font-weight="800" font-size="62" fill="#f4f1ea" stroke="{FUNDO}" stroke-width="8" '
            f'stroke-linejoin="round" paint-order="stroke">{valor}</text>')


def interno_slot(s, cor):
    """Conteúdo do medalhão do item: o glifo do slot num círculo de 100 x 100."""
    caminho = s.get("icone_arquivo")
    if caminho and caminho.suffix == ".svg":
        glifo = f'<g transform="translate(19 19) scale(0.62)">{_corpo_svg(caminho)}</g>'
    else:
        glifo = (f'<text x="50" y="52" text-anchor="middle" dominant-baseline="central" font-family="Source Sans 3, sans-serif" '
                 f'font-weight="700" font-size="34" fill="#efe6d2">{s["sigla"]}</text>')
    return (f'<circle cx="50" cy="50" r="{R_ANEL + TRACO_ANEL / 2}" fill="{FUNDO}"/>'
            f'<circle cx="50" cy="50" r="{R_ANEL}" fill="none" stroke="{cor}" stroke-width="{TRACO_ANEL}"/>{glifo}')


def bandeira(cor, centro=None, anexo=None, classes=(), avancado=False, detalhe=True, titulo=""):
    """SVG do estandarte (Markup), ou None se não houver nada para pendurar nele.
    centro: SVG de 100 x 100 do medalhão; anexo: SVG de 100 x 100 do círculo preso a ele."""
    partes = []
    if centro:
        largura = PANO_LARGO
        cx, cy = largura / 2, 92
        if anexo:
            partes.append(_anexo(anexo, cor, cx, cy))
        partes.append(_medalhao(centro, cor, cx, cy, avancado, detalhe))
        fim = 266 if classes else 196   # onde as laterais do pano terminam e começa a ponta
        if classes:
            partes.append(_classes_no_pano(classes, cor, cx, 222, 1.4))
    elif classes:  # sem medalhão (aliado comum): estandarte estreito, classes empilhadas
        largura = PANO_ESTREITO
        if len(classes) == 1:
            fim = 160
            partes.append(_glifo_classe_em(classes[0], cor, largura / 2, 86, 1.5))
        else:
            passo, k = 86, 1.15
            fim = 66 + passo * (len(classes) - 1) + 50
            partes += [_glifo_classe_em(s, cor, largura / 2, 66 + i * passo, k) for i, s in enumerate(classes)]
    else:
        return None
    meio, ponta = largura / 2, fim + largura / 3
    pano = f"M0 -40 H{largura} V{fim} L{_f(meio)} {_f(ponta)} L0 {fim} Z"
    return Markup(
        f'<svg class="pj-bandeira" viewBox="0 0 {largura} {_f(ponta)}" width="{largura}" height="{_f(ponta)}" '
        f'role="img" aria-label="{titulo}"><title>{titulo}</title>'
        f'<path class="pano" d="{pano}" stroke="{cor}"/>{"".join(partes)}</svg>')


def bandeira_personagem(elementos, classes, unico, cor):
    nomes = [e["nome"] for e in elementos] + (["personagem único"] if unico else []) + [s["nome"] for s in classes]
    return bandeira(cor, circulo_elementos(elementos) if elementos else None,
                    anexo_coroa() if unico else None, classes, titulo=" · ".join(nomes))


# ---------- gemas lapidadas (personagem): estrela do custo e triângulo do nível ----------
# Mesmo detalhamento do hexágono de poder: uma faceta por aresta, sombreada pela direção
# da luz (de cima à esquerda), mesa central lisa com o valor, luz na mesa, reflexo, filete
# e contorno escuro. Pontos de cada forma no sentido horário na tela.

LUZ = (-0.6, -0.8)  # de cima à esquerda
ESTRELA = [(50, 4), (62.5, 34.5), (95, 37), (70, 58.5), (78, 91), (50, 73.5), (22, 91), (30, 58.5), (5, 37), (37.5, 34.5)]


def _escala(pontos, centro, fator):
    cx, cy = centro
    return [(cx + (x - cx) * fator, cy + (y - cy) * fator) for x, y in pontos]


def _gema_lapidada(pontos, centro, viewbox, valor, rotulo, classe, ident, mesa=0.5, brilho=None):
    n = len(pontos)
    interno = _escala(pontos, centro, mesa)
    facetas = []
    for k in range(n):
        (x0, y0), (x1, y1) = pontos[k], pontos[(k + 1) % n]
        nx, ny = y1 - y0, -(x1 - x0)  # normal para fora da aresta
        luz = (nx * LUZ[0] + ny * LUZ[1]) / math.hypot(nx, ny)
        mistura = (f"color-mix(in srgb, var(--prata) {round(100 - luz * 55)}%, white)" if luz > 0
                   else f"color-mix(in srgb, var(--prata) {round(100 + luz * 50)}%, black)")
        facetas.append(f'<polygon style="fill: {mistura}" points="{_pts([pontos[k], pontos[(k + 1) % n], interno[(k + 1) % n], interno[k]])}"/>')
    reflexo = f'<polygon class="reflexo" points="{_pts(brilho)}"/>' if brilho else ""
    w, h = viewbox
    return Markup(
        f'<svg class="gema gema-poder {classe}" viewBox="0 0 {w} {h}" role="img" aria-label="{rotulo}">'
        f'<title>{rotulo}</title>'
        f'<defs><radialGradient id="luz-{ident}" cx="35%" cy="28%" r="75%">'
        f'<stop offset="0" stop-color="#fff" stop-opacity="0.38"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>'
        f'</radialGradient></defs>'
        f'<polygon class="contorno-fundo" points="{_pts(pontos)}"/>'
        f'{"".join(facetas)}'
        f'<polygon class="mesa" points="{_pts(interno)}"/>'
        f'<polygon points="{_pts(interno)}" fill="url(#luz-{ident})"/>'
        f'{reflexo}'
        f'<polygon class="filete" points="{_pts(_escala(pontos, centro, 0.84))}"/>'
        f'<polygon class="contorno" points="{_pts(pontos)}"/>'
        f'<text x="{_f(centro[0])}" y="{_f(centro[1] + 2)}">{valor}</text></svg>')


def estrela_lapidada(valor, ident):
    return _gema_lapidada(ESTRELA, (50, 52), (100, 96), valor, f"{valor} estrelas", "estrela-lapidada",
                          f"estrela-{ident}", brilho=[(30, 40), (46, 22), (50, 30), (38, 44)])


def simbolo_quina(icone, rotulo, girar=0):
    """Ícone de evolução (divisas, giradas para apontar para a direita) ou de ascensão (estrela)
    para a quina de baixo à direita do personagem, na cor do texto que contrasta com o tema."""
    corpo = re.search(r"<svg[^>]*>(.*)</svg>", _svg_do_arquivo(str(icone), icone.stat().st_mtime), re.S).group(1)
    corpo = corpo.replace("#efe6d2", "currentColor")
    if girar:
        corpo = f'<g transform="rotate({girar} 50 50)">{corpo}</g>'
    return Markup(f'<svg class="quina-icone" viewBox="0 0 100 100" role="img" aria-label="{rotulo}">'
                  f'<title>{rotulo}</title>{corpo}</svg>')



# ---------- moldura do personagem: chanfros nas quinas, fina nas laterais, grossa nas quinas ----------

def _ponto_na_linha(pts, acum, dist):
    for i in range(1, len(pts)):
        if dist <= acum[i] + 1e-9:
            f = (dist - acum[i - 1]) / ((acum[i] - acum[i - 1]) or 1)
            return (pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f)
    return pts[-1]


def _contorno(pts, meias):
    """Polígono de uma linha de espessura variável (meia largura por vértice), juntas em quina viva."""
    def normal(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1
        return (-dy / n, dx / n)
    esq, dir_ = [], []
    for i, (x, y) in enumerate(pts):
        n1 = normal(pts[i - 1], pts[i]) if i > 0 else None
        n2 = normal(pts[i], pts[i + 1]) if i < len(pts) - 1 else None
        if n1 and n2:
            mx, my = n1[0] + n2[0], n1[1] + n2[1]
            m = math.hypot(mx, my) or 1
            mx, my = mx / m, my / m
            k = meias[i] / max(mx * n1[0] + my * n1[1], 0.2)
        else:
            mx, my = n1 or n2
            k = meias[i]
        esq.append((x + mx * k, y + my * k))
        dir_.append((x - mx * k, y - my * k))
    return "M" + " L".join(f"{_f(a)} {_f(b)}" for a, b in esq + dir_[::-1]) + " Z"


def linha_moldura(trechos, chanfro=18, fino=2.6, grosso=8, alcance=74):
    """Caminho SVG (polígonos cheios) dos trechos da moldura. Cada trecho é uma lista de
    (x, y, quina); nas quinas entra um chanfro de 45°, e a linha engrossa de `fino` nas
    laterais até `grosso` no chanfro, ao longo de `alcance` px de cada lado da quina."""
    caminhos = []
    for trecho in trechos:
        pts, quinas = [], []
        for i, (x, y, quina) in enumerate(trecho):
            if not quina:
                pts.append((x, y))
                continue
            (xa, ya, _), (xb, yb, _) = trecho[i - 1], trecho[i + 1]
            da, db = math.hypot(x - xa, y - ya), math.hypot(xb - x, yb - y)
            ch = min(chanfro, da * 0.8, db * 0.8)  # trecho curto (estandarte perto da quina): chanfro menor
            pts.append((x - (x - xa) / da * ch, y - (y - ya) / da * ch))
            pts.append((x + (xb - x) / db * ch, y + (yb - y) / db * ch))
            quinas.append(len(pts) - 2)  # o chanfro é o segmento que começa aqui
        acum = [0.0]
        for i in range(1, len(pts)):
            acum.append(acum[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
        centros = [(acum[q] + acum[q + 1]) / 2 for q in quinas]
        # vértices + pontos onde a espessura muda de inclinação (início do afinamento e meio do chanfro)
        marcas = set(acum)
        for sc in centros:
            marcas.update(v for v in (sc - alcance, sc, sc + alcance) if 0 < v < acum[-1])
        marcas = sorted(marcas)
        novos = [_ponto_na_linha(pts, acum, m) for m in marcas]
        def meia(m):
            perto = min((abs(m - sc) for sc in centros), default=alcance)
            return (fino + (grosso - fino) * max(0.0, 1 - perto / alcance)) / 2
        caminhos.append(_contorno(novos, [meia(m) for m in marcas]))
    return " ".join(caminhos)
