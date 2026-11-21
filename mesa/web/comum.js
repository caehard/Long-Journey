// Peças comuns ao deckbuilder e à mesa: API, acervo, zoom, avisos, menus e eventos ao vivo.

const $ = s => document.querySelector(s);

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "style") e.style.cssText = v;
    else if (k.startsWith("on")) e[k] = v;
    else if (k === "dados") Object.assign(e.dataset, v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const f of filhos.flat()) if (f != null && f !== false) e.append(f);
  return e;
}

const API = {
  async get(url) {
    const r = await fetch(url, { cache: "no-store" });
    return r.json();
  },
  async post(url, corpo = {}) {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
    const j = await r.json().catch(() => ({ erro: `erro ${r.status}` }));
    if (!r.ok || j.erro) throw new Error(j.erro || `erro ${r.status}`);
    return j;
  },
};

// ---------- acervo (as cartas exportadas de cards/) ----------

const Acervo = {
  cartas: {}, elementos: {}, versao: null, erro: null,
  async carregar() {
    const j = await API.get("/api/acervo");
    const antes = this.cartas;
    this.cartas = j.cartas || {};
    this.elementos = j.elementos || {};
    this.versao = j.versao;
    this.erro = j.erro;
    // o que mudou desde a última carga (para avisar "carta nova" / "carta atualizada")
    const novas = [], alteradas = [];
    if (Object.keys(antes).length) {
      for (const [k, c] of Object.entries(this.cartas)) {
        if (!antes[k]) novas.push(c.nome || k);
        else if (antes[k].assinatura !== c.assinatura) alteradas.push(c.nome || k);
      }
    }
    return { novas, alteradas };
  },
  carta(id) { return this.cartas[id]; },
  nome(id, verso = false) {
    const c = this.cartas[id];
    if (!c) return id;
    return verso && c.nome_verso ? c.nome_verso : c.nome;
  },
  img(id, verso = false) {
    const c = this.cartas[id];
    if (!c || !c.faces || !c.faces.length) return null;
    return "/acervo/" + c.faces[verso && c.faces.length > 1 ? 1 : 0];
  },
  cor(elemento) { return (this.elementos[elemento] || {}).cor || "#888"; },
  nomeElemento(elemento) { return (this.elementos[elemento] || {}).nome || elemento; },
};

const NOME_TIPO = { acao: "Ação", protagonista: "Protagonista", personagem: "Personagem", item: "Item",
  campo: "Campo de batalha", retiro: "Retiro", runa: "Runa", quest: "Quest", ato: "Ato" };

function bolinhas(elementos) {
  return el("span", { class: "bolinhas" }, ...(elementos || []).map(e =>
    el("span", { class: "bolinha", title: Acervo.nomeElemento(e), style: `background:${Acervo.cor(e)}` })));
}

// imagem de uma carta (ou o verso genérico, se escondida ou sem imagem)
function imagemCarta(id, verso = false, rotulo = "") {
  const src = id ? Acervo.img(id, verso) : null;
  if (src) return el("img", { class: "carta-img", src, alt: Acervo.nome(id, verso), draggable: "false", loading: "lazy" });
  return el("div", { class: "verso-carta" }, rotulo || (id ? Acervo.nome(id, verso) : "Long\nJourney"));
}

// ---------- zoom ----------

function ligarZoom(alvo, id, verso = false) {
  if (!id) return;
  alvo.addEventListener("mouseenter", ev => mostrarZoom(id, verso, ev));
  alvo.addEventListener("mousemove", ev => posicionarZoom(ev));
  alvo.addEventListener("mouseleave", esconderZoom);
}
function mostrarZoom(id, verso, ev) {
  const src = Acervo.img(id, verso);
  if (!src) return;
  let z = $("#zoom");
  if (!z) { z = el("div", { id: "zoom" }, el("img")); document.body.append(z); }
  z.querySelector("img").src = src;
  z.style.display = "block";
  posicionarZoom(ev);
}
function posicionarZoom(ev) {
  const z = $("#zoom");
  if (!z || z.style.display !== "block") return;
  const w = 315, h = 440, m = 18;
  let x = ev.clientX + m, y = ev.clientY - h / 2;
  if (x + w > innerWidth - 8) x = ev.clientX - w - m;
  y = Math.max(8, Math.min(y, innerHeight - h - 8));
  z.style.left = x + "px"; z.style.top = y + "px";
}
function esconderZoom() { const z = $("#zoom"); if (z) z.style.display = "none"; }

// ---------- avisos ----------

function avisar(texto, tipo = "") {
  let caixa = $("#avisos");
  if (!caixa) { caixa = el("div", { id: "avisos" }); document.body.append(caixa); }
  const t = el("div", { class: `toast ${tipo}` }, texto);
  caixa.append(t);
  setTimeout(() => t.remove(), tipo === "erro" ? 6000 : 3500);
}

// ---------- menu de contexto ----------
// itens: [{rotulo, acao}] | {rotulo, itens:[...]} (submenu) | "-" (separador) | {titulo}

function abrirMenu(ev, itens) {
  ev.preventDefault();
  fecharMenu();
  esconderZoom();
  const montar = lista => el("div", { class: "menu" }, ...lista.filter(Boolean).map(it => {
    if (it === "-") return el("hr");
    if (it.titulo) return el("div", { class: "titulo" }, it.titulo);
    if (it.itens) return el("div", { class: "sub" }, el("button", {}, it.rotulo), montar(it.itens));
    return el("button", { onclick: () => { fecharMenu(); it.acao(); } }, it.rotulo);
  }));
  const m = montar(itens);
  m.id = "menu-contexto";
  document.body.append(m);
  const r = m.getBoundingClientRect();
  m.style.left = Math.min(ev.clientX, innerWidth - r.width - 8) + "px";
  m.style.top = Math.min(ev.clientY, innerHeight - r.height - 8) + "px";
}
function fecharMenu() { const m = $("#menu-contexto"); if (m) m.remove(); }
document.addEventListener("click", ev => { if (!ev.target.closest(".menu")) fecharMenu(); });
document.addEventListener("keydown", ev => { if (ev.key === "Escape") { fecharMenu(); fecharModal(); } });

// ---------- janela ----------

function abrirModal(titulo, ...conteudo) {
  fecharModal();
  const fundo = el("div", { class: "fundo-modal", id: "modal", onclick: ev => { if (ev.target === fundo) fecharModal(); } },
    el("div", { class: "modal" },
      el("header", {}, el("h3", {}, titulo), el("span", { class: "espaco" }),
        el("button", { class: "botao pequeno", onclick: fecharModal }, "Fechar")),
      el("div", { class: "conteudo" }, ...conteudo)));
  document.body.append(fundo);
  return fundo;
}
function fecharModal() { const m = $("#modal"); if (m) m.remove(); }

// ---------- eventos ao vivo ----------
// Avisa quando a partida ou o acervo mudam (o servidor manda {versao, acervo}).

function ouvirMudancas(token, aoMudar) {
  let fonte;
  const abrir = () => {
    fonte = new EventSource("/api/eventos?token=" + encodeURIComponent(token || ""));
    fonte.addEventListener("mudou", ev => aoMudar(JSON.parse(ev.data)));
    fonte.onerror = () => { fonte.close(); setTimeout(abrir, 1500); };
  };
  abrir();
}

// recarrega o acervo quando a versão muda e avisa o que entrou
async function acompanharAcervo(versao, aoAtualizar) {
  if (versao == null || versao === Acervo.versao) return false;
  const { novas, alteradas } = await Acervo.carregar();
  for (const n of novas) avisar(`Carta nova no acervo: ${n}`, "ok");
  if (alteradas.length) avisar(`Atualizada: ${alteradas.slice(0, 3).join(", ")}${alteradas.length > 3 ? "…" : ""}`);
  aoAtualizar && aoAtualizar();
  return true;
}
