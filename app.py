"""App local para testar o criador de cartas.

Uso: python app.py [--porta 8765] [--sem-navegador]  (abre http://localhost:8765 no navegador)

Usa o mesmo código do gerador: a pré-visualização é o template real preenchido
pelo gerador/dados.py, e "Exportar" roda o gerar.py de verdade.
"""

import json
import mimetypes
import re
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from gerador import dados
from gerador.dados import CARTAS, FRAMES, RAIZ, carregar_config, ler_dados, simbolo, slug

dados.URL_BASE = "/raiz/"  # o navegador busca fontes, ícones e artes por este servidor

from gerador.render import Renderizador  # noqa: E402

PORTA = 8765
APP = RAIZ / "app"
ARTE = RAIZ / "arte"
SAIDA = RAIZ / "out"
PASTAS_PUBLICAS = (FRAMES, ARTE, SAIDA)
EXT_ARTE = {".png", ".jpg", ".jpeg", ".webp"}

mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/ttf", ".ttf")

montador = Renderizador()  # só monta HTML; o navegador do Playwright não é aberto aqui
trava_exportar = threading.Lock()


def _dentro(caminho, pastas):
    caminho = caminho.resolve()
    return any(caminho.is_relative_to(p.resolve()) for p in pastas)


def _arquivo_de_carta(nome):
    """Nome de arquivo seguro dentro de cards/."""
    nome = Path(str(nome)).name
    if not nome.endswith(".json"):
        nome += ".json"
    caminho = (CARTAS / nome).resolve()
    if not _dentro(caminho, [CARTAS]):
        raise ValueError("nome de arquivo inválido")
    return caminho


def previa(carta, arquivo):
    cfg = carregar_config()
    origem = Path(arquivo or (slug(carta.get("nome", "")) or "previa") + ".json")
    try:
        faces, val = ler_dados(carta, origem, cfg)
        cartas = [montador.carta_html(t, c, c["id"] + suf, 0) for t, c, suf in faces]
    except Exception as e:  # template ou dado inesperado: mostra o erro em vez de cair
        return {"html": "", "erros": [f"erro ao montar a carta: {e}"], "avisos": []}
    legendas = len(faces) == 2
    if legendas:
        cartas = [f'<div><div class="legenda">{t}</div>{h}</div>' for t, h in zip(("Frente", "Verso"), cartas)]
    estilo = ("body{margin:0;display:flex;gap:30px;padding:0}"
              ".legenda{height:32px;font:700 18px Cinzel,serif;letter-spacing:3px;text-transform:uppercase;"
              "color:#9aa0b4;text-align:center}")
    return {"html": montador.pagina("".join(cartas), estilo), "erros": val.erros, "avisos": val.avisos,
            "faces": len(faces), "legendas": legendas}


def configuracao():
    cfg = carregar_config()

    def lista(categoria):
        return [{"chave": k, "nome": v.get("nome", k), "icone": simbolo(cfg, categoria, k)["icone"],
                 "cor": v.get("cor")} for k, v in cfg.get(categoria, {}).items()]

    return {
        "elementos": lista("elementos"),
        "classes": lista("classes"),
        "subtipos": lista("subtipos_acao"),
        "slots": lista("slots"),
        "palavras_chave": lista("palavras_chave"),
        "tipos": list(dados.MODELOS),
        "modelos": dados.MODELOS,
        "artes": sorted(p.relative_to(RAIZ).as_posix() for p in ARTE.glob("**/*") if p.suffix.lower() in EXT_ARTE),
    }


def listar_cartas():
    saida = []
    for p in sorted(CARTAS.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            saida.append({"arquivo": p.name, "nome": d.get("nome", ""), "tipo": d.get("tipo", "")})
        except Exception:
            saida.append({"arquivo": p.name, "nome": "(JSON inválido)", "tipo": ""})
    return saida


def exportar(arquivo, pdf=False):
    caminho = _arquivo_de_carta(arquivo)
    args = [sys.executable, str(RAIZ / "gerar.py"), str(caminho)] + (["--pdf"] if pdf else [])
    with trava_exportar:
        r = subprocess.run(args, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace")
    pngs = sorted((SAIDA / "png").glob(f"{caminho.stem}*.png"))
    pngs = [p for p in pngs if re.fullmatch(re.escape(caminho.stem) + r"(-frente|-verso)?", p.stem)]
    return {"ok": r.returncode == 0, "saida": (r.stdout + r.stderr).strip(),
            "pngs": ["/raiz/" + p.relative_to(RAIZ).as_posix() for p in pngs]}


class Manipulador(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _json(self, obj, status=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _arquivo(self, caminho):
        if not caminho.is_file():
            return self.send_error(404)
        corpo = caminho.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(caminho.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _corpo(self):
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def do_GET(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        if url.path in ("/", "/index.html"):
            return self._arquivo(APP / "index.html")
        if url.path.startswith("/raiz/"):
            caminho = RAIZ / unquote(url.path[len("/raiz/"):])
            if not _dentro(caminho, PASTAS_PUBLICAS):
                return self.send_error(403)
            return self._arquivo(caminho)
        if url.path == "/api/config":
            return self._json(configuracao())
        if url.path == "/api/cartas":
            return self._json(listar_cartas())
        if url.path == "/api/carta":
            try:
                caminho = _arquivo_de_carta(q.get("arquivo", [""])[0])
                return self._json(json.loads(caminho.read_text(encoding="utf-8")))
            except Exception as e:
                return self._json({"erro": str(e)}, 400)
        self.send_error(404)

    def do_POST(self):
        url = urlparse(self.path)
        try:
            if url.path == "/api/arte":
                nome = Path(unquote(self.headers.get("X-Nome", "arte.png")))
                ext = nome.suffix.lower()
                if ext not in EXT_ARTE:
                    return self._json({"erro": f"formato não aceito: {ext} (use png, jpg ou webp)"}, 400)
                ARTE.mkdir(exist_ok=True)
                destino = ARTE / f"{slug(nome.stem) or 'arte'}{ext}"
                destino.write_bytes(self._corpo())
                return self._json({"arte": destino.relative_to(RAIZ).as_posix()})

            pedido = json.loads(self._corpo() or b"{}")
            if url.path == "/api/previa":
                return self._json(previa(pedido.get("carta", {}), pedido.get("arquivo")))
            if url.path == "/api/salvar":
                carta = pedido["carta"]
                arquivo = pedido.get("arquivo") or (slug(carta.get("nome", "")) or "carta-sem-nome")
                caminho = _arquivo_de_carta(arquivo)
                CARTAS.mkdir(exist_ok=True)
                caminho.write_text(json.dumps(carta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                return self._json({"arquivo": caminho.name})
            if url.path == "/api/exportar":
                return self._json(exportar(pedido["arquivo"], pedido.get("pdf", False)))
        except Exception as e:
            return self._json({"erro": str(e)}, 400)
        self.send_error(404)


def main():
    porta = int(sys.argv[sys.argv.index("--porta") + 1]) if "--porta" in sys.argv else PORTA
    try:
        servidor = ThreadingHTTPServer(("127.0.0.1", porta), Manipulador)
    except OSError:
        sys.exit(f"A porta {porta} já está em uso (o app já está aberto?). Use --porta para escolher outra.")
    endereco = f"http://localhost:{porta}"
    print(f"Criador de cartas em {endereco}  (Ctrl+C para sair)")
    if "--sem-navegador" not in sys.argv:
        threading.Timer(0.6, webbrowser.open, [endereco]).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
