"""Decks: guardar em decks/ e conferir as regras de construção (livro, seção 3).

Formato de um deck (decks/<nome>.json), com as cartas pelo id (nome do arquivo em cards/):
  {"nome": "...", "protagonista": "id", "campo": "id", "retiro": "id",
   "runas": ["id", "id", "id"], "jornada": {"id": cópias}, "eventos": {"id": cópias}}

A conferência é a mesma no deckbuilder (que mostra os erros enquanto se monta o deck) e na
mesa (que só aceita deck sem erro).
"""

import json
import re
import unicodedata
from collections import Counter

from gerador.dados import RAIZ

DECKS = RAIZ / "decks"
ORCAMENTO = 100
TIPOS_JORNADA = {"acao"}
TIPOS_EVENTOS = {"personagem", "item", "quest"}
NOME_TIPO = {"acao": "ação", "protagonista": "protagonista", "personagem": "personagem", "item": "item",
             "campo": "campo de batalha", "retiro": "retiro", "runa": "runa", "quest": "quest",
             "ato": "carta de Ato"}


def copias_permitidas(estrelas):
    """1 estrela: até 4; 2: até 3; 3: até 2; 4 ou mais: 1 (livro, seção 3)."""
    e = max(int(estrelas or 0), 1)
    return {1: 4, 2: 3, 3: 2}.get(e, 1)


def slug(texto):
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")


def caminho_do_deck(nome):
    s = slug(nome)
    if not s:
        raise ValueError("dê um nome ao deck")
    return DECKS / f"{s}.json"


def listar():
    saida = []
    for p in sorted(DECKS.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            saida.append({"arquivo": p.stem, "nome": d.get("nome") or p.stem})
        except ValueError:
            saida.append({"arquivo": p.stem, "nome": f"{p.stem} (JSON inválido)"})
    return saida


def ler(arquivo):
    p = DECKS / f"{slug(arquivo)}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def normalizar(d):
    """Deixa o deck no formato esperado, sem confiar no que veio do navegador."""
    def ident(v):
        return str(v) if isinstance(v, str) and v else None

    def lista(v):
        if not isinstance(v, dict):
            return {}
        return {str(k): int(n) for k, n in v.items() if isinstance(n, (int, float)) and int(n) > 0}

    runas = d.get("runas") if isinstance(d.get("runas"), list) else []
    return {"nome": str(d.get("nome") or "").strip()[:80], "protagonista": ident(d.get("protagonista")),
            "campo": ident(d.get("campo")), "retiro": ident(d.get("retiro")),
            "runas": [ident(r) for r in runas[:3]], "jornada": lista(d.get("jornada")),
            "eventos": lista(d.get("eventos"))}


def salvar(d):
    d = normalizar(d)
    caminho = caminho_do_deck(d["nome"])
    DECKS.mkdir(exist_ok=True)
    caminho.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return caminho.stem


def apagar(arquivo):
    (DECKS / f"{slug(arquivo)}.json").unlink(missing_ok=True)


def conferir(d, cartas):
    """Confere um deck contra o acervo. Devolve {estrelas, erros, avisos, contagem}."""
    d = normalizar(d)
    erros, avisos = [], []
    estrelas = 0

    def carta(ident, onde):
        c = cartas.get(ident)
        if not c:
            erros.append(f"{onde}: a carta \"{ident}\" não está no acervo (foi apagada ou renomeada?)")
            return None
        if c.get("erros"):
            erros.append(f"{onde}: {c.get('nome') or ident} tem erro no JSON e não pode ser usada")
            return None
        return c

    # fora dos decks: 1 protagonista, 1 campo, 1 retiro (custam estrelas) e 3 runas (não custam)
    elementos_base = []
    for campo, tipo, rotulo in (("protagonista", "protagonista", "Protagonista"),
                                ("campo", "campo", "Campo de batalha"), ("retiro", "retiro", "Retiro")):
        if not d[campo]:
            erros.append(f"falta escolher o {rotulo.lower()}")
            continue
        c = carta(d[campo], rotulo)
        if not c:
            continue
        if c["tipo"] != tipo:
            erros.append(f"{rotulo}: {c['nome']} é {NOME_TIPO.get(c['tipo'], c['tipo'])}, não {rotulo.lower()}")
            continue
        estrelas += c.get("estrelas") or 0
        elementos_base += c.get("elementos", [])[:1]

    runas = [r for r in d["runas"] if r]
    elementos_runas = []
    if len(runas) != 3:
        erros.append(f"são 3 runas, uma de cada elemento do protagonista, do campo e do retiro (há {len(runas)})")
    for r in runas:
        c = carta(r, "Runa")
        if c and c["tipo"] != "runa":
            erros.append(f"Runa: {c['nome']} não é uma runa")
        elif c:
            elementos_runas += c.get("elementos", [])
    if len(elementos_base) == 3 and len(runas) == 3 and Counter(elementos_runas) != Counter(elementos_base):
        erros.append("as runas devem ser dos elementos do protagonista, do campo e do retiro, uma de cada "
                     f"(pedido: {', '.join(sorted(elementos_base))}; escolhido: {', '.join(sorted(elementos_runas))})")
    cobertos = set(elementos_runas or elementos_base)

    contagem = {}
    for deck, tipos, rotulo in (("jornada", TIPOS_JORNADA, "Jornada"), ("eventos", TIPOS_EVENTOS, "Eventos")):
        total = 0
        for ident, n in d[deck].items():
            c = carta(ident, rotulo)
            if not c:
                continue
            if c["tipo"] not in tipos:
                onde = "o deck de Eventos" if c["tipo"] in TIPOS_EVENTOS else (
                    "a Jornada" if c["tipo"] in TIPOS_JORNADA else "fora dos decks")
                erros.append(f"{rotulo}: {c['nome']} é {NOME_TIPO.get(c['tipo'], c['tipo'])}; vai em {onde}")
                continue
            limite = copias_permitidas(c.get("estrelas"))
            if n > limite:
                erros.append(f"{rotulo}: {n} cópias de {c['nome']}; com {c.get('estrelas') or 0} estrela(s), "
                             f"o máximo é {limite}")
            estrelas += (c.get("estrelas") or 0) * n
            total += n
            fora = [e for e in c.get("elementos", []) if e not in cobertos]
            if fora and cobertos:
                avisos.append(f"{rotulo}: {c['nome']} é de {', '.join(fora)}, que as suas runas não cobrem")
        contagem[deck] = total
    if not contagem.get("jornada"):
        avisos.append("a Jornada está vazia: ela é a vida do protagonista")

    if estrelas > ORCAMENTO:
        erros.append(f"o deck soma {estrelas} estrelas; o teto é {ORCAMENTO}")
    return {"estrelas": estrelas, "orcamento": ORCAMENTO, "erros": erros, "avisos": avisos,
            "contagem": contagem}


def runas_sugeridas(d, cartas):
    """Escolhe as 3 runas pelos elementos do protagonista, do campo e do retiro, mantendo as já
    escolhidas que servem. Devolve a lista de ids (None onde não há runa daquele elemento)."""
    d = normalizar(d)
    pedidos = []
    for campo in ("protagonista", "campo", "retiro"):
        c = cartas.get(d[campo] or "")
        pedidos.append((c.get("elementos") or [None])[0] if c else None)
    atuais = [r for r in d["runas"] if r in cartas]
    escolhidas = []
    for el in pedidos:
        achou = next((r for r in atuais if el in cartas[r].get("elementos", [])), None)
        if achou:
            atuais.remove(achou)
        else:
            achou = next((k for k, c in sorted(cartas.items()) if c.get("tipo") == "runa"
                          and not c.get("erros") and el in c.get("elementos", [])), None)
        escolhidas.append(achou)
    return pedidos, escolhidas


def ler_para_jogo(arquivo, cartas):
    """Lê um deck e confere. Devolve (deck, conferência)."""
    d = normalizar(ler(arquivo))
    return d, conferir(d, cartas)

