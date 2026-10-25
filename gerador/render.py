"""Preenche os templates de frames/ e exporta PNG e PDF com Playwright.

Usa o Edge ou o Chrome já instalados; se nenhum existir, cai no Chromium do
Playwright (instale com: python -m playwright install chromium).
"""

import html
import re
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup
from playwright.sync_api import sync_playwright

from .dados import FRAMES, ROMANOS, RAIZ, url_de

SAIDA = RAIZ / "out"
TEMP = SAIDA / ".tmp"

FOLHAS_ESTILO = ("carta.css", "frame.css", "layout.css")

LARGURA, ALTURA = 630, 880   # px da área de corte (10 px = 1 mm)
PX_POR_MM_CSS = 96 / 25.4    # 1 mm de impressão em px de CSS
ESCALA_IMPRESSAO = PX_POR_MM_CSS / 10

# Folha A4 de impressão caseira: 3 x 3 cartas, centralizadas
A4 = (210, 297)
GRADE = (3, 3)


# ---------- marcação simples nos textos ----------
# **negrito**, *itálico*, quebra de linha = novo parágrafo

def _inline(texto):
    t = html.escape(texto)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
    return t


def marcacao(texto):
    paragrafos = [p.strip() for p in str(texto or "").split("\n") if p.strip()]
    return Markup("".join(f"<p>{_inline(p)}</p>" for p in paragrafos))


def marcacao_linha(texto):
    return Markup(_inline(str(texto or "")).replace("\n", "<br>"))


def romano(n):
    return ROMANOS.get(n, str(n))


def _ambiente():
    env = Environment(loader=FileSystemLoader(FRAMES), autoescape=True,
                      undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    env.filters.update(marcacao=marcacao, marcacao_linha=marcacao_linha, romano=romano)
    return env


# Diminui a fonte de nomes e textos longos até caberem. O que não couber nem no
# tamanho mínimo fica marcado e é reportado como aviso.
AJUSTE_JS = """
window.__avisos = [];
(async () => {
  await document.fonts.ready;
  await Promise.all([...document.images].map(i => i.decode().catch(() => {})));
  const aviso = (el, o) => {
    el.classList.add('erro-ajuste');
    window.__avisos.push([el.closest('.carta').dataset.id, o]);
  };
  // texto do tipo: margem simétrica do tamanho do que ocupa as pontas da barra
  // (estandarte à esquerda, símbolos à direita), para continuar centralizado
  for (const el of document.querySelectorAll('.tipo-texto')) {
    const barra = el.parentElement;
    const dir = barra.querySelector('.sub-simbolos');
    const esq = Math.max(barra.classList.contains('com-classe') ? 64 : 0, 24);
    const direita = Math.max(dir ? dir.offsetWidth + 16 : 0, 24);
    const simetrico = Math.max(esq, direita);
    el.style.padding = '0 ' + simetrico + 'px';
    // se não cabe centralizado, usa todo o espaço livre entre as pontas
    if (el.scrollWidth > el.clientWidth + 0.5) el.style.padding = '0 ' + direita + 'px 0 ' + esq + 'px';
  }
  for (const el of document.querySelectorAll('.ajustar-largura')) {
    let fs = parseFloat(getComputedStyle(el).fontSize);
    const min = fs * 0.55;
    while (el.scrollWidth > el.clientWidth + 0.5 && fs > min) { fs -= 0.5; el.style.fontSize = fs + 'px'; }
    if (el.scrollWidth > el.clientWidth + 0.5) aviso(el, 'texto de uma linha não coube: ' + el.textContent.trim());
  }
  // texto em pé (raça do personagem): mesma ideia, medindo a altura
  for (const el of document.querySelectorAll('.ajustar-vertical')) {
    let fs = parseFloat(getComputedStyle(el).fontSize);
    const min = fs * 0.55;
    while (el.scrollHeight > el.clientHeight + 0.5 && fs > min) { fs -= 0.5; el.style.fontSize = fs + 'px'; }
    if (el.scrollHeight > el.clientHeight + 0.5) aviso(el, 'texto vertical não coube: ' + el.textContent.trim());
  }
  // ambientação opcional: só fica se o efeito couber inteiro com ela no tamanho normal
  for (const a of document.querySelectorAll('.ambientacao.opcional')) {
    const e = a.parentElement.querySelector('.efeito');
    if (e && e.scrollHeight > e.clientHeight + 0.5) a.remove();
  }
  for (const el of document.querySelectorAll('.ajustar-altura')) {
    let fs = parseFloat(getComputedStyle(el).fontSize);
    while (el.scrollHeight > el.clientHeight + 0.5 && fs > 13) { fs -= 0.5; el.style.fontSize = fs + 'px'; }
    if (el.scrollHeight > el.clientHeight + 0.5) aviso(el, 'texto de efeito não coube na caixa');
    else if (fs < 16) window.__avisos.push([el.closest('.carta').dataset.id, 'texto de efeito longo, fonte reduzida para ' + fs + 'px']);
  }
  document.body.dataset.pronto = '1';
})();
"""


class Renderizador:
    """Abre o navegador uma vez e renderiza quantas cartas forem pedidas."""

    def __init__(self, escala=2.0, sangria_mm=0.0):
        self.env = _ambiente()
        self.escala = escala
        self.sangria = round(sangria_mm * 10)
        self._pw = None
        self.navegador = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        for canal in ("msedge", "chrome", None):
            try:
                self.navegador = self._pw.chromium.launch(channel=canal) if canal else self._pw.chromium.launch()
                break
            except Exception:
                continue
        if not self.navegador:
            raise RuntimeError("Nenhum navegador encontrado. Rode: python -m playwright install chromium")
        TEMP.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, *_):
        if self.navegador:
            self.navegador.close()
        self._pw.stop()
        shutil.rmtree(TEMP, ignore_errors=True)

    # ----- montagem do HTML -----

    def carta_html(self, template, c, ident, sangria):
        return self.env.get_template(f"{template}.html").render(c=c, id=ident, sangria=sangria)

    def pagina(self, corpo, estilo=""):
        return (
            '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            + "".join(f'<link rel="stylesheet" href="{url_de(FRAMES / css)}">' for css in FOLHAS_ESTILO) +
            f"<style>body{{background:transparent}}{estilo}</style></head>"
            f"<body>{corpo}<script>{AJUSTE_JS}</script></body></html>"
        )

    def _abrir(self, html_pagina, nome, largura=LARGURA, altura=ALTURA, escala=1):
        arquivo = TEMP / f"{nome}.html"
        arquivo.write_text(html_pagina, encoding="utf-8")
        pagina = self.navegador.new_page(viewport={"width": largura, "height": altura},
                                         device_scale_factor=escala)
        pagina.goto(arquivo.as_uri())
        pagina.wait_for_selector("body[data-pronto='1']", timeout=30000)
        avisos = pagina.evaluate("window.__avisos")
        return pagina, avisos

    # ----- saídas -----

    def png(self, faces, destino):
        """faces: [(template, dados, id)]. Um PNG por face em destino/."""
        destino.mkdir(parents=True, exist_ok=True)
        corpo = "".join(self.carta_html(t, c, i, self.sangria) for t, c, i in faces)
        pagina, avisos = self._abrir(self.pagina(corpo, "body{display:flex;flex-direction:column;gap:20px}"),
                                     "png", largura=LARGURA + 2 * self.sangria,
                                     altura=ALTURA + 2 * self.sangria, escala=self.escala)
        arquivos = []
        for el in pagina.query_selector_all(".carta"):
            arq = destino / f"{el.get_attribute('data-id')}.png"
            el.screenshot(path=str(arq), omit_background=True)
            arquivos.append(arq)
        pagina.close()
        return arquivos, avisos

    def pdf_individual(self, faces, destino):
        """Um PDF por face, no tamanho real da carta (mais a sangria, se houver)."""
        destino.mkdir(parents=True, exist_ok=True)
        larg_mm = 63 + 2 * self.sangria / 10
        alt_mm = 88 + 2 * self.sangria / 10
        estilo = (f"@page{{size:{larg_mm}mm {alt_mm}mm;margin:0}}"
                  f".pg{{width:{larg_mm}mm;height:{alt_mm}mm;overflow:hidden}}"
                  f".pg .carta{{transform:scale({ESCALA_IMPRESSAO});transform-origin:0 0;border-radius:0}}")
        arquivos, avisos = [], []
        for t, c, i in faces:
            corpo = f'<div class="pg">{self.carta_html(t, c, i, self.sangria)}</div>'
            pagina, av = self._abrir(self.pagina(corpo, estilo), f"pdf-{i}")
            arq = destino / f"{i}.pdf"
            pagina.pdf(path=str(arq), width=f"{larg_mm}mm", height=f"{alt_mm}mm", print_background=True)
            pagina.close()
            arquivos.append(arq)
            avisos += av
        return arquivos, avisos

    def folha_a4(self, faces, arquivo):
        """Todas as faces em folhas A4, 3 x 3, com marcas de corte. Sem sangria."""
        cols, lins = GRADE
        margem_x = (A4[0] - cols * 63) / 2
        margem_y = (A4[1] - lins * 88) / 2
        por_folha = cols * lins

        marcas = []
        for k in range(cols + 1):
            x = margem_x + k * 63
            marcas.append(f'<i style="left:{x}mm;top:0;width:0.2mm;height:{margem_y - 2}mm"></i>')
            marcas.append(f'<i style="left:{x}mm;bottom:0;width:0.2mm;height:{margem_y - 2}mm"></i>')
        for k in range(lins + 1):
            y = margem_y + k * 88
            marcas.append(f'<i style="top:{y}mm;left:0;height:0.2mm;width:{margem_x - 2}mm"></i>')
            marcas.append(f'<i style="top:{y}mm;right:0;height:0.2mm;width:{margem_x - 2}mm"></i>')
        marcas = "".join(marcas)

        folhas = []
        for ini in range(0, len(faces), por_folha):
            cartas = []
            for n, (t, c, i) in enumerate(faces[ini:ini + por_folha]):
                x = margem_x + (n % cols) * 63
                y = margem_y + (n // cols) * 88
                cartas.append(f'<div class="slot" style="left:{x}mm;top:{y}mm">'
                              f'{self.carta_html(t, c, i, 0)}</div>')
            folhas.append(f'<section class="a4">{marcas}{"".join(cartas)}</section>')

        estilo = (f"@page{{size:A4;margin:0}}"
                  f".a4{{position:relative;width:{A4[0]}mm;height:{A4[1]}mm;overflow:hidden;break-after:page;background:#fff}}"
                  f".a4 i{{position:absolute;background:#000}}"
                  f".slot{{position:absolute;width:63mm;height:88mm;overflow:hidden}}"
                  f".slot .carta{{transform:scale({ESCALA_IMPRESSAO});transform-origin:0 0;border-radius:0}}")
        pagina, avisos = self._abrir(self.pagina("".join(folhas), estilo), "folha")
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        pagina.pdf(path=str(arquivo), format="A4", print_background=True)
        pagina.close()
        return arquivo, avisos
