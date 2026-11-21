"""Acervo da mesa: as cartas de cards/ exportadas para o deckbuilder e o jogo.

Para cada carta válida de cards/, o acervo guarda a imagem de cada face (PNG na escala 1,
630 x 880, em acervo/img/) e um resumo com o que o deckbuilder e a mesa precisam (tipo,
estrelas, elementos, nível, ato...), tudo listado em acervo/acervo.json.

Só refaz as cartas que mudaram: cada uma tem uma assinatura (o JSON, as artes que ela usa e
os frames e o código do gerador). Cartas apagadas saem do acervo; cartas com erro ficam
listadas com os erros, sem imagem.

Uso: python -m mesa.acervo [--tudo]   (o servidor da mesa roda isto sozinho quando algo muda)
"""

import hashlib
import json
import os
import sys
import time

from gerador.dados import CARTAS, FRAMES, RAIZ, carregar_config, ler_carta

ACERVO = RAIZ / "acervo"
IMAGENS = ACERVO / "img"
INDICE = ACERVO / "acervo.json"
GERADOR = RAIZ / "gerador"
ARTE = RAIZ / "arte"
ESCALA = 1.0


def arquivos_de_cartas():
    return sorted(p for p in CARTAS.glob("*.json") if not p.name.startswith("_"))


def _impressao(pastas_e_padroes):
    """Lista (caminho, mtime, tamanho) dos arquivos: muda quando algum arquivo muda."""
    itens = []
    for pasta, padrao in pastas_e_padroes:
        if pasta.exists():
            for p in sorted(pasta.glob(padrao)):
                if p.is_file() and "__pycache__" not in p.parts:
                    st = p.stat()
                    itens.append((p.relative_to(RAIZ).as_posix(), st.st_mtime_ns, st.st_size))
    return itens


def impressao_geral():
    """O que, se mudar, pede para conferir o acervo de novo (o servidor observa isto)."""
    return _impressao([(CARTAS, "*.json"), (ARTE, "**/*"), (FRAMES, "**/*"), (GERADOR, "*.py")])


def _assinatura_comum():
    dados = json.dumps(_impressao([(FRAMES, "**/*"), (GERADOR, "*.py")])).encode()
    return hashlib.sha1(dados + str(ESCALA).encode()).hexdigest()


def _artes(d):
    """Caminhos de arte que a carta usa (na raiz e nas faces)."""
    caminhos = [d.get("arte")] + [(d.get(f) or {}).get("arte") for f in ("frente", "verso")]
    return [c for c in caminhos if isinstance(c, str) and c]


def _assinatura(caminho, d, comum):
    h = hashlib.sha1(caminho.read_bytes())
    for a in _artes(d):
        p = RAIZ / a
        if p.exists():
            h.update(f"{a}:{p.stat().st_mtime_ns}".encode())
    h.update(comum.encode())
    return h.hexdigest()


def _texto_busca(d):
    partes = [d.get("nome", ""), d.get("texto", ""), d.get("recompensa", ""), d.get("ao_revelar", ""),
              d.get("raca", ""), d.get("cla", ""), d.get("funcao", "")]
    for f in ("frente", "verso"):
        face = d.get(f) or {}
        partes += [face.get("nome", ""), face.get("texto", "")]
    return " ".join(str(p) for p in partes if p)


def resumo(d):
    """O que o deckbuilder e a mesa usam de cada carta, tirado do JSON."""
    t = d.get("tipo", "")
    elementos = d.get("elementos") or ([d["elemento"]] if d.get("elemento") else [])
    r = {"tipo": t, "nome": d.get("nome", ""), "estrelas": d.get("estrelas"),
         "elementos": list(elementos), "classes": list(d.get("classes") or []),
         "busca": _texto_busca(d)}
    if t in ("personagem", "item"):
        r["unico"] = d.get("unico") is True
    if t == "personagem":
        r["nivel"] = d.get("nivel")
    if t == "protagonista":
        r["enredo"] = d.get("enredo", 5)
    if t in ("protagonista", "personagem"):
        r["poder"] = (d.get("frente") or {}).get("poder")
        if isinstance(d.get("verso"), dict):
            r["nome_verso"] = d["verso"].get("nome") or r["nome"]
            r["poder_verso"] = d["verso"].get("poder")
    if t == "quest":
        r["ato"] = d.get("ato")
    if t in ("acao", "item", "campo", "retiro") and d.get("ato_minimo"):
        r["ato_minimo"] = d.get("ato_minimo")
    if t == "acao":
        r["subtipos"] = list(d.get("subtipos") or [])
        r["custo_carga"] = d.get("custo_carga", 0)
    if t == "item":
        r["slot"] = d.get("slot")
        if d.get("custo_moedas") is not None:
            r["custo_moedas"] = d.get("custo_moedas")
    if t == "ato":
        r["rodadas"] = d.get("rodadas")
    return r


def ler_indice():
    try:
        return json.loads(INDICE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"versao": 0, "cartas": {}, "elementos": {}}


def _gravar_indice(indice):
    ACERVO.mkdir(exist_ok=True)
    temp = INDICE.with_suffix(".tmp")
    temp.write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temp, INDICE)  # troca atômica: o servidor nunca lê um índice pela metade


def sincronizar(tudo=False, saida=print):
    """Confere cards/ contra o acervo e refaz o que mudou. Devolve {mudou, novas, erros}."""
    cfg = carregar_config()
    indice = ler_indice()
    antigas = indice.get("cartas", {})
    comum = _assinatura_comum()
    cartas, pendentes, mudou = {}, [], False

    for caminho in arquivos_de_cartas():
        ident = caminho.stem
        try:
            d = json.loads(caminho.read_text(encoding="utf-8"))
        except ValueError as e:
            d = {}
            erro_json = f"JSON inválido: {e}"
        else:
            erro_json = None
        assinatura = _assinatura(caminho, d if isinstance(d, dict) else {}, comum)
        velha = antigas.get(ident)
        if velha and velha.get("assinatura") == assinatura and not tudo:
            cartas[ident] = velha
            continue
        mudou = True
        if erro_json or not isinstance(d, dict):
            cartas[ident] = {"id": ident, "arquivo": caminho.name, "assinatura": assinatura,
                             "erros": [erro_json or "o arquivo deve conter um objeto JSON"], "faces": []}
            continue
        faces, val = ler_carta(caminho, cfg)
        entrada = {"id": ident, "arquivo": caminho.name, "assinatura": assinatura, **resumo(d),
                   "erros": list(val.erros), "avisos": list(val.avisos), "faces": []}
        cartas[ident] = entrada
        if not val.erros:
            pendentes.append((entrada, faces))

    removidas = set(antigas) - set(cartas)
    if removidas:
        mudou = True
        for ident in removidas:
            for face in antigas[ident].get("faces", []):
                (ACERVO / face.split("?")[0]).unlink(missing_ok=True)

    if pendentes:
        from gerador.render import Renderizador  # Playwright só quando há o que desenhar
        todas = [(t, c, c["id"] + suf) for _, fs in pendentes for t, c, suf in fs]
        with Renderizador(escala=ESCALA) as render:
            arquivos, _ = render.png(todas, IMAGENS)
        nomes = {a.stem for a in arquivos}
        for entrada, fs in pendentes:
            entrada["faces"] = [f"img/{entrada['id']}{suf}.png?v={entrada['assinatura'][:10]}"
                                for _, _, suf in fs if entrada["id"] + suf in nomes]
            if len(entrada["faces"]) < len(fs):
                entrada["erros"].append("a imagem não foi gerada")

    if mudou or not INDICE.exists():
        elementos = {k: {"nome": v.get("nome", k), "cor": v.get("cor", "#999")}
                     for k, v in cfg.get("elementos", {}).items()}
        indice = {"versao": time.time_ns(), "cartas": cartas, "elementos": elementos}
        _gravar_indice(indice)
    novas = [cartas[p[0]["id"]]["nome"] for p in pendentes]
    if novas:
        saida(f"acervo: {len(novas)} carta(s) atualizada(s): {', '.join(novas)}")
    if removidas:
        saida(f"acervo: {len(removidas)} carta(s) removida(s): {', '.join(sorted(removidas))}")
    erros = {k: v["erros"] for k, v in cartas.items() if v.get("erros")}
    return {"mudou": mudou, "novas": novas, "removidas": sorted(removidas), "erros": erros}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r = sincronizar(tudo="--tudo" in sys.argv, saida=lambda m: print(m, file=sys.stderr))
    print(json.dumps(r, ensure_ascii=False))
