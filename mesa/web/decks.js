// Deckbuilder: monta um deck com as cartas do acervo e confere as regras de construção
// (livro, seção 3) a cada mudança, pelo servidor (mesa/decks.py), que é quem a mesa também usa.

const TIPOS_FILTRO = ["protagonista", "campo", "retiro", "runa", "acao", "personagem", "item", "quest"];
const ORDEM_TIPO = { protagonista: 0, campo: 1, retiro: 2, runa: 3, acao: 4, personagem: 5, item: 6, quest: 7, ato: 8 };
const RASCUNHO = "lj-deck-rascunho";

const E = {
  deck: deckVazio(), arquivo: null, sujo: false, conf: null, pedido: 0, timer: null,
  filtroTipo: null, filtroElemento: null, busca: "", decks: [],
};

function deckVazio() {
  return { nome: "", protagonista: null, campo: null, retiro: null, runas: [null, null, null], jornada: {}, eventos: {} };
}

function copiasPermitidas(estrelas) {
  const e = Math.max(estrelas || 0, 1);
  return { 1: 4, 2: 3, 3: 2 }[e] || 1;
}

function guardarRascunho() {
  try { localStorage.setItem(RASCUNHO, JSON.stringify({ deck: E.deck, arquivo: E.arquivo, sujo: E.sujo })); } catch { /* sem armazenamento */ }
}

function marcar(sujo = true) {
  E.sujo = sujo;
  guardarRascunho();
  $("#estado-deck").textContent = E.sujo ? "não salvo" : (E.arquivo ? "salvo" : "");
  $("#estado-deck").className = E.sujo ? "aviso" : "dica";
  conferirDepois();
}

// ---------- conferência no servidor ----------

function conferirDepois() {
  clearTimeout(E.timer);
  E.timer = setTimeout(conferir, 150);
}

async function conferir() {
  const pedido = ++E.pedido;
  try {
    const r = await API.post("/api/decks/conferir", { deck: E.deck });
    if (pedido !== E.pedido) return;
    E.conf = r;
    // runas: as do elemento do protagonista, do campo e do retiro (mantém as escolhidas que servem)
    if (JSON.stringify(r.runas_sugeridas) !== JSON.stringify(E.deck.runas)) {
      E.deck.runas = r.runas_sugeridas;
      guardarRascunho();
      return conferir();
    }
  } catch (e) {
    avisar(e.message, "erro");
  }
  desenharDeck();
  desenharGrade();
}

// ---------- acervo ----------

function quantidadeNoDeck(id) {
  const d = E.deck;
  return (d.jornada[id] || 0) + (d.eventos[id] || 0) +
    [d.protagonista, d.campo, d.retiro, ...d.runas].filter(x => x === id).length;
}

function cartasFiltradas() {
  const busca = E.busca.trim().toLowerCase();
  return Object.entries(Acervo.cartas)
    .filter(([, c]) => !(c.erros && c.erros.length) && c.faces && c.faces.length)
    .filter(([, c]) => !E.filtroTipo || c.tipo === E.filtroTipo)
    .filter(([, c]) => !E.filtroElemento || (c.elementos || []).includes(E.filtroElemento))
    .filter(([, c]) => !busca || (c.busca || c.nome || "").toLowerCase().includes(busca))
    .sort(([, a], [, b]) => (ORDEM_TIPO[a.tipo] ?? 9) - (ORDEM_TIPO[b.tipo] ?? 9)
      || (a.estrelas || 0) - (b.estrelas || 0) || a.nome.localeCompare(b.nome));
}

function desenharFiltros() {
  const tipos = $("#filtro-tipo");
  tipos.replaceChildren(
    el("button", { class: "chip" + (!E.filtroTipo ? " ativo" : ""), onclick: () => { E.filtroTipo = null; desenharFiltros(); desenharGrade(); } }, "Todas"),
    ...TIPOS_FILTRO.map(t => el("button", {
      class: "chip" + (E.filtroTipo === t ? " ativo" : ""),
      onclick: () => { E.filtroTipo = E.filtroTipo === t ? null : t; desenharFiltros(); desenharGrade(); },
    }, NOME_TIPO[t])));
  $("#filtro-elemento").replaceChildren(...Object.keys(Acervo.elementos).map(k => el("button", {
    class: "chip" + (E.filtroElemento === k ? " ativo" : ""),
    onclick: () => { E.filtroElemento = E.filtroElemento === k ? null : k; desenharFiltros(); desenharGrade(); },
  }, el("span", { class: "bolinha", style: `background:${Acervo.cor(k)}` }), Acervo.nomeElemento(k))));
}

function desenharGrade() {
  const lista = cartasFiltradas();
  const grade = $("#grade");
  if (!lista.length) {
    grade.replaceChildren(el("div", { class: "vazio-acervo" },
      Object.keys(Acervo.cartas).length ? "Nenhuma carta com esses filtros." : "O acervo está vazio: crie cartas no criador (python app.py)."));
    return;
  }
  grade.replaceChildren(...lista.map(([id, c]) => {
    const n = quantidadeNoDeck(id);
    const fora = c.tipo === "ato";
    const item = el("div", {
      class: "item-acervo" + (fora ? " fora" : ""),
      title: fora ? "Cartas de Ato são da temporada: não entram em deck" : "Clique para pôr no deck; botão direito para tirar",
      onclick: () => adicionar(id),
      oncontextmenu: ev => { ev.preventDefault(); remover(id); },
    }, imagemCarta(id), n ? el("span", { class: "qtd" }, n) : null);
    ligarZoom(item, id);
    return item;
  }));
}

// ---------- mexer no deck ----------

function adicionar(id) {
  const c = Acervo.carta(id);
  const d = E.deck;
  if (!c) return;
  if (["protagonista", "campo", "retiro"].includes(c.tipo)) {
    d[c.tipo] = id;
  } else if (c.tipo === "runa") {
    const pedidos = (E.conf && E.conf.elementos_runas) || [];
    const i = pedidos.findIndex(e => (c.elementos || []).includes(e));
    if (i < 0) {
      return avisar(`As runas são dos elementos do protagonista, do campo e do retiro${pedidos.filter(Boolean).length ? ` (${pedidos.filter(Boolean).map(e => Acervo.nomeElemento(e)).join(", ")})` : ""}. ${c.nome} não serve.`, "erro");
    }
    d.runas[i] = id;
  } else if (c.tipo === "acao" || ["personagem", "item", "quest"].includes(c.tipo)) {
    const deck = c.tipo === "acao" ? d.jornada : d.eventos;
    const limite = copiasPermitidas(c.estrelas);
    if ((deck[id] || 0) >= limite) {
      return avisar(`${c.nome}: com ${c.estrelas || 0} estrela(s), o máximo é ${limite} cópia(s) por deck.`, "erro");
    }
    deck[id] = (deck[id] || 0) + 1;
  } else {
    return avisar("Cartas de Ato não entram em deck: o deck de Atos é da temporada, comum a todos.", "erro");
  }
  marcar();
  desenharGrade();
}

function remover(id) {
  const d = E.deck;
  for (const deck of [d.jornada, d.eventos]) {
    if (deck[id]) { deck[id]--; if (!deck[id]) delete deck[id]; marcar(); desenharGrade(); return; }
  }
  for (const k of ["protagonista", "campo", "retiro"]) if (d[k] === id) { d[k] = null; marcar(); desenharGrade(); return; }
}

// ---------- painel do deck ----------

function estrelas(n) { return n ? `${n}★` : "0★"; }

function slot(rotulo, id, aoLimpar, extra = null) {
  const c = id && Acervo.carta(id);
  const mini = el("div", { class: "mini" }, c ? imagemCarta(id) : el("div", { class: "verso-carta" }, ""));
  if (c) ligarZoom(mini, id);
  return el("div", { class: "slot" + (c ? "" : " vazio") },
    mini,
    el("div", {},
      el("div", { class: "rotulo" }, rotulo),
      el("div", { class: "nome" }, c ? c.nome : (id ? `${id} (fora do acervo)` : "clique numa carta do acervo")),
      c ? el("div", { class: "dica" }, bolinhas(c.elementos), c.tipo === "runa" ? "" : " " + estrelas(c.estrelas)) : null,
      extra),
    aoLimpar && id ? el("button", { class: "botao pequeno", title: "Tirar", onclick: aoLimpar }, "✕") : el("span"));
}

function slotRuna(i) {
  const d = E.deck;
  const pedido = E.conf && E.conf.elementos_runas ? E.conf.elementos_runas[i] : null;
  const origem = ["do protagonista", "do campo", "do retiro"][i];
  const opcoes = Object.entries(Acervo.cartas).filter(([, c]) => c.tipo === "runa" && !(c.erros || []).length
    && (c.elementos || []).includes(pedido));
  let extra = null;
  if (!pedido) extra = el("div", { class: "dica" }, `escolha antes o ${origem.slice(3)}`);
  else if (!opcoes.length) extra = el("div", { class: "erro" }, `não há runa de ${Acervo.nomeElemento(pedido)} no acervo`);
  else if (opcoes.length > 1) {
    extra = el("select", { onchange: ev => { d.runas[i] = ev.target.value; marcar(); } },
      ...opcoes.map(([k, c]) => el("option", { value: k, selected: d.runas[i] === k }, c.nome)));
  }
  const rotulo = `Runa ${origem}${pedido ? ` · ${Acervo.nomeElemento(pedido)}` : ""}`;
  return slot(rotulo, d.runas[i], null, extra);
}

function listaDeck(chave) {
  const deck = E.deck[chave];
  const ids = Object.keys(deck).sort((a, b) => {
    const ca = Acervo.carta(a) || {}, cb = Acervo.carta(b) || {};
    return (ORDEM_TIPO[ca.tipo] ?? 9) - (ORDEM_TIPO[cb.tipo] ?? 9) || (ca.estrelas || 0) - (cb.estrelas || 0)
      || (ca.nome || a).localeCompare(cb.nome || b);
  });
  if (!ids.length) return [el("div", { class: "dica" }, chave === "jornada"
    ? "Só ações. Clique numa ação do acervo." : "Personagens, itens e quests. Clique numa carta do acervo.")];
  return ids.map(id => {
    const c = Acervo.carta(id);
    const linha = el("div", { class: "linha-deck" },
      el("span", { class: "ctrl" },
        el("button", { class: "botao", onclick: () => remover(id), title: "Tirar uma" }, "−"),
        el("span", { class: "n" }, deck[id]),
        el("button", { class: "botao", onclick: () => adicionar(id), title: "Pôr mais uma" }, "+")),
      el("span", {}, c ? c.nome : `${id} (fora do acervo)`,
        c && chave === "eventos" ? el("span", { class: "dica" }, ` · ${NOME_TIPO[c.tipo]}${c.tipo === "quest" && c.ato ? ` ${["", "I", "II", "III"][c.ato]}` : ""}`) : null),
      el("span", { class: "info" }, c ? bolinhas(c.elementos) : null, " ", c ? estrelas((c.estrelas || 0) * deck[id]) : ""));
    if (c) ligarZoom(linha, id);
    return linha;
  });
}

function desenharDeck() {
  const d = E.deck, conf = E.conf || { estrelas: 0, orcamento: 100, erros: [], avisos: [], contagem: {} };
  const passou = conf.estrelas > conf.orcamento;
  const itens = [
    ...conf.erros.map(t => el("li", { class: "erro" }, t)),
    ...conf.avisos.map(t => el("li", { class: "aviso" }, t)),
  ];
  if (!conf.erros.length) itens.unshift(el("li", { class: "ok" }, "Deck dentro das regras de construção."));
  $("#deck").replaceChildren(
    el("div", { class: "medidor" },
      el("div", {}, el("span", { class: "valor" + (passou ? " passou" : "") }, conf.estrelas), el("span", { class: "dica" }, ` / ${conf.orcamento} estrelas`)),
      el("div", { class: "barra" }, el("div", { class: passou ? "passou" : "", style: `width:${Math.min(100, conf.estrelas / conf.orcamento * 100)}%` })),
      el("div", { class: "dica" }, "Protagonista, campo, retiro, Jornada e Eventos. Runas não custam estrelas.")),
    el("h2", {}, "Fora dos decks"),
    slot("Protagonista", d.protagonista, () => { d.protagonista = null; marcar(); }),
    slot("Campo de batalha", d.campo, () => { d.campo = null; marcar(); }),
    slot("Retiro", d.retiro, () => { d.retiro = null; marcar(); }),
    slotRuna(0), slotRuna(1), slotRuna(2),
    el("h2", {}, "Jornada", el("span", { class: "dica" }, `${conf.contagem.jornada || 0} carta(s) · embaralhada`)),
    ...listaDeck("jornada"),
    el("h2", {}, "Eventos", el("span", { class: "dica" }, `${conf.contagem.eventos || 0} carta(s) · na ordem montada`)),
    ...listaDeck("eventos"),
    el("h2", {}, "Conferência"),
    el("ul", { class: "conferencia" }, ...itens));
}

// ---------- abrir, salvar, apagar ----------

async function carregarListaDecks() {
  E.decks = await API.get("/api/decks");
  $("#abrir").replaceChildren(el("option", { value: "" }, "Abrir deck…"),
    ...E.decks.map(x => el("option", { value: x.arquivo }, x.nome)));
}

async function abrir(arquivo) {
  if (E.sujo && !confirm("O deck atual tem mudanças não salvas. Abrir outro mesmo assim?")) return;
  const d = await API.get("/api/deck?arquivo=" + encodeURIComponent(arquivo));
  if (d.erro) return avisar(d.erro, "erro");
  E.deck = { ...deckVazio(), ...d, runas: [...(d.runas || []), null, null, null].slice(0, 3) };
  E.arquivo = arquivo;
  $("#nome").value = E.deck.nome;
  marcar(false);
}

async function salvar() {
  E.deck.nome = $("#nome").value.trim();
  if (!E.deck.nome) { $("#nome").focus(); return avisar("Dê um nome ao deck antes de salvar.", "erro"); }
  try {
    const r = await API.post("/api/decks/salvar", { deck: E.deck });
    const outro = E.decks.find(x => x.arquivo === r.arquivo);
    if (outro && outro.arquivo !== E.arquivo && !confirm(`Já existe o deck "${outro.nome}" com esse nome. Substituir?`)) return;
    E.arquivo = r.arquivo;
    marcar(false);
    await carregarListaDecks();
    avisar(`Deck salvo em decks/${r.arquivo}.json.`, "ok");
    if (E.conf && E.conf.erros.length) avisar("Atenção: o deck tem erros e não pode ser usado na mesa até corrigir.", "erro");
  } catch (e) { avisar(e.message, "erro"); }
}

async function apagar() {
  if (!E.arquivo) return avisar("Este deck ainda não foi salvo.");
  if (!confirm(`Apagar o deck "${E.deck.nome || E.arquivo}" de decks/?`)) return;
  await API.post("/api/decks/apagar", { arquivo: E.arquivo });
  E.arquivo = null;
  marcar(true);
  await carregarListaDecks();
  avisar("Deck apagado.");
}

function novo() {
  if (E.sujo && !confirm("O deck atual tem mudanças não salvas. Começar outro mesmo assim?")) return;
  E.deck = deckVazio();
  E.arquivo = null;
  $("#nome").value = "";
  marcar(false);
}

// ---------- início ----------

async function iniciar() {
  await Acervo.carregar();
  try {
    const r = JSON.parse(localStorage.getItem(RASCUNHO) || "null");
    if (r && r.deck) { E.deck = { ...deckVazio(), ...r.deck }; E.arquivo = r.arquivo; E.sujo = r.sujo; }
  } catch { /* sem rascunho */ }
  $("#nome").value = E.deck.nome || "";
  $("#nome").oninput = () => { E.deck.nome = $("#nome").value; marcar(); };
  $("#busca").oninput = () => { E.busca = $("#busca").value; desenharGrade(); };
  $("#abrir").onchange = ev => { if (ev.target.value) abrir(ev.target.value); ev.target.value = ""; };
  $("#novo").onclick = novo;
  $("#salvar").onclick = salvar;
  $("#apagar").onclick = apagar;
  document.addEventListener("keydown", ev => { if ((ev.ctrlKey || ev.metaKey) && ev.key === "s") { ev.preventDefault(); salvar(); } });
  desenharFiltros();
  marcar(E.sujo);
  await carregarListaDecks();
  ouvirMudancas("", d => acompanharAcervo(d.acervo, () => { desenharFiltros(); desenharGrade(); conferir(); }));
}
iniciar();
