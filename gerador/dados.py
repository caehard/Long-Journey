"""Leitura, validação e normalização dos JSON de cartas.

Cada arquivo em cards/ vira uma ou mais "faces" (personagem único tem duas).
Uma face é um dict pronto para o template do frame correspondente.
"""

import json
import re
import unicodedata
from pathlib import Path

from .simbolos import PANO_ESTREITO, PANO_LARGO, anexo_icone, medalhao_solto, anexo_moedas, bandeira, bandeira_personagem, interno_slot, circulo_elementos, estrela_lapidada, linha_moldura, simbolo_quina, circulo_local, circulo_runa_avancada, hexagono_poder, medalhao_slot, moeda_custo, circulo_texto, estandarte, estandarte_duplo, selo_chave, tema

RAIZ = Path(__file__).resolve().parent.parent
FRAMES = RAIZ / "frames"
CARTAS = RAIZ / "cards"

ROMANOS = {1: "I", 2: "II", 3: "III"}

# Por padrão as páginas apontam para os arquivos no disco (file://). O app de
# teste troca isto por "/raiz/" para servir tudo pelo servidor local.
URL_BASE = None


def url_de(caminho):
    caminho = Path(caminho).resolve()
    if URL_BASE is None:
        return caminho.as_uri()
    return URL_BASE + caminho.relative_to(RAIZ).as_posix()

# campos aceitos por tipo; o resto gera aviso, para pegar erro de digitação
CAMPOS_COMUNS = {"tipo", "nome", "estrelas", "numero", "texto", "ambientacao",
                 "arte", "arte_posicao", "arte_zoom", "notas"}
CAMPOS = {
    "acao": {"ato_minimo", "elementos", "custo_carga", "classes", "classe_dupla", "subtipos"},
    "personagem": {"ficha", "elemento", "classes", "classe_dupla", "raca", "cla", "funcao", "poder",
                   "enredo", "frente", "verso"},
    "item": {"ficha", "slot", "custo_moedas", "ato_minimo"},
    "campo": {"elemento", "avancado", "ato_minimo"},
    "retiro": {"elemento", "avancado", "ato_minimo"},
    "runa": {"elemento", "avancado", "ficha", "ato_minimo"},
    "quest": {"atos", "recompensa"},
}

# campos que o livro de regras não permite naquele tipo: viram erro, com o motivo
FICHA_PROIBIDA = "só aliado comum, item comum e runa básica são fichas (livro, seções 6 e 10)"
PROIBIDOS = {
    "acao": {"ficha": FICHA_PROIBIDA},
    "item": {"classes": "classe é impressa só em ações e personagens (livro, glossário)",
             "classe_dupla": "item não tem classe"},
    "campo": {"ficha": FICHA_PROIBIDA},
    "retiro": {"ficha": FICHA_PROIBIDA},
    "quest": {"ficha": FICHA_PROIBIDA,
              "ato": "a pilha de quests é embaralhada; a quest não tem ato fixo (livro, seções 4 e 11)",
              "niveis": "a quest dá níveis iguais ao ato em que é concluída (livro, seção 11)"},
}
CAMPOS_FACE = {"nome", "arte", "arte_posicao", "arte_zoom", "texto", "ambientacao", "poder",
               "classes", "raca", "cla", "funcao",
               "evolui", "evolui_nivel", "ascensao_nivel", "ascende", "classe_dupla"}

NOMES_LOCAL = {"campo": "Campo de batalha", "retiro": "Retiro", "runa": "Runa"}


class ErroCarta(Exception):
    pass


def slug(texto):
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


def carregar_config():
    return json.loads((FRAMES / "config.json").read_text(encoding="utf-8"))


# categoria do config -> pasta em frames/icones/
PASTAS_ICONES = {"subtipos_acao": "subtipos", "palavras_chave": "palavras-chave"}


def _icone(categoria, chave):
    for ext in ("svg", "png", "webp"):
        caminho = FRAMES / "icones" / categoria / f"{chave}.{ext}"
        if caminho.exists():
            return caminho
    return None


def simbolo(cfg, categoria, bruto):
    """'Escudo 2' -> {nome: 'Escudo', sigla: 'Esc', valor: '2', icone: ...}"""
    m = re.match(r"^(.*?)\s+(\d+|X)$", str(bruto).strip())
    nome_bruto, valor = (m.group(1), m.group(2)) if m else (str(bruto).strip(), None)
    chave = slug(nome_bruto)
    icone = _icone(PASTAS_ICONES.get(categoria, categoria), chave)
    info = cfg.get(categoria, {}).get(chave, {})
    nome = info.get("nome") or nome_bruto[:1].upper() + nome_bruto[1:]
    return {
        "chave": chave,
        "nome": nome,
        "sigla": info.get("sigla") or nome[:3].capitalize(),
        "cor": info.get("cor"),
        "valor": valor,
        "icone_arquivo": icone,
        "icone": url_de(icone) if icone else None,
        "conhecido": bool(info),
    }


class Validador:
    def __init__(self, origem):
        self.origem = origem
        self.erros = []
        self.avisos = []

    def erro(self, msg):
        self.erros.append(msg)

    def aviso(self, msg):
        self.avisos.append(msg)

    def inteiro(self, d, campo, minimo=None, maximo=None, obrigatorio=True):
        v = d.get(campo)
        if v is None:
            if obrigatorio:
                self.erro(f'falta o campo "{campo}"')
            return None
        if isinstance(v, bool) or not isinstance(v, int):
            if v == "X":  # valor ainda não definido, aceito no protótipo
                return v
            self.erro(f'"{campo}" deve ser um número inteiro (está {v!r})')
            return None
        if (minimo is not None and v < minimo) or (maximo is not None and v > maximo):
            self.erro(f'"{campo}" deve estar entre {minimo} e {maximo} (está {v})')
        return v


def _lista(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _elementos(d, cfg, val, campo, maximo):
    brutos = _lista(d.get(campo))
    vistos, saida = set(), []
    for b in brutos:
        s = simbolo(cfg, "elementos", b)
        if s["chave"] in vistos:
            val.erro(f'elemento duplicado: "{b}" (não existe carta com elemento repetido)')
            continue
        vistos.add(s["chave"])
        if not s["conhecido"]:
            conhecidos = ", ".join(cfg["elementos"])
            val.erro(f'elemento desconhecido: "{b}". Cadastre em frames/config.json (hoje: {conhecidos})')
            s["cor"] = "#888"
        saida.append(s)
    if len(saida) > maximo:
        val.erro(f"no máximo {maximo} elemento(s) neste tipo de carta (tem {len(saida)})")
    return saida


def _simbolos(d, cfg, val, campo, categoria, restrito=False):
    saida, vistos = [], set()
    for b in _lista(d.get(campo)):
        s = simbolo(cfg, categoria, b)
        if s["chave"] in vistos:
            val.aviso(f'"{b}" repetido em "{campo}"')
            continue
        vistos.add(s["chave"])
        if restrito and not s["conhecido"]:
            val.erro(f'"{b}" não é um valor válido de "{campo}" (válidos: {", ".join(cfg[categoria])})')
            continue
        saida.append(s)
    return saida


def _arte(d, val):
    caminho = d.get("arte")
    if not caminho:
        return None
    p = (RAIZ / caminho) if not Path(caminho).is_absolute() else Path(caminho)
    if not p.exists():
        val.aviso(f"arte não encontrada: {caminho} (usando espaço reservado)")
        return None
    return url_de(p)


def _base(d, cfg, val, origem):
    nome = (d.get("nome") or "").strip()
    if not nome:
        val.erro('falta o campo "nome"')
    ficha = bool(d.get("ficha"))
    estrelas = None
    if not ficha:
        estrelas = val.inteiro(d, "estrelas", 0)
    return {
        "id": origem.stem,
        "tipo": d.get("tipo"),
        "nome": nome,
        "ficha": ficha,
        "estrelas": estrelas,
        "numero": d.get("numero"),
        "texto": d.get("texto", ""),
        "ambientacao": d.get("ambientacao", ""),
        "arte_url": _arte(d, val),
        "arte_posicao": d.get("arte_posicao"),
        "arte_zoom": d.get("arte_zoom"),
        "classes_s": [],
        "dupla": False,
        "sem_estrela": False,
    }


def _sem_acento(texto):
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()


# Grade dos selos de palavra-chave, ao lado e acima do poder (fileira 0 = a do poder).
# Ordem: 1ª espelhando o poder, 2ª acima do poder, 3ª espelhando a 2ª, 4ª acima da 2ª,
# 5ª espelhando a 4ª. Com estandarte de classe, a posição esquerda da fileira 2 fica sob ele.
# colmeia de selos à direita do texto (x, y do canto de cima de cada selo de 58 x 64 px),
# encostados, em ordem de leitura: 2 em cima, 2 no meio (deslocados meio selo), 1 embaixo.
# O hexágono ocupa 90% da largura do selo: passo horizontal 52,2 px e vertical 1,5 x raio.
POSICOES_CHAVES = [(0, 0), (52.2, 0), (26.1, 45.4), (78.3, 45.4), (52.2, 90.8)]

# medidas do frame do personagem (as mesmas de personagem.css), para cortar a moldura
PJ_NOME_TOPO, PJ_NOME_ALTURA = 505, 54       # barra do nome
PJ_PANO_DIREITA = 36                         # estandarte: distância da borda direita
PJ_NOME_TOPO_QUEST = 385                     # na quest o nome sobe para os atos caberem
PJ_NOME_TOPO_RUNA = 58                       # na runa o nome fica no alto
PJ_RUNA_BASE, PJ_RUNA_VAO = 716, 84          # runa: linha de baixo mais alta, aberta em volta do elemento
PJ_CAIXA_ESQ, PJ_CAIXA_TOPO = 234, 700       # caixa de evolução/ascensão (canto de baixo à esquerda)
PJ_CAIXA_INCL, PJ_CAIXA_ALTURA = 60, 180     # borda esquerda inclinada: 60 px mais para dentro no topo


def _chaves_no_texto(c, texto, cfg, val):
    """Acha no texto as palavras-chave que têm ícone ("Escudo 2", "elusivo X"...), na ordem em
    que aparecem, e as distribui na colmeia ao lado do texto (POSICOES_CHAVES)."""
    plano = _sem_acento(texto)
    achadas = []
    for chave, info in cfg.get("palavras_chave", {}).items():
        nome = _sem_acento(info.get("nome", chave))
        m = re.search(rf"(?<![a-z0-9]){re.escape(nome)}(?:\s+(\d+|x))?(?![a-z0-9])", plano)
        if not m:
            continue
        s = simbolo(cfg, "palavras_chave", chave + (f" {m.group(1).upper()}" if m.group(1) else ""))
        if s["icone_arquivo"] and s["icone_arquivo"].suffix == ".svg":
            achadas.append((m.start(), s))
    selos = [selo_chave(s) for _, s in sorted(achadas, key=lambda x: x[0])]
    if len(selos) > len(POSICOES_CHAVES):
        val.aviso(f"{len(selos)} palavras-chave com ícone; só cabem {len(POSICOES_CHAVES)} (as primeiras do texto)")
    c["chaves_pos"] = [(svg, x, y) for svg, (x, y) in zip(selos, POSICOES_CHAVES)]


def _raca_e_pano(c, f, unico):
    """Texto vertical do canto de cima à esquerda (raça; clã e função na linha de dentro, ou a
    raça sozinha nela) e o estandarte (elemento, coroa de único, classe)."""
    c["linhas_raca"] = [x for x in (f.get("raca"), " · ".join(f.get(k) for k in ("cla", "funcao") if f.get(k))) if x]
    c["bandeira"] = bandeira_personagem(c["elementos_s"], c["classes_s"], unico, c["tema"]["a"])
    largura_pano = PANO_LARGO if (c["elementos_s"] or unico) else PANO_ESTREITO
    c["pano_largura"] = largura_pano if c["bandeira"] else None


def _cortes_moldura(c):
    """Trechos da moldura do personagem (em px da carta), com chanfro nas quinas e mais grossa
    perto delas (simbolos.linha_moldura). A linha não passa por baixo do estandarte, da barra
    do nome nem da caixa de evolução: ela é interrompida nesses lugares (não é só escondida),
    para nada aparecer atrás do que é transparente."""
    e, d, t, b = 22.5, 630 - 22.5, 22.5, 880 - 96 - 2.5   # centro da linha
    runa = c.get("runa_medalhao")
    if runa:
        b = PJ_RUNA_BASE
    pano = c.get("pano_largura")
    pano1 = 630 - PJ_PANO_DIREITA
    # a base para na borda inclinada da caixa, na altura da linha
    caixa_x = PJ_CAIXA_ESQ + PJ_CAIXA_INCL * (1 - (b - PJ_CAIXA_TOPO) / PJ_CAIXA_ALTURA)
    QUEBRA = None
    # volta completa a partir do nome, descendo pela esquerda; QUEBRA = trecho interrompido
    nome_topo = c.get("nome_topo", PJ_NOME_TOPO)
    volta = [(e, nome_topo + PJ_NOME_ALTURA, False), (e, b, True)]
    if c.get("criterio_rotulo"):
        volta += [(caixa_x, b, False), QUEBRA, (d, PJ_CAIXA_TOPO, False)]
    elif runa:
        volta += [(315 - PJ_RUNA_VAO, b, False), QUEBRA, (315 + PJ_RUNA_VAO, b, False), (d, b, True)]
    else:
        volta += [(d, b, True)]
    volta += [(d, t, True)]
    if pano:
        volta += [(pano1, t, False), QUEBRA, (pano1 - pano, t, False)]
    volta += [(e, t, True), (e, nome_topo, False)]
    trechos, atual = [], []
    for ponto in volta:
        if ponto is QUEBRA:
            trechos.append(atual)
            atual = []
        else:
            atual.append(ponto)
    trechos.append(atual)
    c["moldura_caminho"] = linha_moldura(trechos)


def _com_elementos(c, elementos):
    c["elementos_s"] = elementos
    c["circulo"] = circulo_elementos(elementos, c.get("custo_carga"))
    c["tinta"] = elementos[0]["cor"] if elementos else "#3a4258"
    c["tema"] = tema(elementos)
    return c


def _com_classes(c, d, cfg, val):
    """Com exatamente 2 classes, um estandarte partido ao meio (desligue com "classe_dupla": false)."""
    c["classes_s"] = _simbolos(d, cfg, val, "classes", "classes")
    c["dupla"] = len(c["classes_s"]) == 2 and d.get("classe_dupla", True) is not False
    return c


def _estandartes(c):
    """Desenha os estandartes na cor do tema (precisa de classes e elementos já lidos)."""
    cor = c["tema"]["a"]  # o estandarte fica à esquerda: pega a primeira cor
    c["classe_dupla"] = estandarte_duplo(*c["classes_s"], cor=cor) if c.get("dupla") else None
    c["classes_svg"] = [(s, estandarte(s, cor)) for s in c.get("classes_s", [])]


def _acao(d, cfg, val, origem):
    c = _base(d, cfg, val, origem)
    c["ato_minimo"] = val.inteiro(d, "ato_minimo", 1, 3, obrigatorio=False) or 1
    c["custo_carga"] = val.inteiro(d, "custo_carga", 0, obrigatorio=False) or 0
    _com_classes(c, d, cfg, val)
    c["subtipos_s"] = _simbolos(d, cfg, val, "subtipos", "subtipos_acao", restrito=True)
    _com_elementos(c, _elementos(d, cfg, val, "elementos", 3))
    # estandarte: elementos (com o custo de carga por cima) e a classe embaixo; o ato mínimo
    # fica no pentágono colado ao nome (carta.html)
    _pano(c, ["Ação", " · ".join(x["nome"] for x in c["subtipos_s"])],
          c["circulo"], None, c["classes_s"])
    return [("acao", c, "")]


def _personagem(d, cfg, val, origem):
    """Personagem único: duas faces (base e evoluída) e 1 elemento (livro, seções 3, 10 e 12).
    Ficha = aliado comum: uma face, sem elemento, nível, enredo nem estrelas (livro, seção 10)."""
    if d.get("ficha"):
        for k, motivo in (("elemento", "nunca tem elemento"), ("enredo", "enredo é do personagem principal"),
                          ("frente", "tem uma face só"), ("verso", "tem uma face só")):
            if k in d:
                val.erro(f'aliado comum (ficha) não tem "{k}": {motivo} (livro, seção 10)')
        c = _base(d, cfg, val, origem)
        _com_classes(c, d, cfg, val)
        _com_elementos(c, [])
        c.update(poder=val.inteiro(d, "poder", 0), marca_unico=None,
                 criterio=None, criterio_rotulo=None, criterio_nivel=None, rodape_extra="aliado comum")
        c["linha_tipo"] = " · ".join(d.get(k) for k in ("raca", "cla", "funcao") if d.get(k)) or "Aliado comum"
        c["poder_svg"] = hexagono_poder(c["poder"]) if c["poder"] is not None else None
        _chaves_no_texto(c, c["texto"], cfg, val)
        _raca_e_pano(c, d, unico=False)
        if not d.get("raca"):
            val.aviso("aliado comum sempre tem raça (livro, seção 10)")
        return [("personagem", c, "")]

    if not isinstance(d.get("frente"), dict) or not isinstance(d.get("verso"), dict):
        val.erro('personagem único tem duas faces: faltam "frente" e/ou "verso" (livro, seção 12)')
        return []
    if "poder" in d:
        val.aviso('"poder" fica em cada face ("frente" e "verso")')

    marca_unico = dict(simbolo(cfg, "marcas", "unico"), nome="Personagem único")
    faces = []
    for lado in ("frente", "verso"):
        face = d[lado]
        for k in face:
            if k not in CAMPOS_FACE:
                val.aviso(f'campo desconhecido em "{lado}": "{k}"')
        f = {**d, **face}  # a face herda o que é comum e pode sobrescrever
        f.pop("frente", None)
        f.pop("verso", None)
        c = _base(f, cfg, val, origem)
        _com_classes(c, f, cfg, val)
        elementos = _elementos(f, cfg, val, "elemento", 1)
        if not elementos and lado == "frente":
            val.erro('falta o campo "elemento": o personagem único tem 1 elemento, que gera a runa dele (livro, seção 4)')
        _com_elementos(c, elementos)
        c["poder"] = val.inteiro(f, "poder", 0)
        enredo = val.inteiro(f, "enredo", 0, obrigatorio=False)
        if lado == "frente" and enredo not in (None, 5):
            val.aviso(f"enredo {enredo}: todo personagem tem enredo 5 e ele não aparece na carta; "
                      "se este muda o enredo, escreva isso no texto")
        c["marca_unico"] = marca_unico
        c["poder_svg"] = hexagono_poder(c["poder"]) if c["poder"] is not None else None
        _chaves_no_texto(c, c["texto"], cfg, val)
        _raca_e_pano(c, f, unico=True)
        c["lado"] = lado

        # caixa de evolução/ascensão perto da base: nível mínimo no triângulo + condição
        if lado == "verso":
            n = val.inteiro(f, "ascensao_nivel")
            if isinstance(n, int) and not 6 <= n <= 11:
                val.aviso(f"ascensao_nivel {n} fora da faixa do livro (6 a 11)")
            c["criterio_rotulo"], c["criterio"], c["criterio_nivel"] = "Ascensão", f.get("ascende", ""), n
        else:
            n = val.inteiro(f, "evolui_nivel", 0, obrigatorio=False)
            if n is None:
                val.aviso('falta "evolui_nivel" na frente: o nível mínimo para evoluir (livro, seção 12)')
            c["criterio_rotulo"], c["criterio"], c["criterio_nivel"] = "Evolução", f.get("evolui", ""), n
        # quina de baixo à direita: ícone de evolução (setas para a direita) ou de ascensão.
        # O nível mínimo (evolui_nivel / ascensao_nivel) continua validado, mas não aparece na carta.
        icone = simbolo(cfg, "marcas", "ascensao" if lado == "verso" else "evolucao")["icone_arquivo"]
        c["quina_svg"] = (simbolo_quina(icone, c["criterio_rotulo"], girar=0 if lado == "verso" else 90)
                          if icone else None)
        c["linha_tipo"] = " · ".join(f.get(k) for k in ("raca", "cla", "funcao") if f.get(k)) or "Personagem"
        c["rodape_extra"] = {"frente": "forma base", "verso": "forma evoluída"}[lado]
        faces.append(("personagem", c, f"-{lado}"))
    return faces


def _pano(c, linhas, centro=None, anexo=None, classes=(), avancado=False, detalhe=True,
          segundo=None, segundo_avancado=False, nome_segundo=""):
    """Layout novo (frames/carta.html): texto vertical do canto de cima à esquerda e estandarte."""
    c["linhas_raca"] = [x for x in linhas if x]
    nomes = [e["nome"] for e in c.get("elementos_s", [])] + [s["nome"] for s in classes] + ([nome_segundo] if nome_segundo else [])
    c["bandeira"] = bandeira(c["tema"]["a"], centro, anexo, classes, avancado, detalhe, " · ".join(nomes),
                             segundo, segundo_avancado)
    c["pano_largura"] = (PANO_LARGO if centro else PANO_ESTREITO) if c["bandeira"] else None


def _layout(c):
    """Completa o que o frame comum (carta.html) usa e cada tipo não preencheu."""
    for k, v in (("linhas_raca", []), ("bandeira", None), ("pano_largura", None), ("poder_svg", None),
                 ("chaves_pos", []), ("criterio_rotulo", None), ("quina_svg", None), ("atos", None),
                 ("recompensa", ""), ("lado", ""), ("sem_texto", False), ("ato_minimo", None),
                 ("runa_medalhao", None)):
        c.setdefault(k, v)
    # só o personagem único tem a estrela embaixo à esquerda; nos outros ela fica no centro
    c["base_centro"] = not (c["tipo"] == "personagem" and not c["ficha"])
    _cortes_moldura(c)
    c["estrela_svg"] = (estrela_lapidada(c["estrelas"], f"{c['id']}{c['lado']}")
                        if c.get("estrelas") is not None and not c["ficha"] else None)


def _item(d, cfg, val, origem):
    c = _base(d, cfg, val, origem)
    if not d.get("slot"):
        val.erro(f'falta o campo "slot" (válidos: {", ".join(cfg["slots"])})')
        c["slot_s"] = simbolo(cfg, "slots", "?")
    else:
        slots = _simbolos(d, cfg, val, "slot", "slots", restrito=True)
        c["slot_s"] = slots[0] if slots else simbolo(cfg, "slots", d["slot"])
    _com_elementos(c, [])
    c["ato_minimo"] = val.inteiro(d, "ato_minimo", 1, 3, obrigatorio=False)
    # custo em moedas (comprar no mercado) no lugar dos elementos; sem custo, sem círculo,
    # porque o item também pode entrar em jogo por outros efeitos
    c["custo_moedas"] = val.inteiro(d, "custo_moedas", 0, obrigatorio=False)
    c["circulo"] = moeda_custo(c["custo_moedas"]) if c["custo_moedas"] is not None else ""
    c["medalhao"] = medalhao_slot(c["slot_s"], lendario=not c["ficha"])
    # estandarte: o slot no medalhão (comum, sem os detalhes), o custo em moedas preso a ele
    _pano(c, ["Item comum" if c["ficha"] else "Item", c["slot_s"]["nome"]],
          interno_slot(c["slot_s"], c["tema"]["a"]),
          anexo_moedas(c["custo_moedas"]) if c["custo_moedas"] is not None else None,
          detalhe=not c["ficha"])
    return [("item", c, "")]


def _local(d, cfg, val, origem):
    c = _base(d, cfg, val, origem)
    elementos = _elementos(d, cfg, val, "elemento", 1)
    if not elementos:
        val.erro('falta o campo "elemento" (campo, retiro e runa sempre fornecem uma runa)')
    _com_elementos(c, elementos)
    c["ato_minimo"] = val.inteiro(d, "ato_minimo", 1, 3, obrigatorio=False)
    c["avancado"] = bool(d.get("avancado"))
    c["linha_tipo"] = f'{NOMES_LOCAL[d["tipo"]]} · {"Avançado" if c["avancado"] else "Básico"}'
    if d["tipo"] == "runa":
        c["linha_tipo"] = c["linha_tipo"].replace("Avançado", "Avançada").replace("Básico", "Básica")
        if not c["avancado"] and not c["ficha"]:
            val.erro('runa básica é sempre ficha (livro, seção 6): use "ficha": true, ou marque "avancado"')
        if c["avancado"] and c["ficha"]:
            val.erro("runa avançada vem do deck de Eventos e não é ficha (livro, seção 6)")
        # avançada: moldura rúnica em volta do elemento (no lugar do "Av") e caixa de texto;
        # básica: só nome, elemento e arte
        if c["avancado"]:
            c["circulo"] = circulo_runa_avancada(elementos)
            if not c["texto"].strip():
                val.aviso("runa avançada sem texto: o efeito dela vai na caixa de texto")
        elif c["texto"].strip() or c["ambientacao"].strip():
            val.aviso("runa básica não tem caixa de texto: texto e ambientação não aparecem")
        if not c["avancado"]:
            c["sem_texto"] = True
        # sem estandarte e sem texto vertical: o nome sobe e o elemento desce para o centro de
        # baixo, sobre a linha da moldura; a estrela rúnica em volta é o que diz "avançada"
        c["nome_topo"] = PJ_NOME_TOPO_RUNA
        c["runa_base"] = PJ_RUNA_BASE
        c["runa_medalhao"] = medalhao_solto(
            circulo_elementos(elementos), c["tema"]["a"], c["avancado"],
            " · ".join([e["nome"] for e in elementos] + (["runa avançada"] if c["avancado"] else ["runa básica"])))
        return [("runa", c, "")]
    # estandarte: o elemento no medalhão e, embaixo, separado e do mesmo tamanho, o ícone do tipo
    # (com a estrela rúnica se for avançado)
    icone = dict(simbolo(cfg, "locais", d["tipo"]), nome=NOMES_LOCAL[d["tipo"]])
    c["icone_local"] = circulo_local(icone, c["tema"]["a"], c["avancado"])
    _pano(c, [NOMES_LOCAL[d["tipo"]], "Avançado" if c["avancado"] else "Básico"],
          circulo_elementos(elementos), segundo=interno_slot(icone, c["tema"]["a"]),
          segundo_avancado=c["avancado"], nome_segundo=icone["nome"] + (" avançado" if c["avancado"] else ""))
    return [("local", c, "")]


def _quest(d, cfg, val, origem):
    """Quest: um texto (condição de conclusão, inimigo neutro...) para cada ato, porque a pilha
    é embaralhada e a mesma quest pode sair no ato I, II ou III (livro, seções 4 e 11)."""
    c = _base(d, cfg, val, origem)
    atos = d.get("atos")
    if not isinstance(atos, list) or not all(isinstance(t, str) for t in atos) or len(atos) > 3:
        val.erro('"atos" deve ser uma lista com o texto de cada ato: ["ato I", "ato II", "ato III"]')
        atos = []
    atos = (atos + ["", "", ""])[:3]
    for n, t in enumerate(atos, 1):
        if not t.strip():
            val.aviso(f"falta o texto do ato {ROMANOS[n]}")
    if d.get("texto"):
        val.aviso('na quest o texto vai em "atos" (um por ato); "texto" não aparece na carta')
    c["atos"] = atos
    c["recompensa"] = (d.get("recompensa") or "").strip()  # opcional: os atos encolhem para ela caber
    _com_elementos(c, [])
    c["nome_topo"] = PJ_NOME_TOPO_QUEST  # nome mais alto, para os 3 atos caberem embaixo
    _pano(c, ["Quest"])
    return [("quest", c, "")]


TIPOS = {"acao": _acao, "personagem": _personagem, "item": _item,
         "campo": _local, "retiro": _local, "runa": _local, "quest": _quest}


def ler_carta(caminho, cfg):
    """Devolve (faces, validador). faces = [(template, dados, sufixo_do_arquivo)]."""
    caminho = Path(caminho)
    try:
        d = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        val = Validador(caminho)
        val.erro(f"JSON inválido: linha {e.lineno}, coluna {e.colno}: {e.msg}")
        return [], val
    return ler_dados(d, caminho, cfg)


def ler_dados(d, origem, cfg):
    """Como ler_carta, mas a partir do dict já carregado. origem dá o nome dos arquivos de saída."""
    caminho = Path(origem)
    val = Validador(caminho)
    d = json.loads(json.dumps(d))  # cópia: a normalização altera o dict
    if not isinstance(d, dict):
        val.erro("o arquivo deve conter um objeto JSON")
        return [], val

    tipo = slug(d.get("tipo", "")).replace("-", "_")
    if tipo not in TIPOS:
        val.erro(f'tipo inválido: {d.get("tipo")!r} (válidos: {", ".join(TIPOS)})')
        return [], val
    d["tipo"] = tipo

    if "palavras_chave" in d:
        val.aviso('"palavras_chave" não é mais usado: escreva as palavras-chave no texto '
                  "(ex.: Escudo 2); as que têm ícone aparecem sozinhas na carta")
    for k in d:
        if k == "palavras_chave":
            continue
        if k in PROIBIDOS.get(tipo, {}):
            val.erro(f'"{k}" não existe em {tipo}: {PROIBIDOS[tipo][k]}')
        elif k not in CAMPOS_COMUNS | CAMPOS[tipo] and not k.startswith("_"):
            val.aviso(f'campo desconhecido: "{k}"')

    faces = TIPOS[tipo](d, cfg, val, caminho)

    total = cfg["colecao"].get("total", "")
    edicao = cfg["colecao"].get("edicao", "")
    for _, c, _ in faces:
        _estandartes(c)
        _layout(c)
        c["rotulo_numero"] = f'{c["numero"]} / {total}' if c.get("numero") else ""
        c["rotulo_edicao"] = " · ".join(x for x in (edicao, c.get("rodape_extra")) if x)
    # todos os tipos usam o frame comum (frames/carta.html); os templates antigos estão em frames/antigo/
    faces = [("carta", c, sufixo) for _, c, sufixo in faces]
    return faces, val


# ---------- esqueletos para "gerar.py nova" ----------

MODELOS = {
    "acao": {
        "tipo": "acao", "nome": "", "numero": "", "estrelas": 1, "ato_minimo": 1,
        "elementos": ["mana"], "custo_carga": 0, "classes": [], "subtipos": ["ataque"],
        "texto": "", "ambientacao": "", "arte": "",
    },
    "personagem": {
        "tipo": "personagem", "nome": "", "numero": "", "estrelas": 10, "elemento": "mana",
        "classes": [], "raca": "", "cla": "", "funcao": "",
        "frente": {"poder": 2, "texto": "", "evolui_nivel": 3, "evolui": "", "arte": ""},
        "verso": {"nome": "", "poder": 3, "ascensao_nivel": 8, "texto": "", "ascende": "", "arte": ""},
    },
    "item": {
        "tipo": "item", "nome": "", "numero": "", "estrelas": 5, "custo_moedas": 3,
        "slot": "arma de 1 mão",
        "texto": "", "ambientacao": "", "arte": "",
    },
    "campo": {
        "tipo": "campo", "nome": "", "numero": "", "estrelas": 3, "elemento": "mana",
        "avancado": False, "texto": "", "ambientacao": "", "arte": "",
    },
    "retiro": {
        "tipo": "retiro", "nome": "", "numero": "", "estrelas": 3, "elemento": "gaia",
        "avancado": False, "texto": "", "ambientacao": "", "arte": "",
    },
    "runa": {
        "tipo": "runa", "nome": "", "numero": "", "estrelas": 4, "elemento": "mana",
        "avancado": True, "texto": "", "ambientacao": "", "arte": "",
    },
    "quest": {
        "tipo": "quest", "nome": "", "numero": "", "estrelas": 2,
        "atos": ["", "", ""], "arte": "",
    },
}
