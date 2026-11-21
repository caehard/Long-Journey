"""Estado de uma partida na mesa virtual.

A mesa não aplica as regras: os jogadores movem as cartas e ajustam os contadores, como numa
mesa de verdade. O servidor guarda o estado, esconde o que cada jogador não pode ver (mão,
Jornada, deck de Eventos e cargas dos outros, Atos virados) e registra tudo no log.

Zonas (listas de cartas; nas pilhas, o índice 0 é o topo):
  mao:A, jornada:A, eventos:A, historico:A, quests:A    do jogador A (assento)
  campo:A, retiro_carta:A, runas:A                      as cartas fora dos decks, em jogo
  regiao:A, retiro:A                                    as unidades na região do campo de A e no retiro de A
  cargas:A:I                                            as cargas sob a runa I de A
  anexos:IID                                            os itens equipados na unidade IID
  pilha, cemiterio, atos_ocultos, ato_atual, atos_passados, fora
"""

import copy
import json
import os
import random
import secrets
import threading

from . import decks

FASES = ["Epílogo", "Hiato", "Conto", "Saga", "Prólogo"]
SAGA = 3
CORES = ["#e0a24a", "#5aa0e6", "#7fc76f", "#c78fe8", "#e06a6a", "#5fd0c8"]
KARMA_INICIAL = {"bom": 1, "mau": -1, "neutro": 0}
MAX_JOGADORES = 6
MAX_DESFAZER = 40
TOPO_PRIMEIRO = ("jornada:", "eventos:", "historico:", "cargas:", "pilha", "cemiterio", "atos_")
MESA = ("regiao:", "retiro:", "anexos:", "quests:", "campo:", "retiro_carta:", "runas:", "ato_atual", "pilha")
NOMES_ZONA = {"mao": "mão", "jornada": "Jornada", "eventos": "deck de Eventos", "historico": "histórico",
              "quests": "quests em jogo", "campo": "campo de batalha", "retiro_carta": "retiro",
              "runas": "runas", "regiao": "região", "retiro": "retiro", "cargas": "cargas", "anexos": "itens",
              "pilha": "pilha", "cemiterio": "cemitério", "atos_ocultos": "Atos", "ato_atual": "Ato atual",
              "atos_passados": "Atos passados", "fora": "fora de jogo"}


class ErroJogada(Exception):
    pass


def _dono_da_zona(zona):
    partes = zona.split(":")
    if len(partes) >= 2 and partes[0] != "anexos":
        try:
            return int(partes[1])
        except ValueError:
            return None
    return None


def _estado_vazio():
    return {"etapa": "sala", "sessoes": {}, "jogadores": [], "cartas": {}, "zonas": {}, "turno": None,
            "log": [], "seq": 0, "nlog": 0}


class Partida:
    def __init__(self, arquivo, acervo):
        """arquivo: onde o estado é gravado; acervo(): devolve o dict de cartas do acervo."""
        self.arquivo = arquivo
        self.acervo = acervo
        self.trava = threading.RLock()
        self.mudou = threading.Condition(self.trava)
        self.versao = 1
        self.desfazer = []
        self.e = _estado_vazio()
        try:
            salvo = json.loads(arquivo.read_text(encoding="utf-8"))
            if isinstance(salvo, dict) and "etapa" in salvo:
                self.e = {**_estado_vazio(), **salvo}
        except (OSError, ValueError):
            pass

    # ---------- utilidades ----------

    def _gravar(self):
        self.versao += 1
        try:
            self.arquivo.parent.mkdir(exist_ok=True)
            temp = self.arquivo.with_suffix(".tmp")
            temp.write_text(json.dumps(self.e, ensure_ascii=False), encoding="utf-8")
            os.replace(temp, self.arquivo)
        except OSError:
            pass
        self.mudou.notify_all()

    def _log(self, texto, quem=None):
        self.e["nlog"] += 1
        self.e["log"].append({"n": self.e["nlog"], "texto": texto, "quem": quem})
        del self.e["log"][:-300]

    def _jogador(self, assento):
        for j in self.e["jogadores"]:
            if j["assento"] == assento:
                return j
        raise ErroJogada("jogador não encontrado")

    def _nome_jogador(self, assento):
        try:
            return self._jogador(assento)["nome"]
        except ErroJogada:
            return "alguém"

    def _zona(self, nome):
        return self.e["zonas"].setdefault(nome, [])

    def _onde(self, iid):
        for nome, lista in self.e["zonas"].items():
            if iid in lista:
                return nome
        raise ErroJogada("carta não encontrada na mesa")

    def _nome_carta(self, iid):
        c = self.e["cartas"].get(iid)
        if not c:
            return "carta"
        a = self.acervo().get(c["id"], {})
        if c.get("verso") and a.get("nome_verso"):
            return a["nome_verso"]
        return a.get("nome") or c["id"]

    def _tipo(self, iid):
        return self.acervo().get(self.e["cartas"][iid]["id"], {}).get("tipo", "")

    def _novo(self, ident, dono):
        self.e["seq"] += 1
        iid = f"c{self.e['seq']}"
        self.e["cartas"][iid] = {"iid": iid, "id": ident, "dono": dono, "exausta": False, "verso": False,
                                 "marcador": 0, "neutro": False}
        return iid

    @staticmethod
    def oculta(zona, assento):
        """A zona esconde as cartas de quem está no assento?"""
        dono = _dono_da_zona(zona)
        if zona.startswith(("jornada:", "atos_ocultos")):
            return True
        if zona.startswith(("mao:", "eventos:", "cargas:")):
            return dono != assento
        return False

    def _publica(self, zona):
        return not zona.startswith(("mao:", "jornada:", "eventos:", "cargas:", "atos_ocultos"))

    def _rotulo_zona(self, zona):
        partes = zona.split(":")
        base = NOMES_ZONA.get(partes[0], partes[0])
        if partes[0] == "anexos":
            return f"equipada em {self._nome_carta(partes[1])}"
        if partes[0] == "cargas":
            return f"cargas da runa {int(partes[2]) + 1} de {self._nome_jogador(int(partes[1]))}"
        dono = _dono_da_zona(zona)
        return base if dono is None else f"{base} de {self._nome_jogador(dono)}"

    def _limpar(self, iid):
        c = self.e["cartas"][iid]
        c.update(exausta=False, verso=False, marcador=0, neutro=False)

    def _mover(self, iid, destino, topo=None):
        """Move a carta (e os itens equipados nela, se ela sai da mesa). Devolve a zona de origem."""
        origem = self._onde(iid)
        if destino.startswith("anexos:"):
            alvo = destino.split(":", 1)[1]
            if alvo == iid or alvo not in self.e["cartas"]:
                raise ErroJogada("unidade inválida para equipar")
        self.e["zonas"][origem].remove(iid)
        lista = self._zona(destino)
        if topo is None:
            topo = destino.startswith(TOPO_PRIMEIRO)
        lista.insert(0, iid) if topo else lista.append(iid)
        if not destino.startswith(MESA):
            self._limpar(iid)  # fora da mesa a carta perde o estado (exaurida, virada, marcador)
        # itens equipados: se a unidade sai da mesa, vão para o cemitério
        if not destino.startswith(("regiao:", "retiro:")):
            for item in list(self.e["zonas"].get(f"anexos:{iid}", [])):
                self._mover(item, "cemiterio")
        return origem

    def _pode_mexer(self, iid, assento):
        zona = self._onde(iid)
        if self.oculta(zona, assento) and not (zona.startswith("jornada:") and _dono_da_zona(zona) == assento):
            raise ErroJogada("você não pode mexer numa carta que não vê")
        return zona

    def _contar_entrada(self, iid, origem, destino, assento):
        # o nome só fica escondido quando a carta vai de uma zona escondida para outra
        visivel = self._publica(origem) or self._publica(destino)
        nome = self._nome_carta(iid) if visivel else "uma carta"
        self._log(f"{self._nome_jogador(assento)} moveu {nome}: {self._rotulo_zona(origem)} → "
                  f"{self._rotulo_zona(destino)}", assento)

    # ---------- visão de cada jogador ----------

    def visao(self, token):
        with self.trava:
            sessao = self.e["sessoes"].get(token)
            assento = sessao.get("assento") if sessao else None
            zonas = {}
            for nome, lista in self.e["zonas"].items():
                escondida = self.oculta(nome, assento)
                espiar = 0
                if nome.startswith("jornada:") and _dono_da_zona(nome) == assento:
                    espiar = self._jogador(assento).get("espiar", 0)
                saida = []
                for i, iid in enumerate(lista):
                    c = self.e["cartas"][iid]
                    if escondida and i >= espiar:
                        saida.append({"iid": iid, "dono": c["dono"], "oculta": True})
                    else:
                        saida.append(c)
                zonas[nome] = saida
            jogadores = [{k: v for k, v in j.items() if k != "token"} for j in self.e["jogadores"]]
            return {"versao": self.versao, "etapa": self.e["etapa"], "eu": assento,
                    "nome": sessao.get("nome") if sessao else None, "jogadores": jogadores,
                    "zonas": zonas, "turno": self.e["turno"], "log": self.e["log"][-150:],
                    "pode_desfazer": bool(self.desfazer), "fases": FASES}

    # ---------- sala ----------

    def entrar(self, nome, token=None):
        with self.trava:
            nome = (str(nome or "").strip() or "Jogador")[:24]
            if token and token in self.e["sessoes"]:
                self.e["sessoes"][token]["nome"] = nome
                for j in self.e["jogadores"]:
                    if j.get("token") == token:
                        j["nome"] = nome
            else:
                token = secrets.token_urlsafe(16)
                self.e["sessoes"][token] = {"nome": nome, "assento": None}
            self._gravar()
            return token

    def sessao(self, token):
        s = self.e["sessoes"].get(token)
        if not s:
            raise ErroJogada("sessão desconhecida: entre de novo na mesa")
        return s

    def sentar(self, token, arquivo_deck, alinhamento):
        with self.trava:
            s = self.sessao(token)
            if self.e["etapa"] != "sala":
                raise ErroJogada("a partida já começou")
            if alinhamento not in KARMA_INICIAL:
                raise ErroJogada("alinhamento inválido")
            try:
                deck, conf = decks.ler_para_jogo(arquivo_deck, self.acervo())
            except (OSError, ValueError):
                raise ErroJogada("deck não encontrado")
            if conf["erros"]:
                raise ErroJogada("o deck tem erros; corrija no deckbuilder: " + conf["erros"][0])
            j = next((j for j in self.e["jogadores"] if j.get("token") == token), None)
            if not j:
                if len(self.e["jogadores"]) >= MAX_JOGADORES:
                    raise ErroJogada(f"a mesa tem no máximo {MAX_JOGADORES} jogadores")
                livres = sorted(set(range(MAX_JOGADORES)) - {x["assento"] for x in self.e["jogadores"]})
                j = {"assento": livres[0], "token": token, "cor": CORES[livres[0]]}
                self.e["jogadores"].append(j)
                self.e["jogadores"].sort(key=lambda x: x["assento"])
            j.update(nome=s["nome"], deck=arquivo_deck, deck_nome=deck["nome"], alinhamento=alinhamento)
            s["assento"] = j["assento"]
            self._log(f"{s['nome']} sentou com o deck {deck['nome']} ({alinhamento}).", j["assento"])
            self._gravar()

    def levantar(self, token):
        with self.trava:
            s = self.sessao(token)
            if self.e["etapa"] != "sala":
                raise ErroJogada("a partida já começou")
            self.e["jogadores"] = [j for j in self.e["jogadores"] if j.get("token") != token]
            s["assento"] = None
            self._gravar()

    def comecar(self, token):
        with self.trava:
            s = self.sessao(token)
            if self.e["etapa"] != "sala":
                raise ErroJogada("a partida já começou")
            if not self.e["jogadores"]:
                raise ErroJogada("ninguém sentou à mesa")
            acervo = self.acervo()
            preparados = []
            for j in self.e["jogadores"]:
                deck, conf = decks.ler_para_jogo(j["deck"], acervo)
                if conf["erros"]:
                    raise ErroJogada(f"o deck de {j['nome']} tem erros: {conf['erros'][0]}")
                preparados.append((j, deck))
            self.desfazer = []
            self.e.update(cartas={}, zonas={}, seq=0, log=[], nlog=0)
            self._log(f"{s['nome']} começou a partida.")
            # 1 e 7. protagonista (na região do próprio campo), campo, retiro e runas, prontos e sem cargas
            for j, deck in preparados:
                a = j["assento"]
                for zona in ("mao", "jornada", "eventos", "historico", "quests", "campo", "retiro_carta",
                             "runas", "regiao", "retiro"):
                    self._zona(f"{zona}:{a}")
                self._zona(f"campo:{a}").append(self._novo(deck["campo"], a))
                self._zona(f"retiro_carta:{a}").append(self._novo(deck["retiro"], a))
                self._zona(f"regiao:{a}").append(self._novo(deck["protagonista"], a))
                for i, r in enumerate(deck["runas"]):
                    self._zona(f"runas:{a}").append(self._novo(r, a))
                    self._zona(f"cargas:{a}:{i}")
                jornada = [self._novo(k, a) for k, n in deck["jornada"].items() for _ in range(n)]
                random.shuffle(jornada)
                self._zona(f"jornada:{a}").extend(jornada)
                # o deck de Eventos não é embaralhado: fica na ordem em que foi montado
                self._zona(f"eventos:{a}").extend(self._novo(k, a) for k, n in deck["eventos"].items()
                                                  for _ in range(n))
                enredo = acervo.get(deck["protagonista"], {}).get("enredo") or 5
                j.update(karma=KARMA_INICIAL[j["alinhamento"]], nivel=0, moedas=0, enredo=enredo, vivo=True,
                         espiar=0)
                # 4. mão inicial igual ao enredo, sem mulligan
                for iid in self.e["zonas"][f"jornada:{a}"][:enredo]:
                    self._mover(iid, f"mao:{a}")
            for zona in ("pilha", "cemiterio", "atos_ocultos", "ato_atual", "atos_passados", "fora"):
                self._zona(zona)
            # 2 e 6. três Atos sorteados do deck da temporada; o primeiro é revelado
            atos = [k for k, c in acervo.items() if c.get("tipo") == "ato" and not c.get("erros")]
            random.shuffle(atos)
            for k in atos[:3]:
                self._zona("atos_ocultos").append(self._novo(k, None))
            if len(atos) < 3:
                self._log(f"Atenção: o acervo só tem {len(atos)} carta(s) de Ato; a partida precisa de 3.")
            if self.e["zonas"]["atos_ocultos"]:
                self._mover(self.e["zonas"]["atos_ocultos"][0], "ato_atual")
            # 3. primeiro jogador sorteado; a ordem segue os assentos a partir dele
            assentos = [j["assento"] for j, _ in preparados]
            inicio = random.randrange(len(assentos))
            ordem = assentos[inicio:] + assentos[:inicio]
            # 9. na primeira rodada, cada turno começa direto na Saga
            self.e["turno"] = {"ordem": ordem, "vez": 0, "fase": SAGA, "rodada": 1, "rodadas_ato": 0, "ato": 1,
                               "transicao": False}
            self.e["etapa"] = "jogo"
            ato = self.e["zonas"]["ato_atual"]
            if ato:
                self._log(f"Ato 1: {self._nome_carta(ato[0])}.")
            self._log(f"Primeiro jogador: {self._nome_jogador(ordem[0])}. A primeira rodada começa na Saga.")
            self._gravar()

    def encerrar(self, token):
        with self.trava:
            s = self.sessao(token)
            self.e.update(etapa="sala", cartas={}, zonas={}, turno=None)
            self.desfazer = []
            self._log(f"{s['nome']} encerrou a partida.")
            self._gravar()

    # ---------- jogadas ----------

    def acao(self, token, pedido):
        with self.trava:
            s = self.sessao(token)
            a = s.get("assento")
            op = pedido.get("op")
            if op == "chat":
                texto = str(pedido.get("texto", "")).strip()[:300]
                if texto:
                    self._log(f"{s['nome']}: {texto}", a)
                    self._gravar()
                return
            if self.e["etapa"] == "sala":
                raise ErroJogada("a partida ainda não começou")
            if a is None:
                raise ErroJogada("só quem está sentado à mesa pode jogar")
            if op == "desfazer":
                if not self.desfazer:
                    raise ErroJogada("nada para desfazer")
                anterior = self.desfazer.pop()
                self.e.update(anterior)
                self._log(f"{s['nome']} desfez a última jogada.", a)
                self._gravar()
                return
            metodo = getattr(self, f"_op_{op}", None)
            if not metodo:
                raise ErroJogada(f"jogada desconhecida: {op}")
            foto = {k: copy.deepcopy(self.e[k]) for k in ("cartas", "zonas", "jogadores", "turno", "etapa", "seq")}
            try:
                metodo(a, pedido)
            except Exception:
                self.e.update(foto)  # jogada pela metade não fica na mesa
                raise
            self.desfazer.append(foto)
            del self.desfazer[:-MAX_DESFAZER]
            self._gravar()

    def _iid(self, pedido):
        iid = pedido.get("iid")
        if iid not in self.e["cartas"]:
            raise ErroJogada("carta inválida")
        return iid

    def _destino_valido(self, destino):
        if not isinstance(destino, str):
            raise ErroJogada("destino inválido")
        base = destino.split(":")[0]
        if base not in NOMES_ZONA:
            raise ErroJogada("destino inválido")
        if base == "anexos":
            alvo = destino.split(":", 1)[1]
            if alvo not in self.e["cartas"] or not self._onde(alvo).startswith(("regiao:", "retiro:")):
                raise ErroJogada("só se equipa um item numa unidade em jogo")
        elif destino not in self.e["zonas"]:
            raise ErroJogada("destino inválido")
        return destino

    def _op_mover(self, a, p):
        iid = self._iid(p)
        self._pode_mexer(iid, a)
        destino = self._destino_valido(p.get("destino"))
        topo = {"topo": True, "fundo": False}.get(p.get("onde"))
        origem = self._mover(iid, destino, topo)
        self._contar_entrada(iid, origem, destino, a)

    def _op_exaurir(self, a, p):
        iid = self._iid(p)
        self._pode_mexer(iid, a)
        c = self.e["cartas"][iid]
        c["exausta"] = not c["exausta"]
        self._log(f"{self._nome_jogador(a)} {'exauriu' if c['exausta'] else 'desvirou'} "
                  f"{self._nome_carta(iid)}.", a)

    def _op_virar(self, a, p):
        iid = self._iid(p)
        self._pode_mexer(iid, a)
        if not self.acervo().get(self.e["cartas"][iid]["id"], {}).get("nome_verso"):
            raise ErroJogada("esta carta não tem verso")
        c = self.e["cartas"][iid]
        antes = self._nome_carta(iid)
        c["verso"] = not c["verso"]
        self._log(f"{self._nome_jogador(a)} virou {antes} para {'a forma evoluída' if c['verso'] else 'a forma base'}"
                  f" ({self._nome_carta(iid)}).", a)

    def _op_marcador(self, a, p):
        iid = self._iid(p)
        self._pode_mexer(iid, a)
        c = self.e["cartas"][iid]
        c["marcador"] = max(0, c.get("marcador", 0) + int(p.get("delta", 0)))
        self._log(f"{self._nome_jogador(a)}: marcador de {self._nome_carta(iid)} em {c['marcador']}.", a)

    def _op_neutro(self, a, p):
        iid = self._iid(p)
        c = self.e["cartas"][iid]
        c["neutro"] = not c.get("neutro")
        self._log(f"{self._nome_jogador(a)} marcou {self._nome_carta(iid)} como "
                  f"{'inimigo neutro' if c['neutro'] else 'carta do dono'}.", a)

    def _comprar(self, a, n):
        jornada, mao = self._zona(f"jornada:{a}"), f"mao:{a}"
        comprou = 0
        for _ in range(n):
            if not jornada:
                break
            self._mover(jornada[0], mao)
            comprou += 1
        return comprou

    def _op_comprar(self, a, p):
        n = max(1, min(int(p.get("n", 1)), 20))
        comprou = self._comprar(a, n)
        extra = " (a Jornada acabou: comprar sem cartas não faz nada)" if comprou < n else ""
        self._log(f"{self._nome_jogador(a)} comprou {comprou} carta(s){extra}.", a)

    def _op_conto(self, a, p):
        j = self._jogador(a)
        mao = len(self._zona(f"mao:{a}"))
        if mao >= j["enredo"]:
            excesso = mao - j["enredo"]
            self._log(f"{j['nome']} está com {mao} cartas e enredo {j['enredo']}"
                      + (f": descarte {excesso} para o histórico." if excesso else "."), a)
            return
        comprou = self._comprar(a, j["enredo"] - mao)
        self._log(f"{j['nome']} comprou {comprou} no Conto (enredo {j['enredo']}).", a)

    def _op_embaralhar(self, a, p):
        random.shuffle(self._zona(f"jornada:{a}"))
        self._jogador(a)["espiar"] = 0
        self._log(f"{self._nome_jogador(a)} embaralhou a Jornada.", a)

    def _op_espiar(self, a, p):
        n = max(0, min(int(p.get("n", 0)), 10))
        self._jogador(a)["espiar"] = n
        if n:
            self._log(f"{self._nome_jogador(a)} olha {n} carta(s) do topo da Jornada.", a)

    def _op_dano(self, a, p):
        alvo = int(p.get("alvo", a))
        n = max(1, min(int(p.get("n", 1)), 60))
        j = self._jogador(alvo)
        jornada = self._zona(f"jornada:{alvo}")
        perdeu = 0
        for _ in range(n):
            if not jornada:
                break
            self._mover(jornada[0], f"historico:{alvo}")
            perdeu += 1
        texto = f"{self._nome_jogador(a)} aplicou {n} de dano ao protagonista de {j['nome']}: {perdeu} carta(s) da Jornada para o histórico."
        if perdeu < n:
            texto += " O dano passou do que havia na Jornada: o protagonista morre."
        self._log(texto, a)

    def _op_dano_cargas(self, a, p):
        alvo = int(p.get("alvo", a))
        runa = int(p.get("runa", 0))
        n = max(1, min(int(p.get("n", 1)), 60))
        cargas = self._zona(f"cargas:{alvo}:{runa}")
        perdeu = 0
        for _ in range(n):
            if not cargas:
                break
            self._mover(cargas[0], f"historico:{alvo}")
            perdeu += 1
        self._log(f"{self._nome_jogador(a)} mandou {perdeu} carga(s) da runa {runa + 1} de "
                  f"{self._nome_jogador(alvo)} para o histórico.", a)

    def _runa(self, a, p):
        i = int(p.get("runa", -1))
        runas = self._zona(f"runas:{a}")
        if not 0 <= i < len(runas):
            raise ErroJogada("runa inválida")
        return i, runas[i]

    def _fonte_carga(self, a, p):
        fonte = p.get("fonte")
        if fonte == "jornada":
            jornada = self._zona(f"jornada:{a}")
            if not jornada:
                raise ErroJogada("a Jornada está vazia")
            return jornada[0]
        if fonte not in self._zona(f"mao:{a}"):
            raise ErroJogada("escolha uma carta da sua mão")
        return fonte

    def _op_recarregar(self, a, p):
        i, runa = self._runa(a, p)
        carta = self._fonte_carga(a, p)
        de = "do topo da Jornada" if p.get("fonte") == "jornada" else "da mão"
        self._mover(carta, f"cargas:{a}:{i}")
        self.e["cartas"][runa]["exausta"] = False
        self._log(f"{self._nome_jogador(a)} recarregou {self._nome_carta(runa)} com 1 carta {de}.", a)

    def _op_carregar(self, a, p):
        i, runa = self._runa(a, p)
        if self.e["cartas"][runa]["exausta"]:
            raise ErroJogada("no Prólogo só se carrega uma runa não exaurida")
        carta = self._fonte_carga(a, p)
        self._mover(carta, f"cargas:{a}:{i}")
        self.e["cartas"][runa]["exausta"] = True
        comprou = self._comprar(a, 1)
        self._log(f"{self._nome_jogador(a)} carregou {self._nome_carta(runa)} no Prólogo, exauriu-a e comprou "
                  f"{comprou}.", a)

    def _op_jogar(self, a, p):
        iid = self._iid(p)
        if self._onde(iid) != f"mao:{a}":
            raise ErroJogada("só se joga uma carta da própria mão")
        self._mover(iid, "pilha", True)
        executor = p.get("executor")
        quem = f" (executor: {self._nome_carta(executor)})" if executor in self.e["cartas"] else ""
        self._log(f"{self._nome_jogador(a)} jogou {self._nome_carta(iid)}{quem}.", a)

    def _op_resolver(self, a, p):
        pilha = self._zona("pilha")
        if not pilha:
            raise ErroJogada("a pilha está vazia")
        iid = pilha[0]
        dono = self.e["cartas"][iid]["dono"]
        nome = self._nome_carta(iid)
        destino = f"historico:{dono}" if self._tipo(iid) == "acao" and dono is not None else "cemiterio"
        self._mover(iid, destino)
        self._log(f"{self._nome_jogador(a)} resolveu {nome} (→ {self._rotulo_zona(destino)}).", a)
        if not pilha:
            self._log("A pilha esvaziou: aplique agora todo o dano pendente.")

    def _op_puxar(self, a, p):
        iid = self._iid(p)
        if self._onde(iid) != f"eventos:{a}":
            raise ErroJogada("só se puxa do próprio deck de Eventos")
        tipo = self._tipo(iid)
        destino = p.get("destino")
        if not destino:
            destino = f"quests:{a}" if tipo == "quest" else f"regiao:{a}"
        destino = self._destino_valido(destino)
        if tipo == "item" and not destino.startswith("anexos:"):
            raise ErroJogada("um item puxado é equipado numa unidade: escolha o portador")
        self._mover(iid, destino, False)
        self._log(f"{self._nome_jogador(a)} puxou {self._nome_carta(iid)} do deck de Eventos "
                  f"({self._rotulo_zona(destino)}).", a)

    def _op_morrer(self, a, p):
        iid = self._iid(p)
        zona = self._onde(iid)
        if not zona.startswith(("regiao:", "retiro:")):
            raise ErroJogada("só uma unidade em jogo morre")
        nome = self._nome_carta(iid)
        c = self.e["cartas"][iid]
        if self._tipo(iid) == "protagonista":
            self._mover(iid, "fora")
            if c["dono"] is not None:
                self._jogador(c["dono"])["vivo"] = False
            self._log(f"{nome}, protagonista de {self._nome_jogador(c['dono'])}, morreu e saiu de jogo. "
                      "Distribuam os níveis pela morte (seção 9).", a)
            vivos = [j for j in self.e["jogadores"] if j.get("vivo")]
            if len(self.e["jogadores"]) > 1 and len(vivos) <= 1:
                self.e["etapa"] = "fim"
                self._log("Só resta um protagonista vivo (ou nenhum): o jogo termina na contagem de níveis.")
        else:
            self._mover(iid, "cemiterio")
            self._log(f"{nome} morreu e foi para o cemitério, com os itens que portava.", a)

    def _op_desvirar(self, a, p):
        n = 0
        for zona, lista in self.e["zonas"].items():
            if zona.startswith(("regiao:", "retiro:", "anexos:", "quests:", "campo:", "retiro_carta:")):
                for iid in lista:
                    c = self.e["cartas"][iid]
                    if c["dono"] == a and c["exausta"]:
                        c["exausta"] = False
                        n += 1
        exauridas = sum(1 for iid in self._zona(f"runas:{a}") if self.e["cartas"][iid]["exausta"])
        aviso = f" Recarregue as {exauridas} runa(s) exaurida(s)." if exauridas else ""
        self._log(f"{self._nome_jogador(a)} desvirou {n} carta(s) no Hiato.{aviso}", a)

    def _op_jogador(self, a, p):
        alvo = int(p.get("alvo", a))
        campo = p.get("campo")
        if campo not in ("nivel", "karma", "moedas"):
            raise ErroJogada("contador inválido")
        j = self._jogador(alvo)
        j[campo] = j.get(campo, 0) + int(p.get("delta", 0))
        if campo in ("nivel", "moedas"):
            j[campo] = max(0, j[campo])
        nomes = {"nivel": "nível", "karma": "karma", "moedas": "moedas"}
        self._log(f"{self._nome_jogador(a)}: {nomes[campo]} de {j['nome']} agora é {j[campo]}.", a)

    def _op_alinhamento(self, a, p):
        valor = p.get("valor")
        if valor not in KARMA_INICIAL:
            raise ErroJogada("alinhamento inválido")
        alvo = int(p.get("alvo", a))
        j = self._jogador(alvo)
        j["alinhamento"] = valor
        self._log(f"{self._nome_jogador(a)} mudou o alinhamento de {j['nome']} para {valor}.", a)

    def _vivos_na_ordem(self):
        t = self.e["turno"]
        return [x for x in t["ordem"] if self._jogador(x).get("vivo", True)]

    def _op_fase(self, a, p):
        t = self.e["turno"]
        if t["fase"] < len(FASES) - 1:
            t["fase"] += 1
            self._log(f"{self._nome_jogador(t['ordem'][t['vez']])}: {FASES[t['fase']]}.", a)
        else:
            self._op_passar(a, p)

    def _op_passar(self, a, p):
        t = self.e["turno"]
        if not self._vivos_na_ordem():
            raise ErroJogada("não há jogadores vivos")
        vez = t["vez"]
        while True:
            vez += 1
            if vez >= len(t["ordem"]):
                vez = 0
                self._fim_da_rodada()
            if self._jogador(t["ordem"][vez]).get("vivo", True):
                break
        t["vez"] = vez
        t["fase"] = SAGA if t["rodada"] == 1 else 0
        self._log(f"Turno de {self._nome_jogador(t['ordem'][vez])} (rodada {t['rodada']}, "
                  f"{FASES[t['fase']]}).", a)

    def _fim_da_rodada(self):
        t = self.e["turno"]
        # a contagem do Ato começa na rodada seguinte ao início do jogo: a 1ª rodada não conta
        if t["rodada"] >= 2 and not t["transicao"]:
            t["rodadas_ato"] += 1
            ato = self._zona("ato_atual")
            rodadas = self.acervo().get(self.e["cartas"][ato[0]]["id"], {}).get("rodadas") if ato else None
            if rodadas and t["rodadas_ato"] >= rodadas:
                t["transicao"] = True
                self._log(f"Acabaram as rodadas do ato {t['ato']}: façam a transição de ato "
                          "(os neutros ajustam o karma antes).")
        t["rodada"] += 1

    def _op_transicao(self, a, p):
        t = self.e["turno"]
        # 1. o Ato atual deixa de valer
        for iid in list(self._zona("ato_atual")):
            self._mover(iid, "atos_passados")
        # 2. alinhamento reavaliado pelo karma (os neutros ajustam o karma antes, pelos contadores)
        mudancas = []
        for j in self.e["jogadores"]:
            novo = "bom" if j.get("karma", 0) > 0 else "mau" if j.get("karma", 0) < 0 else "neutro"
            if novo != j.get("alinhamento"):
                mudancas.append(f"{j['nome']} agora é {novo}")
            j["alinhamento"] = novo
        t.update(transicao=False, rodadas_ato=0)
        if t["ato"] >= 3 or not self._zona("atos_ocultos"):
            self.e["etapa"] = "fim"
            self._log("Fim do ato 3: o jogo termina. Vence quem tem mais níveis.", a)
            return
        # 3. revela-se o próximo Ato
        t["ato"] += 1
        self._mover(self._zona("atos_ocultos")[0], "ato_atual")
        self._log(f"Transição de ato. Ato {t['ato']}: {self._nome_carta(self._zona('ato_atual')[0])}."
                  + (f" {'; '.join(mudancas)}." if mudancas else " Ninguém mudou de alinhamento."), a)

    def _op_revelar(self, a, p):
        iid = self._iid(p)
        if self._onde(iid) not in (f"mao:{a}", f"eventos:{a}", f"jornada:{a}"):
            raise ErroJogada("só se revela uma carta que é sua e está escondida")
        self._log(f"{self._nome_jogador(a)} revelou {self._nome_carta(iid)}.", a)
