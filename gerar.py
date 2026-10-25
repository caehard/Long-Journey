"""Gerador de cartas.

Uso:
  python gerar.py                         gera o PNG de todas as cartas de cards/
  python gerar.py cards/x.json ...        gera só essas cartas
  python gerar.py --pdf                   também um PDF por carta (63 x 88 mm)
  python gerar.py --folha                 também out/folha-a4.pdf (3 x 3, marcas de corte)
  python gerar.py --sangria 3             adiciona 3 mm de sangria (para gráfica)
  python gerar.py --escala 3              PNG maior (padrão 2 = 1260 x 1760 px, ~500 dpi)
  python gerar.py --observar              regera sozinho quando um JSON, frame ou arte muda

  python gerar.py nova acao "Bola de Fogo"   cria cards/bola-de-fogo.json a partir do modelo
  python gerar.py validar                    só confere os JSON, sem gerar imagens

Tipos para "nova": acao, personagem, item, campo, retiro, runa, quest.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from gerador.dados import CARTAS, FRAMES, MODELOS, RAIZ, carregar_config, ler_carta, slug

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _rel(p):
    try:
        return Path(p).resolve().relative_to(RAIZ)
    except ValueError:
        return p


def coletar(caminhos, cfg):
    """Lê e valida as cartas. Devolve as faces válidas e quantos arquivos tinham erro."""
    faces, com_erro = [], 0
    for caminho in caminhos:
        fs, val = ler_carta(caminho, cfg)
        for a in val.avisos:
            print(f"  aviso  {_rel(caminho)}: {a}")
        if val.erros:
            com_erro += 1
            for e in val.erros:
                print(f"  ERRO   {_rel(caminho)}: {e}")
            continue
        faces += [(t, c, c["id"] + suf) for t, c, suf in fs]
    return faces, com_erro


def arquivos_de_cartas(args_cartas):
    if args_cartas:
        return [Path(c) for c in args_cartas]
    return sorted(p for p in CARTAS.glob("**/*.json") if not p.name.startswith("_"))


def gerar(args, render):
    cfg = carregar_config()
    caminhos = arquivos_de_cartas(args.cartas)
    if not caminhos:
        print("Nenhuma carta em cards/. Crie uma com: python gerar.py nova acao \"Nome\"")
        return
    faces, com_erro = coletar(caminhos, cfg)
    if not faces:
        print("Nada para gerar.")
        return

    inicio = time.time()
    saida = RAIZ / "out"
    avisos = []
    pngs, av = render.png(faces, saida / "png")
    avisos += av
    print(f"PNG: {len(pngs)} em {_rel(saida / 'png')}")
    if args.pdf:
        pdfs, av = render.pdf_individual(faces, saida / "pdf")
        avisos += av
        print(f"PDF: {len(pdfs)} em {_rel(saida / 'pdf')}")
    if args.folha:
        arq, av = render.folha_a4(faces, saida / "folha-a4.pdf")
        avisos += av
        print(f"Folha A4: {_rel(arq)}")
    for ident, msg in dict.fromkeys(map(tuple, avisos)):
        print(f"  aviso  {ident}: {msg}")
    if com_erro:
        print(f"{com_erro} carta(s) com erro não foram geradas.")
    print(f"Pronto em {time.time() - inicio:.1f}s.")


def observar(args, render):
    pastas = [CARTAS, FRAMES, RAIZ / "arte"]

    def estado():
        return {p: p.stat().st_mtime for d in pastas if d.exists() for p in d.rglob("*") if p.is_file()}

    visto = estado()
    gerar(args, render)
    print("Observando cards/, frames/ e arte/. Ctrl+C para sair.")
    try:
        while True:
            time.sleep(0.7)
            agora = estado()
            if agora != visto:
                visto = agora
                print(time.strftime("\n[%H:%M:%S] mudança detectada"))
                try:
                    gerar(args, render)
                except Exception as e:  # um template quebrado não deve matar o modo observar
                    print(f"  ERRO   {e}")
    except KeyboardInterrupt:
        pass


def nova(tipo, nome):
    tipo = slug(tipo).replace("-", "_")
    if tipo not in MODELOS:
        sys.exit(f'Tipo inválido: {tipo}. Use um de: {", ".join(MODELOS)}')
    destino = CARTAS / f"{slug(nome)}.json"
    if destino.exists():
        sys.exit(f"Já existe: {_rel(destino)}")
    carta = json.loads(json.dumps(MODELOS[tipo]))
    carta["nome"] = nome
    carta["arte"] = f"arte/{slug(nome)}.png"
    if tipo == "personagem":
        carta.pop("arte")
        carta["frente"]["arte"] = f"arte/{slug(nome)}.png"
        carta["verso"]["arte"] = f"arte/{slug(nome)}-evoluido.png"
        carta["verso"]["nome"] = nome
    CARTAS.mkdir(exist_ok=True)
    destino.write_text(json.dumps(carta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Criado {_rel(destino)}. Preencha os campos e rode: python gerar.py {_rel(destino).as_posix()}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "nova":
        if len(sys.argv) != 4:
            sys.exit('Uso: python gerar.py nova <tipo> "Nome da carta"')
        return nova(sys.argv[2], sys.argv[3])
    if len(sys.argv) > 1 and sys.argv[1] == "validar":
        faces, com_erro = coletar(arquivos_de_cartas(sys.argv[2:]), carregar_config())
        print(f"{len(faces)} face(s) válida(s), {com_erro} arquivo(s) com erro.")
        sys.exit(1 if com_erro else 0)

    ap = argparse.ArgumentParser(description="Gera as imagens das cartas a partir de cards/*.json.")
    ap.add_argument("cartas", nargs="*", help="arquivos JSON (padrão: todos em cards/)")
    ap.add_argument("--pdf", action="store_true", help="gera também um PDF por carta")
    ap.add_argument("--folha", action="store_true", help="gera também folhas A4 3x3 para imprimir")
    ap.add_argument("--escala", type=float, default=2.0, help="multiplicador do PNG (padrão 2)")
    ap.add_argument("--sangria", type=float, default=0.0, help="sangria em mm (ex.: 3)")
    ap.add_argument("--observar", action="store_true", help="regera ao salvar")
    args = ap.parse_args()

    from gerador.render import Renderizador  # importa Playwright só quando precisa
    with Renderizador(escala=args.escala, sangria_mm=args.sangria) as render:
        (observar if args.observar else gerar)(args, render)


if __name__ == "__main__":
    main()
