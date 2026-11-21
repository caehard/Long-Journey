"""Servidor da mesa virtual: deckbuilder e emulador de partida.

Observa cards/, arte/, frames/ e gerador/: quando algo muda (por exemplo, uma carta salva no
criador), refaz o acervo (mesa/acervo.py) e avisa os navegadores abertos, que atualizam sozinhos.
O criador (app.py) também avisa a mesa ao salvar, para a atualização ser imediata.
"""

import json
import mimetypes
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from gerador.dados import FRAMES, RAIZ

from . import acervo, decks
from .partida import ErroJogada, Partida

PORTA = 8766
WEB = RAIZ / "mesa" / "web"
PAGINAS = {"/": "index.html", "/decks": "decks.html", "/jogo": "jogo.html"}

mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("text/javascript", ".js")


class Acervo:
    """O índice do acervo em memória, refeito por uma thread quando os arquivos mudam."""

    def __init__(self):
        self.indice = acervo.ler_indice()
        self.trava = threading.Lock()
        self.agora = threading.Event()
        self.ultimo = None
        self.erro = None
        self.ao_mudar = lambda: None

    def cartas(self):
        return self.indice.get("cartas", {})

    def sincronizar(self):
        with self.trava:
            r = subprocess.run([sys.executable, "-m", "mesa.acervo"], cwd=RAIZ, capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
            for linha in r.stderr.strip().splitlines():
                print(f"[{time.strftime('%H:%M:%S')}] {linha}")
            self.erro = None if r.returncode == 0 else (r.stderr.strip().splitlines() or ["erro"])[-1]
            novo = acervo.ler_indice()
            if novo.get("versao") != self.indice.get("versao"):
                self.indice = novo
                self.ao_mudar()

    def observar(self):
        while True:
            impressao = acervo.impressao_geral()
            if impressao != self.ultimo or self.agora.is_set():
                self.agora.clear()
                self.ultimo = impressao
                try:
                    self.sincronizar()
                except Exception as e:  # um erro no gerador não pode derrubar a mesa
                    self.erro = str(e)
                    print(f"  ERRO no acervo: {e}")
            self.agora.wait(0.8)


ACERVO = Acervo()
PARTIDA = Partida(acervo.ACERVO / "partida.json", ACERVO.cartas)


def _avisar_acervo():
    with PARTIDA.trava:
        PARTIDA.versao += 1
        PARTIDA.mudou.notify_all()


ACERVO.ao_mudar = _avisar_acervo


def _dentro(caminho, pasta):
    return caminho.resolve().is_relative_to(pasta.resolve())


class Manipulador(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def _json(self, obj, status=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _arquivo(self, caminho, cache=False):
        if not caminho.is_file():
            return self.send_error(404)
        corpo = caminho.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(caminho.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(corpo)))
        # as imagens do acervo levam ?v=assinatura na URL: podem ficar em cache
        self.send_header("Cache-Control", "max-age=31536000, immutable" if cache else "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _corpo(self):
        tamanho = int(self.headers.get("Content-Length", 0))
        if tamanho > 2_000_000:
            raise ValueError("pedido grande demais")
        return json.loads(self.rfile.read(tamanho) or b"{}")

    def _eventos(self, token):
        """Server-sent events: avisa quando a partida ou o acervo mudam."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        visto = None
        try:
            while True:
                with PARTIDA.trava:
                    if visto == PARTIDA.versao:
                        PARTIDA.mudou.wait(15)
                    versao = PARTIDA.versao
                dado = json.dumps({"versao": versao, "acervo": ACERVO.indice.get("versao"),
                                   "erro_acervo": ACERVO.erro})
                if versao != visto:
                    self.wfile.write(f"event: mudou\ndata: {dado}\n\n".encode())
                    visto = versao
                else:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        caminho = unquote(url.path)
        if caminho in PAGINAS:
            return self._arquivo(WEB / PAGINAS[caminho])
        if caminho.startswith("/web/"):
            alvo = WEB / caminho[len("/web/"):]
            return self._arquivo(alvo) if _dentro(alvo, WEB) else self.send_error(403)
        if caminho.startswith("/acervo/img/"):
            alvo = acervo.IMAGENS / caminho[len("/acervo/img/"):]
            return self._arquivo(alvo, cache=True) if _dentro(alvo, acervo.IMAGENS) else self.send_error(403)
        if caminho.startswith("/frames/"):
            alvo = FRAMES / caminho[len("/frames/"):]
            ok = _dentro(alvo, FRAMES / "fontes") or _dentro(alvo, FRAMES / "icones")
            return self._arquivo(alvo) if ok else self.send_error(403)
        if caminho == "/api/acervo":
            return self._json({**ACERVO.indice, "erro": ACERVO.erro})
        if caminho == "/api/decks":
            return self._json(decks.listar())
        if caminho == "/api/deck":
            try:
                return self._json(decks.normalizar(decks.ler(q.get("arquivo", ""))))
            except (OSError, ValueError):
                return self._json({"erro": "deck não encontrado"}, 404)
        if caminho == "/api/estado":
            return self._json(PARTIDA.visao(q.get("token", "")))
        if caminho == "/api/eventos":
            return self._eventos(q.get("token", ""))
        self.send_error(404)

    def do_POST(self):
        caminho = urlparse(self.path).path
        try:
            p = self._corpo()
            if caminho == "/api/decks/conferir":
                deck = p.get("deck", {})
                pedidos, sugeridas = decks.runas_sugeridas(deck, ACERVO.cartas())
                return self._json({**decks.conferir(deck, ACERVO.cartas()), "elementos_runas": pedidos,
                                   "runas_sugeridas": sugeridas})
            if caminho == "/api/decks/salvar":
                return self._json({"arquivo": decks.salvar(p.get("deck", {}))})
            if caminho == "/api/decks/apagar":
                decks.apagar(p.get("arquivo", ""))
                return self._json({"ok": True})
            if caminho == "/api/acervo/sincronizar":
                ACERVO.agora.set()
                return self._json({"ok": True})
            if caminho == "/api/entrar":
                return self._json({"token": PARTIDA.entrar(p.get("nome"), p.get("token"))})
            token = p.get("token", "")
            if caminho == "/api/sentar":
                PARTIDA.sentar(token, p.get("deck", ""), p.get("alinhamento", "neutro"))
            elif caminho == "/api/levantar":
                PARTIDA.levantar(token)
            elif caminho == "/api/comecar":
                PARTIDA.comecar(token)
            elif caminho == "/api/encerrar":
                PARTIDA.encerrar(token)
            elif caminho == "/api/acao":
                PARTIDA.acao(token, p)
            else:
                return self.send_error(404)
            return self._json({"ok": True})
        except ErroJogada as e:
            return self._json({"erro": str(e)}, 400)
        except (ValueError, KeyError, TypeError) as e:
            return self._json({"erro": f"pedido inválido: {e}"}, 400)


def _ips_locais():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return [s.getsockname()[0]]
    except OSError:
        return []


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    args = sys.argv[1:]
    porta = int(args[args.index("--porta") + 1]) if "--porta" in args else PORTA
    rede = "--rede" in args
    try:
        servidor = ThreadingHTTPServer(("0.0.0.0" if rede else "127.0.0.1", porta), Manipulador)
    except OSError:
        sys.exit(f"A porta {porta} já está em uso (a mesa já está aberta?). Use --porta para escolher outra.")
    servidor.daemon_threads = True
    print("Conferindo o acervo (a primeira vez desenha todas as cartas)...")
    ACERVO.ultimo = acervo.impressao_geral()
    ACERVO.sincronizar()
    threading.Thread(target=ACERVO.observar, daemon=True).start()
    endereco = f"http://localhost:{porta}"
    print(f"Mesa em {endereco}  (deckbuilder em /decks, partida em /jogo; Ctrl+C para sair)")
    if rede:
        for ip in _ips_locais():
            print(f"Na rede local, os outros jogadores abrem http://{ip}:{porta}/jogo")
    if "--sem-navegador" not in args:
        threading.Timer(0.6, webbrowser.open, [endereco]).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
