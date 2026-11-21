"""Leitura, validação e normalização dos JSON de cartas.

Cada arquivo em cards/ vira uma ou mais "faces" (personagem único tem duas).
Uma face é um dict pronto para o template do frame correspondente.
"""

import json
import math
import re
import unicodedata
from pathlib import Path

from .simbolos import PANO_LARGO, anexo_classe, interno_rodadas, medalhao_solto, anexo_moedas, bandeira, bandeira_personagem, interno_slot, circulo_elementos, estrela_lapidada, linha_moldura, simbolo_quina, hexagono_poder, anexo_coroa, moeda_custo, estandarte, estandarte_duplo, selo_chave, tema

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
    "protagonista": {"elemento", "classes", "classe_dupla", "raca", "cla", "funcao", "poder", "enredo",
                     "frente", "verso"},
    "personagem": {"unico", "nivel", "elemento", "classes", "classe_dupla", "raca", "cla", "funcao", "poder",
                   "frente", "verso"},
    "item": {"unico", "slot", "custo_moedas", "ato_minimo"},
    "campo": {"elemento", "ato_minimo"},
    "retiro": {"elemento", "ato_minimo"},
    "runa": {"elemento"},
    "quest": {"ato", "recompensa", "ao_revelar"},
    "ato": {"rodadas"},
}

# campos que o livro de regras não permite naquele tipo: viram erro, com o motivo
FICHA_PROIBIDA = ("não existem fichas: o que um efeito gera vem do seu deck de Eventos; runas, campo e "
                  "retiro vêm de fora dos decks (livro, seção 3)")
SEM_AVANCADO = "campos e retiros avançados não existem mais (livro, seção 3)"
PROIBIDOS = {
    "acao": {"ficha": FICHA_PROIBIDA},
    "protagonista": {"ficha": FICHA_PROIBIDA,
                     "unico": "Único é subtipo de personagem; o protagonista já é 1 por deck (livro, seção 3)",
                     "nivel": "nível impresso é só do personagem; o do protagonista é a pontuação na partida (livro, seção 11)"},
    "personagem": {"ficha": FICHA_PROIBIDA,
                   "protagonista": 'protagonista é um tipo de carta: use "tipo": "protagonista" (livro, seção 3)',
                   "enredo": "enredo é do protagonista (livro, seção 5)"},
    "item": {"ficha": FICHA_PROIBIDA,
             "classes": "classe é impressa só em ações e personagens (livro, glossário)",
             "classe_dupla": "item não tem classe"},
    "campo": {"ficha": FICHA_PROIBIDA, "avancado": SEM_AVANCADO},
    "retiro": {"ficha": FICHA_PROIBIDA, "avancado": SEM_AVANCADO},
    "runa": {"ficha": FICHA_PROIBIDA,
             "avancado": "não existe runa avançada nem com efeito: só nome e elemento (livro, seção 6)",
             "texto": "a runa não tem efeito: só nome e elemento (livro, seção 6)",
             "estrelas": "a runa não custa estrelas (livro, seção 3)",
             "ato_minimo": "a runa entra em jogo na preparação e não trava por ato (livro, seção 6)"},
    "quest": {"ficha": FICHA_PROIBIDA,
              "atos": 'a quest agora tem um ato só, a partir do qual pode ser puxada: use "ato" (1 a 3); '
                      'o "texto" é o objetivo (livro, seção 11)',
              "ato_minimo": 'na quest o ato é o campo "ato" (livro, seção 11)',
              "niveis": 'o que a quest dá vai em "recompensa" (livro, seção 11)'},
    "ato": {"ficha": FICHA_PROIBIDA,
            "estrelas": "cartas de Ato são da temporada, fora dos decks, e não custam estrelas (livro, seções 3 e 11)",
            "ato": "a carta de Ato é o próprio ato; o número dele vem da ordem em que sai (livro, seção 11)",
            "ato_minimo": "a carta de Ato é o próprio ato; o número dele vem da ordem em que sai (livro, seção 11)",
            "atos": "a carta de Ato tem um efeito só, no \"texto\" (livro, seção 11)",
            "turnos": 'a duração do Ato é contada em rodadas: use "rodadas" (livro, seção 11)',
            "recompensa": "Ato não tem recompensa; recompensa é da quest, no deck de Eventos (livro, seção 11)"},
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


SEM_ESTRELAS = {"ato", "runa"}    # cartas de Ato e runas não custam estrelas (livro, seção 3)


def _base(d, cfg, val, origem):
    nome = (d.get("nome") or "").strip()
    if not nome:
        val.erro('falta o campo "nome"')
    estrelas = None
    if d.get("tipo") not in SEM_ESTRELAS:
        estrelas = val.inteiro(d, "estrelas", 0)
    return {
        "id": origem.stem,
        "tipo": d.get("tipo"),
        "nome": nome,
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
PJ_NOME_TOPO_QUEST = 385                     # na quest o nome sobe para as caixas caberem
# linha de baixo da moldura com os medalhões nela: na runa a linha desce mais (a estrela, se houver, e o
# número ficam no canto de baixo à esquerda); no campo/retiro os medalhões das quinas param acima do número e da edição
PJ_RUNA_BASE, PJ_LOCAL_BASE = 784, 790
# runa, campo e retiro: nome centralizado sobre a linha de cima (a linha abre embaixo dele)
PJ_NOME_CENTRO_TOPO, PJ_NOME_CENTRO_LARG = 0, 330
# campo e retiro: medalhões nas quinas de baixo da moldura (centro x)
PJ_QUINA_ESQ, PJ_QUINA_DIR = 80, 550
# raio visível do medalhão solto: a linha termina um pouco por dentro dele, para entrar por
# baixo do anel e o medalhão ficar encaixado na moldura
PJ_MED_RAIO = 60
PJ_MED_ENCAIXE = 4
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


def _raca_e_pano(c, f, unico, nivel=None):
    """Texto vertical do canto de cima à esquerda (raça; clã e função na linha de dentro, ou a
    raça sozinha nela) e o estandarte (elemento, coroa de único, nível do personagem, classe)."""
    c["linhas_raca"] = [x for x in (f.get("raca"), " · ".join(f.get(k) for k in ("cla", "funcao") if f.get(k))) if x]
    c["bandeira"] = bandeira_personagem(c["elementos_s"], c["classes_s"], unico, c["tema"]["a"], nivel)
    c["pano_largura"] = PANO_LARGO if c["bandeira"] else None


def _cortes_moldura(c):
    """Trechos da moldura (em px da carta), com chanfro nas quinas e mais grossa perto delas
    (simbolos.linha_moldura). A linha não passa por baixo do estandarte, da barra do nome, da
    caixa de evolução nem dos medalhões de baixo: ela é interrompida nesses lugares (não é só
    escondida), para nada aparecer atrás do que é transparente."""
    e, d, t, b = 22.5, 630 - 22.5, 22.5, 880 - 96 - 2.5   # centro da linha
    QUEBRA = None
    if c.get("nome_centro"):
        # runa, campo, retiro: nome centralizado sobre a linha de cima, base alta com os medalhões;
        # a linha termina um pouco por dentro do contorno de cada medalhão (entra por baixo do anel)
        b = c["base_y"]
        folga = 18 if c.get("ato_minimo") else 6   # a placa do ato é 12 px mais larga de cada lado
        n0, n1 = 315 - PJ_NOME_CENTRO_LARG / 2 - folga, 315 + PJ_NOME_CENTRO_LARG / 2 + folga
        volta = [(n1, t, False), (d, t, True)]
        r = PJ_MED_RAIO - PJ_MED_ENCAIXE
        if c.get("quinas"):
            # medalhões nas quinas: a lateral desce até encontrar o círculo e a base sai dele
            dy_d = math.sqrt(max(r ** 2 - (d - PJ_QUINA_DIR) ** 2, 0))
            dy_e = math.sqrt(max(r ** 2 - (PJ_QUINA_ESQ - e) ** 2, 0))
            volta += [(d, b - dy_d, False), QUEBRA, (PJ_QUINA_DIR - r, b, False),
                      (PJ_QUINA_ESQ + r, b, False), QUEBRA, (e, b - dy_e, False)]
        else:                # runa: o elemento no centro de baixo
            volta += [(d, b, True), (315 + r, b, False), QUEBRA, (315 - r, b, False), (e, b, True)]
        volta += [(e, t, True), (n0, t, False)]
    else:
        pano = c.get("pano_largura")
        pano1 = 630 - PJ_PANO_DIREITA
        # a base para na borda inclinada da caixa, na altura da linha
        caixa_x = PJ_CAIXA_ESQ + PJ_CAIXA_INCL * (1 - (b - PJ_CAIXA_TOPO) / PJ_CAIXA_ALTURA)
        # volta completa a partir do nome, descendo pela esquerda; QUEBRA = trecho interrompido
        nome_topo = c.get("nome_topo", PJ_NOME_TOPO)
        volta = [(e, nome_topo + PJ_NOME_ALTURA, False), (e, b, True)]
        if c.get("criterio_rotulo"):
            volta += [(caixa_x, b, False), QUEBRA, (d, PJ_CAIXA_TOPO, False)]
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
    # estandarte: elementos (com o custo de carga por cima) e a classe num círculo preso ao
    # medalhão, onde o item tem as moedas; com 2 classes, uma de cada lado. O ato mínimo fica no
    # pentágono colado ao nome (carta.html)
    if len(c["classes_s"]) > 3:
        val.aviso(f'{len(c["classes_s"])} classes: só as 3 primeiras aparecem no estandarte')
    _pano(c, [" · ".join(x["nome"] for x in c["subtipos_s"])],
          c["circulo"], classes_anexo=c["classes_s"][:3])
    return [("acao", c, "")]


def _protagonista(d, cfg, val, origem):
    return _unidade(d, cfg, val, origem, protagonista=True)


def _personagem(d, cfg, val, origem):
    return _unidade(d, cfg, val, origem, protagonista=False)


def _unidade(d, cfg, val, origem, protagonista):
    """Protagonista e personagem, dois tipos de carta com o mesmo frame (livro, seções 3, 10 e 12).
    Os dois têm 1 elemento e a "frente" (forma base). Protagonista (rosto do deck, 1 por jogador,
    fora dos decks): sempre duas faces, com a ascensão no verso. Personagem (deck de Eventos): o
    "verso" (forma evoluída) é opcional e nunca tem ascensão; tem "nivel" impresso, fixo, igual
    nas duas faces (círculo preso ao medalhão, à esquerda); pode ter o subtipo Único (coroa presa
    ao medalhão, à direita)."""
    if "unico" in d and not isinstance(d["unico"], bool):
        val.erro(f'"unico" deve ser true ou false (está {d["unico"]!r})')
    unico = not protagonista and d.get("unico") is True
    nivel = None if protagonista else val.inteiro(d, "nivel", 0)
    if not isinstance(d.get("frente"), dict):
        val.erro(f'falta a "frente" do {d["tipo"]} (forma base, com poder e texto)')
        return []
    tem_verso = isinstance(d.get("verso"), dict)
    if "verso" in d and not tem_verso:
        val.erro('"verso" deve ser um objeto com a forma evoluída')
        return []
    if protagonista and not tem_verso:
        val.erro('protagonista tem duas faces: falta o "verso" (forma evoluída, com a ascensão) (livro, seção 12)')
        return []
    if not protagonista:
        for k in ("ascensao_nivel", "ascende"):
            if k in (d.get("verso") or {}):
                val.erro(f'"{k}" no verso: só o protagonista ascende (livro, seção 12); '
                         'use "tipo": "protagonista" ou tire o campo')
        if not tem_verso:
            for k in ("evolui", "evolui_nivel"):
                if k in d["frente"]:
                    val.aviso(f'"{k}" sem "verso": o personagem não tem forma evoluída e a evolução não aparece')
        elif "evolui_nivel" in d["frente"]:
            val.aviso('"evolui_nivel" no personagem: o nível dele é o impresso, fixo; se a evolução depende '
                      'do nível do protagonista, escreva isso em "evolui" (livro, seção 12)')
    if "poder" in d:
        val.aviso('"poder" fica em cada face ("frente" e "verso")')

    faces = []
    lados = ("frente", "verso") if tem_verso else ("frente",)
    for lado in lados:
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
            val.erro('falta o campo "elemento": protagonista e personagem têm 1 elemento (no protagonista gera '
                     'a runa; no personagem, diz de quais runas saem as cargas que ele perde com dano) (livro, seções 4 e 9)')
        _com_elementos(c, elementos)
        c["poder"] = val.inteiro(f, "poder", 0)
        enredo = val.inteiro(f, "enredo", 0, obrigatorio=False)
        if protagonista and lado == "frente" and enredo not in (None, 5):
            val.aviso(f"enredo {enredo}: todo protagonista tem enredo 5 e ele não aparece na carta; "
                      "se este muda o enredo, escreva isso no texto")
        c["poder_svg"] = hexagono_poder(c["poder"]) if c["poder"] is not None else None
        _chaves_no_texto(c, c["texto"], cfg, val)
        _raca_e_pano(c, f, unico, nivel)
        c["lado"] = lado if tem_verso else ""

        # caixa perto da base: evolução na frente (se houver verso), ascensão no verso do protagonista.
        # O nível mínimo (evolui_nivel / ascensao_nivel) é validado, mas não aparece na carta.
        if lado == "verso" and protagonista:
            n = val.inteiro(f, "ascensao_nivel")
            if isinstance(n, int) and not 6 <= n <= 11:
                val.aviso(f"ascensao_nivel {n} fora da faixa do livro (6 a 11)")
            c["criterio_rotulo"], c["criterio"], icone = "Ascensão", f.get("ascende", ""), "ascensao"
        elif lado == "frente" and tem_verso:
            if val.inteiro(f, "evolui_nivel", 0, obrigatorio=False) is None and protagonista:
                val.aviso('falta "evolui_nivel" na frente: o nível mínimo para evoluir (livro, seção 12)')
            c["criterio_rotulo"], c["criterio"], icone = "Evolução", f.get("evolui", ""), "evolucao"
        else:
            c["criterio_rotulo"], c["criterio"], icone = None, "", None
        # quina de baixo à direita: ícone de evolução (setas para a direita) ou de ascensão
        arquivo = simbolo(cfg, "marcas", icone)["icone_arquivo"] if icone else None
        c["quina_svg"] = simbolo_quina(arquivo, c["criterio_rotulo"], girar=0 if lado == "verso" else 90) if arquivo else None
        # rodapé: "protagonista" na linha do número (a da edição é cortada pela caixa de ascensão)
        c["rodape_numero"] = "protagonista" if protagonista else ""
        c["rodape_extra"] = {"frente": "forma base", "verso": "forma evoluída"}[lado] if tem_verso else ""
        faces.append((d["tipo"], c, f"-{lado}" if tem_verso else ""))
    return faces


def _pano(c, linhas, centro=None, anexo=None, classes=(), detalhe=True, classes_anexo=(),
          anexo_esq=None, titulo_extra=()):
    """Layout novo (frames/carta.html): texto vertical do canto de cima à esquerda e estandarte."""
    c["linhas_raca"] = [x for x in linhas if x]
    nomes = ([e["nome"] for e in c.get("elementos_s", [])] + [s["nome"] for s in (*classes, *classes_anexo)]
             + list(titulo_extra))
    cor = c["tema"]["a"]
    c["bandeira"] = bandeira(cor, centro, anexo, classes, detalhe, " · ".join(nomes),
                             [anexo_classe(s, cor) for s in classes_anexo], anexo_esq)
    c["pano_largura"] = PANO_LARGO if c["bandeira"] else None


def _layout(c):
    """Completa o que o frame comum (carta.html) usa e cada tipo não preencheu."""
    for k, v in (("linhas_raca", []), ("bandeira", None), ("pano_largura", None), ("poder_svg", None),
                 ("chaves_pos", []), ("criterio_rotulo", None), ("quina_svg", None), ("caixas", None),
                 ("lado", ""), ("sem_texto", False), ("ato_minimo", None),
                 ("medalhoes_base", []), ("nome_centro", False), ("quinas", False)):
        c.setdefault(k, v)
    # protagonista ou personagem com caixa de evolução/ascensão: estrela embaixo à esquerda; nos
    # outros ela fica no centro (e a runa, para a linha de baixo poder descer com o elemento no centro)
    c["base_centro"] = not c["criterio_rotulo"] and c["tipo"] not in ("runa", "campo", "retiro")
    # campo e retiro: os medalhões ocupam as quinas, então estrela e número ficam juntos no centro
    c["base_grupo"] = c["tipo"] in ("campo", "retiro")
    _cortes_moldura(c)
    c["estrela_svg"] = (estrela_lapidada(c["estrelas"], f"{c['id']}{c['lado']}")
                        if c.get("estrelas") else None)


def _item(d, cfg, val, origem):
    c = _base(d, cfg, val, origem)
    if not d.get("slot"):
        val.erro(f'falta o campo "slot" (válidos: {", ".join(cfg["slots"])})')
        c["slot_s"] = simbolo(cfg, "slots", "?")
    else:
        slots = _simbolos(d, cfg, val, "slot", "slots", restrito=True)
        c["slot_s"] = slots[0] if slots else simbolo(cfg, "slots", d["slot"])
    _com_elementos(c, [])
    if "unico" in d and not isinstance(d["unico"], bool):
        val.erro(f'"unico" deve ser true ou false (está {d["unico"]!r})')
    unico = d.get("unico") is True
    c["ato_minimo"] = val.inteiro(d, "ato_minimo", 1, 3, obrigatorio=False)
    # custo em moedas (comprar no mercado) no lugar dos elementos; sem custo, sem círculo,
    # porque o item também pode entrar em jogo por outros efeitos
    c["custo_moedas"] = val.inteiro(d, "custo_moedas", 0, obrigatorio=False)
    c["circulo"] = moeda_custo(c["custo_moedas"]) if c["custo_moedas"] is not None else ""
    # estandarte: o slot no medalhão; a coroa de Único embaixo à direita, como no personagem, e o
    # custo em moedas embaixo à esquerda
    _pano(c, ["Item", c["slot_s"]["nome"]],
          interno_slot(c["slot_s"], c["tema"]["a"]),
          anexo_coroa() if unico else None,
          detalhe=True,
          anexo_esq=anexo_moedas(c["custo_moedas"]) if c["custo_moedas"] is not None else None,
          titulo_extra=["item único"] if unico else [])
    return [("item", c, "")]


def _local(d, cfg, val, origem):
    """Campo de batalha, retiro e runa, os três fora dos decks (livro, seções 3 e 6). A runa é um
    tipo de carta só com nome e elemento: sem efeito e sem estrelas."""
    c = _base(d, cfg, val, origem)
    elementos = _elementos(d, cfg, val, "elemento", 1)
    if not elementos:
        val.erro('falta o campo "elemento" (campo, retiro e runa sempre fornecem uma runa)')
    _com_elementos(c, elementos)
    if d["tipo"] == "runa":
        if c["ambientacao"].strip():
            val.aviso("a runa não tem caixa de texto: a ambientação não aparece")
        c["sem_texto"] = True
        # sem estandarte e sem texto vertical: o nome fica centralizado no topo e o elemento no
        # centro de baixo, sobre a linha da moldura
        c["nome_centro"] = True
        c["nome_topo"] = PJ_NOME_CENTRO_TOPO
        c["medalhoes_base"] = [(medalhao_solto(
            circulo_elementos(elementos), c["tema"]["a"],
            " · ".join([e["nome"] for e in elementos] + ["runa"])), 315, PJ_RUNA_BASE)]
        c["base_y"] = PJ_RUNA_BASE
        return [("runa", c, "")]
    c["ato_minimo"] = val.inteiro(d, "ato_minimo", 1, 3, obrigatorio=False)
    # o design da runa: sem estandarte nem texto vertical, nome centralizado no topo; nas quinas de
    # baixo da moldura, o ícone do tipo (esquerda) e o elemento (direita)
    icone = dict(simbolo(cfg, "locais", d["tipo"]), nome=NOMES_LOCAL[d["tipo"]])
    cor = c["tema"]["a"]
    c["nome_centro"] = True
    c["nome_topo"] = PJ_NOME_CENTRO_TOPO
    c["quinas"] = True
    c["medalhoes_base"] = [
        (medalhao_solto(interno_slot(icone, cor), cor, icone["nome"]), PJ_QUINA_ESQ, PJ_LOCAL_BASE),
        (medalhao_solto(circulo_elementos(elementos), cor, " · ".join(e["nome"] for e in elementos)),
         PJ_QUINA_DIR, PJ_LOCAL_BASE),
    ]
    c["base_y"] = PJ_LOCAL_BASE
    return [("local", c, "")]


def _quest(d, cfg, val, origem):
    """Quest (deck de Eventos): o ato a partir do qual pode ser puxada (o pentágono ao lado do
    nome), o objetivo ("texto"), a recompensa e, se houver, o efeito ao ser revelada
    ("ao_revelar"), cada um numa caixa com rótulo no lugar do texto (livro, seção 11)."""
    c = _base(d, cfg, val, origem)
    c["ato_minimo"] = val.inteiro(d, "ato", 1, 3)
    objetivo, recompensa, revelar = ((d.get(k) or "").strip() for k in ("texto", "recompensa", "ao_revelar"))
    if not objetivo:
        val.erro('falta o "texto": o objetivo da quest (livro, seção 11)')
    if not recompensa:
        val.erro('falta a "recompensa" (livro, seção 11)')
    c["caixas"] = ([("Ao ser revelada", revelar, "")] if revelar else []) + [
        ("Objetivo", objetivo, "principal"), ("Recompensa", recompensa, "destaque")]
    c["sem_texto"] = True
    _com_elementos(c, [])
    c["nome_topo"] = PJ_NOME_TOPO_QUEST  # nome mais alto, para as caixas caberem embaixo
    _pano(c, ["Quest"])
    return [("quest", c, "")]


def _ato(d, cfg, val, origem):
    """Carta de Ato (deck da temporada, fora dos decks dos jogadores; 3 sorteadas por partida):
    nome, rodadas que dura (no medalhão do estandarte) e o efeito enquanto durar ("texto"). Sem
    estrelas e sem número: ela é o próprio ato, e o número vem da ordem (livro, seções 4 e 11)."""
    c = _base(d, cfg, val, origem)
    rodadas = val.inteiro(d, "rodadas", 1)
    if not (c["texto"] or "").strip():
        val.aviso('falta o "texto": o efeito que vale enquanto o ato durar')
    _com_elementos(c, [])
    _pano(c, ["Ato"], interno_rodadas("?" if rodadas is None else rodadas))
    return [("ato", c, "")]


TIPOS = {"acao": _acao, "protagonista": _protagonista, "personagem": _personagem, "item": _item,
         "campo": _local, "retiro": _local, "runa": _local, "quest": _quest, "ato": _ato}


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
        c["rotulo_numero"] = " · ".join(x for x in (f'{c["numero"]} / {total}' if c.get("numero") else "",
                                                    c.get("rodape_numero", "")) if x)
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
    "protagonista": {
        "tipo": "protagonista", "nome": "", "numero": "", "estrelas": 10,
        "elemento": "mana", "classes": [], "raca": "", "cla": "", "funcao": "",
        "frente": {"poder": 2, "texto": "", "evolui_nivel": 3, "evolui": "", "arte": ""},
        "verso": {"nome": "", "poder": 3, "ascensao_nivel": 8, "texto": "", "ascende": "", "arte": ""},
    },
    "personagem": {
        "tipo": "personagem", "nome": "", "numero": "", "estrelas": 4, "nivel": 1, "unico": False,
        "elemento": "mana", "classes": [], "raca": "", "cla": "", "funcao": "",
        "frente": {"poder": 2, "texto": "", "arte": ""},
    },
    "item": {
        "tipo": "item", "nome": "", "numero": "", "estrelas": 5, "unico": False, "custo_moedas": 3,
        "slot": "arma de 1 mão",
        "texto": "", "ambientacao": "", "arte": "",
    },
    "campo": {
        "tipo": "campo", "nome": "", "numero": "", "estrelas": 3, "elemento": "mana",
        "texto": "", "ambientacao": "", "arte": "",
    },
    "retiro": {
        "tipo": "retiro", "nome": "", "numero": "", "estrelas": 3, "elemento": "gaia",
        "texto": "", "ambientacao": "", "arte": "",
    },
    "runa": {
        "tipo": "runa", "nome": "", "numero": "", "elemento": "mana", "arte": "",
    },
    "quest": {
        "tipo": "quest", "nome": "", "numero": "", "estrelas": 2, "ato": 1,
        "texto": "", "recompensa": "", "ao_revelar": "", "arte": "",
    },
    "ato": {
        "tipo": "ato", "nome": "", "numero": "", "rodadas": 6, "texto": "", "arte": "",
    },
}
