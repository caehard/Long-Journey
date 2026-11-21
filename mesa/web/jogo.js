// Mesa: sala de espera e partida. O servidor guarda o estado e esconde o que cada jogador não vê;
// esta página desenha a visão recebida e manda as jogadas (mover, exaurir, comprar...).

const CHAVE_TOKEN = "lj-mesa-token";
const S = { token: null, v: null, decks: [], arrastando: null, modal: null, buscando: false, de_novo: false };
const ROMANO = ["", "I", "II", "III"];
const ALINHAMENTOS = ["bom", "mau", "neutro"];

// cada aba é um jogador (sessionStorage); o localStorage lembra o último para "continuar"
function lerToken() {
  try { return sessionStorage.getItem(CHAVE_TOKEN); } catch { return null; }
}
function ultimoToken() {
  try { return localStorage.getItem(CHAVE_TOKEN); } catch { return null; }
}
function guardarToken(t) {
  S.token = t;
  try { sessionStorage.setItem(CHAVE_TOKEN, t); localStorage.setItem(CHAVE_TOKEN, t); } catch { /* sem armazenamento */ }
}

// ---------- comunicação ----------

async function atualizar() {
  if (S.buscando) { S.de_novo = true; return; }
  S.buscando = true;
  try {
    S.v = await API.get("/api/estado?token=" + encodeURIComponent(S.token || ""));
    if (S.token && !S.v.nome) { S.token = null; S.v = null; }
    desenhar();
  } catch (e) {
    avisar("Sem conexão com a mesa: " + e.message, "erro");
  } finally {
    S.buscando = false;
    if (S.de_novo) { S.de_novo = false; atualizar(); }
  }
}

async function acao(op, dados = {}) {
  try {
    await API.post("/api/acao", { token: S.token, op, ...dados });
    atualizar();
  } catch (e) { avisar(e.message, "erro"); }
}

async function pedido(url, dados = {}) {
  try {
    await API.post(url, { token: S.token, ...dados });
    atualizar();
    return true;
  } catch (e) { avisar(e.message, "erro"); return false; }
}

const mover = (iid, destino, onde = null) => acao("mover", { iid, destino, onde });

function pedirNumero(texto, padrao = 1) {
  const r = prompt(texto, String(padrao));
  if (r == null) return null;
  const n = parseInt(r, 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

// ---------- leitura da visão ----------

const Z = nome => (S.v.zonas && S.v.zonas[nome]) || [];
const eu = () => S.v.eu;
const jogador = a => S.v.jogadores.find(j => j.assento === a);
const nomeJ = a => (jogador(a) || {}).nome || "?";
const corJ = a => (jogador(a) || {}).cor || "#888";
const tipoDe = cv => (cv && cv.id && (Acervo.carta(cv.id) || {}).tipo) || "";

function ordemPaineis() {
  const t = S.v.turno;
  const ordem = t ? [...t.ordem] : S.v.jogadores.map(j => j.assento);
  const i = ordem.indexOf(eu());
  return i < 0 ? ordem : [...ordem.slice(i), ...ordem.slice(0, i)];
}

function unidadesDe(a) {
  // as unidades de A em jogo, em qualquer região ou retiro
  const saida = [];
  for (const [nome, lista] of Object.entries(S.v.zonas)) {
    if (!/^(regiao|retiro):/.test(nome)) continue;
    for (const cv of lista) if (cv.dono === a) saida.push(cv);
  }
  return saida;
}

// ---------- desenho ----------

function desenhar() {
  const raiz = $("#raiz");
  $("#quem").textContent = S.v && S.v.nome ? `Você: ${S.v.nome}${S.v.eu == null ? " (assistindo)" : ""}` : "";
  if (!S.token || !S.v) return raiz.replaceChildren(telaEntrada());
  if (S.v.etapa === "sala") return raiz.replaceChildren(telaSala());
  raiz.replaceChildren(barraTurno(), el("div", { class: "jogo" }, tabuleiro(), lateral()), eu() != null ? areaMao() : null);
  if (S.modal) desenharModal();
  const log = $(".linhas-log");
  if (log) log.scrollTop = log.scrollHeight;
}

// ----- entrada -----

function telaEntrada() {
  const nome = el("input", { type: "text", placeholder: "Seu nome", maxlength: 24 });
  const entrar = async (token = null) => {
    try {
      const r = await API.post("/api/entrar", { nome: nome.value || "Jogador", token });
      guardarToken(r.token);
      ouvir();
      atualizar();
    } catch (e) { avisar(e.message, "erro"); }
  };
  nome.onkeydown = ev => { if (ev.key === "Enter") entrar(); };
  const ultimo = ultimoToken();
  setTimeout(() => nome.focus(), 0);
  return el("div", { class: "centro" },
    el("div", { class: "cartao" },
      el("h2", {}, "Entrar na mesa"),
      el("div", { class: "form-linha" }, nome, el("button", { class: "botao principal", onclick: () => entrar() }, "Entrar")),
      ultimo ? el("p", { class: "dica" }, "Já estava na mesa neste navegador? ",
        el("button", { class: "botao pequeno", onclick: () => { guardarToken(ultimo); ouvir(); atualizar(); } }, "Continuar de onde parei")) : null,
      el("p", { class: "dica" }, "Cada aba é um jogador: para testar sozinho, abra outra aba e entre com outro nome.")));
}

// ----- sala -----

function telaSala() {
  const v = S.v;
  const meu = jogador(v.eu);
  const deck = el("select", {}, el("option", { value: "" }, "Escolha um deck…"),
    ...S.decks.map(d => el("option", { value: d.arquivo, selected: meu && meu.deck === d.arquivo }, d.nome)));
  const al = el("select", {}, ...ALINHAMENTOS.map(a => el("option", { value: a, selected: meu ? meu.alinhamento === a : a === "neutro" }, a)));
  return el("div", { class: "centro" },
    el("div", { class: "cartao" },
      el("h2", {}, "À mesa"),
      v.jogadores.length ? el("ul", { class: "sentados" }, ...v.jogadores.map(j => el("li", {},
        el("span", { class: "ponto", style: `background:${j.cor}` }),
        el("strong", {}, j.nome), el("span", { class: "dica" }, j.deck_nome),
        el("span", { class: `selo-al ${j.alinhamento}` }, j.alinhamento))))
        : el("p", { class: "dica" }, "Ninguém sentou ainda.")),
    el("div", { class: "cartao" },
      el("h2", {}, meu ? "Seu lugar" : "Sentar à mesa"),
      el("div", { class: "form-linha" },
        deck, el("span", { class: "dica" }, "alinhamento inicial:"), al,
        el("button", { class: "botao principal", onclick: () => {
          if (!deck.value) return avisar("Escolha um deck.", "erro");
          pedido("/api/sentar", { deck: deck.value, alinhamento: al.value });
        } }, meu ? "Atualizar" : "Sentar"),
        meu ? el("button", { class: "botao", onclick: () => pedido("/api/levantar") }, "Levantar") : null),
      el("p", { class: "dica" }, "Os decks vêm de decks/. ", el("a", { href: "/decks" }, "Montar um deck"),
        ". O karma inicial segue o alinhamento (bom +1, mau −1, neutro 0).")),
    el("div", { class: "cartao" },
      el("h2", {}, "Começar"),
      el("p", { class: "dica" }, "A preparação é automática (livro, seção 4): protagonistas nas regiões dos próprios campos, ",
        "campo, retiro e runas em jogo, Jornadas embaralhadas, mão igual ao enredo, 3 Atos sorteados das cartas de Ato do acervo, ",
        "primeiro jogador sorteado. A primeira rodada começa na Saga."),
      el("button", { class: "botao principal", disabled: !v.jogadores.length, onclick: () => pedido("/api/comecar") }, "Começar partida")),
    painelLog());
}

// ----- barra do turno -----

function barraTurno() {
  const v = S.v, t = v.turno || {};
  const ato = Z("ato_atual")[0];
  const cartaAto = ato && Acervo.carta(ato.id);
  const rodadas = cartaAto && cartaAto.rodadas;
  const vez = t.ordem ? t.ordem[t.vez] : null;
  const contagem = t.rodada === 1 ? "começa a contar na rodada 2" : `${t.rodadas_ato || 0}/${rodadas || "?"} rodadas`;
  const fim = v.etapa === "fim";
  return el("div", { class: "barra-turno" },
    el("strong", {}, `Ato ${ROMANO[t.ato] || t.ato}`), el("span", {}, cartaAto ? cartaAto.nome : "sem carta de Ato"),
    el("span", { class: "dica" }, contagem),
    el("span", {}, `Rodada ${t.rodada}`),
    vez != null ? el("span", {}, "Vez de ", el("strong", { style: `color:${corJ(vez)}` }, nomeJ(vez))) : null,
    el("span", { class: "fases" }, ...v.fases.map((f, i) => el("span", { class: i === t.fase ? "ativa" : "" }, f))),
    fim ? el("span", { class: "fim" }, "Fim de jogo: vence quem tem mais níveis") : null,
    el("span", { class: "espaco" }),
    el("button", { class: "botao pequeno", onclick: () => acao("fase") }, "Próxima fase"),
    el("button", { class: "botao pequeno", onclick: () => acao("passar") }, "Passar turno"),
    el("button", { class: "botao pequeno" + (t.transicao ? " transicao" : ""), title: "Fim das rodadas do Ato: alinhamento pelo karma e próximo Ato",
      onclick: () => { if (t.transicao || confirm("As rodadas deste Ato ainda não acabaram. Fazer a transição mesmo assim?")) acao("transicao"); } }, "Transição de ato"),
    el("button", { class: "botao pequeno", disabled: !v.pode_desfazer, onclick: () => acao("desfazer") }, "Desfazer"),
    el("button", { class: "botao pequeno", onclick: () => { if (confirm("Encerrar a partida e voltar à sala?")) pedido("/api/encerrar"); } }, "Encerrar"));
}

// ----- cartas -----

function podeArrastar(cv, zona) {
  if (cv.oculta || eu() == null) return false;
  return !/^(campo|retiro_carta|runas|ato_atual|atos_)/.test(zona);
}

function cartaEl(cv, zona, extra = {}) {
  const visivel = !cv.oculta && cv.id;
  const classes = ["carta"];
  if (cv.exausta) classes.push("exausta");
  if (cv.neutro) classes.push("neutro");
  else if (extra.corDono) classes.push("dono");
  const d = el("div", {
    class: classes.join(" "), dados: { iid: cv.iid, zona },
    style: extra.corDono ? `--cor-dono:${corJ(cv.dono)}` : null,
  },
  el("div", { class: "face" }, imagemCarta(visivel ? cv.id : null, cv.verso, extra.rotulo || "Long Journey")),
  cv.marcador ? el("span", { class: "selo marcador", title: "marcador (dano pendente ou o que combinarem)" }, cv.marcador) : null,
  cv.neutro ? el("span", { class: "selo rotulo" }, "neutro") : null,
  extra.cargas != null ? el("span", { class: "selo cargas" }, `${extra.cargas} carga${extra.cargas === 1 ? "" : "s"}`) : null,
  extra.qtd != null ? el("span", { class: "selo qtd" }, extra.qtd) : null);
  if (visivel) ligarZoom(d, cv.id, cv.verso);
  if (extra.aoClicar !== false) {
    const abrir = ev => { ev.stopPropagation(); extra.aoClicar ? extra.aoClicar(ev) : menuCarta(ev, cv, zona); };
    d.onclick = abrir;
    d.oncontextmenu = abrir;
  }
  if (podeArrastar(cv, zona) && extra.arrastar !== false) {
    d.draggable = true;
    d.ondragstart = ev => {
      S.arrastando = { iid: cv.iid, zona, tipo: tipoDe(cv) };
      ev.dataTransfer.setData("text/plain", cv.iid);
      ev.dataTransfer.effectAllowed = "move";
      esconderZoom();
      setTimeout(() => d.classList.add("arrastando"), 0);
    };
    d.ondragend = () => { S.arrastando = null; d.classList.remove("arrastando"); };
  }
  if (extra.aoSoltar) soltarEm(d, extra.aoSoltar);
  return d;
}

// alvo de arrastar e soltar: uma zona (mover para ela) ou uma função própria
function soltarEm(alvo, aoSoltar) {
  alvo.addEventListener("dragover", ev => { if (S.arrastando) { ev.preventDefault(); ev.stopPropagation(); alvo.classList.add("alvo"); } });
  alvo.addEventListener("dragleave", () => alvo.classList.remove("alvo"));
  alvo.addEventListener("drop", ev => {
    ev.preventDefault(); ev.stopPropagation();
    alvo.classList.remove("alvo");
    const a = S.arrastando;
    S.arrastando = null;
    if (a) aoSoltar(a);
  });
}
function zonaAlvo(alvo, destino, onde = null) {
  soltarEm(alvo, a => { if (a.zona !== destino || onde) mover(a.iid, destino, onde); });
  return alvo;
}

function zona(rotulo, destino, conteudo, { larga = false, extraRotulo = null, onde = null } = {}) {
  const z = el("div", { class: "zona" + (larga ? " larga" : "") },
    el("div", { class: "rotulo-z" }, el("span", {}, rotulo), extraRotulo),
    el("div", { class: "cartas" }, ...conteudo));
  return destino ? zonaAlvo(z, destino, onde) : z;
}

// unidade com os itens equipados embaixo; aceita item arrastado (equipar)
function unidadeEl(cv, nomeZona) {
  const anexos = Z("anexos:" + cv.iid);
  const carta = cartaEl(cv, nomeZona, {
    corDono: true,
    aoSoltar: a => {
      if (a.tipo === "item") mover(a.iid, "anexos:" + cv.iid);
      else if (a.zona !== nomeZona) mover(a.iid, nomeZona);
    },
  });
  return el("div", { class: "unidade" }, carta,
    anexos.length ? el("div", { class: "anexos" }, ...anexos.map(it => cartaEl(it, "anexos:" + cv.iid))) : null);
}

// ----- painel de um jogador -----

function contador(rotulo, campo, j) {
  return el("span", { class: "contador", title: rotulo },
    el("span", { class: "dica" }, rotulo),
    el("button", { onclick: () => acao("jogador", { alvo: j.assento, campo, delta: -1 }) }, "−"),
    el("b", {}, j[campo] ?? 0),
    el("button", { onclick: () => acao("jogador", { alvo: j.assento, campo, delta: 1 }) }, "+"));
}

function pilhaEl(lista, nomeZona, rotulo, aoClicar, { mostrarTopo = false } = {}) {
  if (!lista.length) {
    const vazio = el("div", { class: "carta vazia", title: rotulo }, el("div", { class: "face" }, "vazia"));
    if (aoClicar) vazio.onclick = vazio.oncontextmenu = ev => { ev.preventDefault(); ev.stopPropagation(); aoClicar(ev); };
    return vazio;
  }
  const topo = lista[0];
  const cv = mostrarTopo ? topo : { iid: topo.iid, oculta: true };
  return cartaEl(cv, nomeZona, { qtd: lista.length, rotulo, aoClicar, arrastar: mostrarTopo });
}

function painel(a) {
  const j = jogador(a);
  const t = S.v.turno || {};
  const meu = a === eu();
  const mao = Z("mao:" + a), jornada = Z("jornada:" + a), eventos = Z("eventos:" + a), historico = Z("historico:" + a);
  const vez = t.ordem && t.ordem[t.vez] === a;
  const runas = Z("runas:" + a);
  const espiadas = meu ? jornada.filter(c => !c.oculta) : [];

  const cab = el("div", { class: "cab" },
    el("span", { class: "nome-j" }, j.nome), el("span", { class: "dica" }, j.deck_nome),
    meu ? el("span", { class: "contador" }, el("select", { onchange: ev => acao("alinhamento", { valor: ev.target.value }) },
      ...ALINHAMENTOS.map(x => el("option", { value: x, selected: j.alinhamento === x }, x))))
      : el("span", { class: `selo-al ${j.alinhamento}` }, j.alinhamento),
    contador("Nível", "nivel", j), contador("Karma", "karma", j), contador("Moedas", "moedas", j),
    el("span", { class: "dica" }, `Mão ${mao.length} · Jornada ${jornada.length} · enredo ${j.enredo}`),
    j.vivo === false ? el("strong", { class: "erro" }, "protagonista morto") : null);

  const campo = Z("campo:" + a).map(cv => cartaEl(cv, "campo:" + a));
  const retiroCarta = Z("retiro_carta:" + a).map(cv => cartaEl(cv, "retiro_carta:" + a));
  const regiao = zona(`Região de ${j.nome}`, "regiao:" + a,
    [...campo, ...Z("regiao:" + a).map(cv => unidadeEl(cv, "regiao:" + a))], { larga: true });
  const retiro = zona(`Retiro de ${j.nome}`, "retiro:" + a,
    [...retiroCarta, ...Z("retiro:" + a).map(cv => unidadeEl(cv, "retiro:" + a))], { larga: true });

  const runasEl = zona("Runas", null, runas.map((cv, i) => cartaEl(cv, "runas:" + a, {
    cargas: Z(`cargas:${a}:${i}`).length,
    aoClicar: ev => menuRuna(ev, cv, a, i),
    aoSoltar: arr => {
      if (!meu || arr.zona !== "mao:" + a) return avisar("Arraste uma carta da sua mão para a sua runa.", "erro");
      acao(cv.exausta ? "recarregar" : "carregar", { runa: i, fonte: arr.iid });
    },
  })), { extraRotulo: el("span", {}, "soltar carta: exaurida recarrega, pronta carrega") });

  const jornadaEl = zona("Jornada", "jornada:" + a,
    [pilhaEl(jornada, "jornada:" + a, "Jornada", ev => menuJornada(ev, a)),
      espiadas.length ? el("div", { class: "espiadas", title: "o topo que você está olhando" },
        ...espiadas.map(cv => cartaEl(cv, "jornada:" + a))) : null], { onde: "topo" });
  const eventosEl = zona("Eventos", "eventos:" + a,
    [pilhaEl(eventos, "eventos:" + a, "Eventos", ev => meu ? abrirPilha("Seu deck de Eventos", "eventos:" + a)
      : avisar(`Deck de Eventos de ${j.nome}: ${eventos.length} carta(s).`))], { onde: "fundo" });
  const historicoEl = zona("Histórico", "historico:" + a,
    [pilhaEl(historico, "historico:" + a, "Histórico", () => abrirPilha(`Histórico de ${j.nome}`, "historico:" + a), { mostrarTopo: true })]);
  const quests = zona("Quests", "quests:" + a, Z("quests:" + a).map(cv => cartaEl(cv, "quests:" + a)), { larga: true });

  return el("div", { class: "painel" + (j.vivo === false ? " morto" : "") + (vez ? " vez" : ""), style: `--cor:${j.cor}` },
    cab,
    el("div", { class: "linha-zonas" }, regiao, retiro),
    el("div", { class: "linha-zonas", style: "margin-top:10px" }, runasEl, jornadaEl, eventosEl, historicoEl, quests));
}

function tabuleiro() {
  return el("div", { class: "tabuleiro" }, ...ordemPaineis().filter(a => jogador(a)).map(painel));
}

// ----- lateral: Ato, pilha, cemitério, log -----

function lateral() {
  const ato = Z("ato_atual");
  const pilha = Z("pilha");
  const cemiterio = Z("cemiterio");
  const passados = Z("atos_passados");
  return el("aside", { class: "lateral" },
    el("section", {},
      el("h3", {}, "Ato atual", el("span", { class: "dica" }, `${Z("atos_ocultos").length} por revelar`)),
      el("div", { class: "cartas", style: "--carta-l:126px;--carta-a:176px" }, ...ato.map(cv => cartaEl(cv, "ato_atual", { aoClicar: false })),
        passados.length ? el("div", { class: "cartas", style: "--carta-l:44px;--carta-a:62px;min-height:0", title: "Atos passados" },
          ...passados.map(cv => cartaEl(cv, "atos_passados", { aoClicar: false }))) : null)),
    zonaAlvo(el("section", {},
      el("h3", {}, "Pilha", pilha.length ? el("button", { class: "botao pequeno", onclick: () => acao("resolver") }, "Resolver o topo") : null),
      pilha.length ? el("div", { class: "cartas" }, ...pilha.map((cv, i) => cartaEl(cv, "pilha", { qtd: i === 0 ? "topo" : null })))
        : el("div", { class: "dica" }, "vazia (arraste uma carta para cá ou use Jogar)")), "pilha", "topo"),
    zonaAlvo(el("section", {},
      el("h3", {}, "Cemitério", el("span", { class: "dica" }, `${cemiterio.length} carta(s), comum`)),
      el("div", { class: "cartas", style: "min-height:0" },
        pilhaEl(cemiterio, "cemiterio", "Cemitério", () => abrirPilha("Cemitério (comum a todos)", "cemiterio"), { mostrarTopo: true }))), "cemiterio"),
    painelLog());
}

function painelLog() {
  const entrada = el("input", { type: "text", placeholder: "Mensagem para a mesa…", maxlength: 300 });
  entrada.onkeydown = ev => {
    if (ev.key === "Enter" && entrada.value.trim()) { acao("chat", { texto: entrada.value }); entrada.value = ""; }
  };
  return el("section", { class: "log cartao" },
    el("h3", {}, "Registro"),
    el("div", { class: "linhas-log" }, ...(S.v.log || []).map(l => el("div", { class: l.quem === eu() && l.quem != null ? "minha" : "" }, l.texto))),
    entrada);
}

// ----- mão -----

function areaMao() {
  const a = eu();
  const mao = Z("mao:" + a);
  const j = jogador(a);
  return zonaAlvo(el("div", { class: "mao" },
    el("div", { class: "acoes" },
      el("h3", {}, `Sua mão (${mao.length}/${j.enredo})`),
      el("button", { class: "botao pequeno", onclick: () => acao("comprar", { n: 1 }) }, "Comprar 1"),
      el("button", { class: "botao pequeno", title: "Conto: compra até o enredo", onclick: () => acao("conto") }, "Conto"),
      el("button", { class: "botao pequeno", title: "Hiato: desvira suas unidades e itens (as runas se recarregam)", onclick: () => acao("desvirar") }, "Desvirar")),
    el("div", { class: "cartas" }, ...mao.map(cv => cartaEl(cv, "mao:" + a)))), "mao:" + a);
}

// ---------- menus ----------

function destinos(cv) {
  const d = cv.dono;
  const meu = d === eu();
  const de = meu ? "" : d != null ? ` de ${nomeJ(d)}` : "";
  const ir = (destino, onde = null) => () => mover(cv.iid, destino, onde);
  const regioes = S.v.jogadores.map(j => ({ rotulo: `Região de ${j.nome}`, acao: ir("regiao:" + j.assento) }));
  const retiros = S.v.jogadores.map(j => ({ rotulo: `Retiro de ${j.nome}`, acao: ir("retiro:" + j.assento) }));
  const pessoais = d == null ? [] : [
    { rotulo: `Mão${de}`, acao: ir("mao:" + d) },
    { rotulo: `Topo da Jornada${de}`, acao: ir("jornada:" + d, "topo") },
    { rotulo: `Fundo da Jornada${de}`, acao: ir("jornada:" + d, "fundo") },
    { rotulo: `Histórico${de}`, acao: ir("historico:" + d) },
    { rotulo: `Deck de Eventos${de}`, acao: ir("eventos:" + d, "fundo") },
    { rotulo: `Quests em jogo${de}`, acao: ir("quests:" + d) },
  ];
  return { rotulo: "Mover para", itens: [...pessoais, "-", { rotulo: "Cemitério", acao: ir("cemiterio") },
    { rotulo: "Pilha", acao: ir("pilha", "topo") },
    { rotulo: "Uma região", itens: regioes }, { rotulo: "Um retiro", itens: retiros },
    { rotulo: "Fora de jogo", acao: ir("fora") }] };
}

function minhasRunas(aoEscolher, filtro = () => true) {
  const a = eu();
  return Z("runas:" + a).map((r, i) => ({ r, i })).filter(({ r }) => filtro(r)).map(({ r, i }) => ({
    rotulo: `Runa ${i + 1}: ${Acervo.nome(r.id)} (${r.exausta ? "exaurida" : "pronta"}, ${Z(`cargas:${a}:${i}`).length} cargas)`,
    acao: () => aoEscolher(i),
  }));
}

function menuCarta(ev, cv, zona) {
  const base = zona.split(":")[0];
  const a = eu();
  const c = cv.id ? Acervo.carta(cv.id) : null;
  const titulo = { titulo: c ? Acervo.nome(cv.id, cv.verso) : "Carta" };
  const exaurir = { rotulo: cv.exausta ? "Desvirar" : "Exaurir", acao: () => acao("exaurir", { iid: cv.iid }) };
  let itens = [titulo];
  if (a == null) return abrirMenu(ev, [titulo, { titulo: "Você está assistindo" }]);

  if (base === "mao" && zona === "mao:" + a) {
    const executores = unidadesDe(a).map(u => ({ rotulo: Acervo.nome(u.id, u.verso), acao: () => acao("jogar", { iid: cv.iid, executor: u.iid }) }));
    itens.push(
      { rotulo: "Jogar (vai para a pilha)", acao: () => acao("jogar", { iid: cv.iid }) },
      executores.length ? { rotulo: "Jogar com executor", itens: executores } : null,
      "-",
      { rotulo: "Recarregar runa exaurida (Hiato)", itens: minhasRunas(i => acao("recarregar", { runa: i, fonte: cv.iid }), r => r.exausta) },
      { rotulo: "Carregar runa pronta (Prólogo)", itens: minhasRunas(i => acao("carregar", { runa: i, fonte: cv.iid }), r => !r.exausta) },
      { rotulo: "Descartar (histórico)", acao: () => mover(cv.iid, "historico:" + a) },
      { rotulo: "Revelar a todos", acao: () => acao("revelar", { iid: cv.iid }) },
      "-", destinos(cv));
  } else if (base === "regiao" || base === "retiro") {
    itens.push(exaurir,
      c && c.nome_verso ? { rotulo: cv.verso ? "Virar para a forma base" : "Evoluir (virar a carta)", acao: () => acao("virar", { iid: cv.iid }) } : null,
      { rotulo: "Mover (ação de mover)", itens: [
        ...S.v.jogadores.map(j => ({ rotulo: `Região de ${j.nome}`, acao: () => mover(cv.iid, "regiao:" + j.assento) })),
        "-", ...S.v.jogadores.map(j => ({ rotulo: `Retiro de ${j.nome}`, acao: () => mover(cv.iid, "retiro:" + j.assento) })),
      ] },
      { rotulo: "Marcador +1", acao: () => acao("marcador", { iid: cv.iid, delta: 1 }) },
      cv.marcador ? { rotulo: "Marcador −1", acao: () => acao("marcador", { iid: cv.iid, delta: -1 }) } : null,
      { rotulo: cv.neutro ? "Desmarcar inimigo neutro" : "Marcar como inimigo neutro", acao: () => acao("neutro", { iid: cv.iid }) },
      "-",
      { rotulo: c && c.tipo === "protagonista" ? "Morrer (sai de jogo)" : "Morrer (vai ao cemitério)", acao: () => {
        if (confirm(`${Acervo.nome(cv.id, cv.verso)} morre?`)) acao("morrer", { iid: cv.iid });
      } },
      destinos(cv));
  } else if (base === "anexos") {
    const portadores = [...unidadesDe(cv.dono)].map(u => ({ rotulo: Acervo.nome(u.id, u.verso), acao: () => mover(cv.iid, "anexos:" + u.iid) }));
    itens.push(exaurir, portadores.length ? { rotulo: "Equipar em", itens: portadores } : null,
      { rotulo: "Para o cemitério", acao: () => mover(cv.iid, "cemiterio") }, destinos(cv));
  } else if (base === "quests") {
    itens.push(exaurir, { rotulo: "Completar (vai ao cemitério)", acao: () => mover(cv.iid, "cemiterio") },
      { rotulo: "Marcador +1", acao: () => acao("marcador", { iid: cv.iid, delta: 1 }) },
      cv.marcador ? { rotulo: "Marcador −1", acao: () => acao("marcador", { iid: cv.iid, delta: -1 }) } : null, destinos(cv));
  } else if (base === "pilha") {
    const topo = Z("pilha")[0];
    itens.push(topo && topo.iid === cv.iid ? { rotulo: "Resolver", acao: () => acao("resolver") } : { titulo: "resolve depois das de cima" },
      destinos(cv));
  } else if (base === "eventos" && zona === "eventos:" + a) {
    itens.push(...opcoesPuxar(cv), "-", { rotulo: "Revelar a todos", acao: () => acao("revelar", { iid: cv.iid }) }, destinos(cv));
  } else if (base === "campo" || base === "retiro_carta") {
    itens.push(exaurir, { titulo: "Campos e retiros nunca saem de jogo" });
  } else if (!cv.oculta) {
    itens.push(destinos(cv));
  }
  abrirMenu(ev, itens.filter(Boolean));
}

function opcoesPuxar(cv) {
  const a = eu();
  const tipo = tipoDe(cv);
  if (tipo === "item") {
    const portadores = unidadesDe(a).map(u => ({ rotulo: Acervo.nome(u.id, u.verso), acao: () => acao("puxar", { iid: cv.iid, destino: "anexos:" + u.iid }) }));
    return [portadores.length ? { rotulo: "Puxar e equipar em", itens: portadores } : { titulo: "Nenhuma unidade sua para portar o item" }];
  }
  if (tipo === "quest") return [{ rotulo: "Puxar (quests em jogo)", acao: () => acao("puxar", { iid: cv.iid, destino: "quests:" + a }) }];
  return [
    { rotulo: "Puxar para a região do seu campo", acao: () => acao("puxar", { iid: cv.iid, destino: "regiao:" + a }) },
    { rotulo: "Puxar para outro lugar", itens: [
      ...S.v.jogadores.map(j => ({ rotulo: `Região de ${j.nome}`, acao: () => acao("puxar", { iid: cv.iid, destino: "regiao:" + j.assento }) })),
      ...S.v.jogadores.map(j => ({ rotulo: `Retiro de ${j.nome}`, acao: () => acao("puxar", { iid: cv.iid, destino: "retiro:" + j.assento }) })),
    ] },
  ];
}

function menuRuna(ev, cv, dono, i) {
  const a = eu();
  const meu = dono === a;
  const mao = meu ? Z("mao:" + a) : [];
  const cartasMao = op => mao.map(m => ({ rotulo: Acervo.nome(m.id), acao: () => acao(op, { runa: i, fonte: m.iid }) }));
  const cargas = Z(`cargas:${dono}:${i}`).length;
  abrirMenu(ev, [
    { titulo: `${Acervo.nome(cv.id)} de ${nomeJ(dono)} · ${cargas} carga(s)` },
    meu ? { rotulo: cv.exausta ? "Desvirar" : "Exaurir", acao: () => acao("exaurir", { iid: cv.iid }) } : null,
    meu && cv.exausta ? { rotulo: "Recarregar com o topo da Jornada", acao: () => acao("recarregar", { runa: i, fonte: "jornada" }) } : null,
    meu && cv.exausta && mao.length ? { rotulo: "Recarregar com carta da mão", itens: cartasMao("recarregar") } : null,
    meu && !cv.exausta && mao.length ? { rotulo: "Carregar no Prólogo (exaure e compra 1)", itens: cartasMao("carregar") } : null,
    { rotulo: "Dano nas cargas (personagem)…", acao: () => {
      const n = pedirNumero(`Quantas cargas da runa ${i + 1} de ${nomeJ(dono)} vão para o histórico?`);
      if (n) acao("dano_cargas", { alvo: dono, runa: i, n });
    } },
    meu ? { rotulo: "Ver as cargas", acao: () => abrirPilha(`Cargas da runa ${i + 1}`, `cargas:${a}:${i}`) } : null,
  ].filter(Boolean));
}

function menuJornada(ev, dono) {
  const a = eu();
  const meu = dono === a;
  const dano = { rotulo: `Dano no protagonista de ${meu ? "você" : nomeJ(dono)}…`, acao: () => {
    const n = pedirNumero(`Quanto dano no protagonista de ${nomeJ(dono)}? (cada ponto manda 1 carta do topo da Jornada para o histórico)`);
    if (n) acao("dano", { alvo: dono, n });
  } };
  if (!meu) return abrirMenu(ev, [{ titulo: `Jornada de ${nomeJ(dono)}` }, dano]);
  const espiando = (jogador(a) || {}).espiar || 0;
  abrirMenu(ev, [
    { titulo: "Sua Jornada" },
    { rotulo: "Comprar 1", acao: () => acao("comprar", { n: 1 }) },
    { rotulo: "Comprar até o enredo (Conto)", acao: () => acao("conto") },
    { rotulo: "Olhar o topo…", acao: () => { const n = pedirNumero("Quantas cartas do topo você quer olhar?"); if (n) acao("espiar", { n }); } },
    espiando ? { rotulo: "Parar de olhar o topo", acao: () => acao("espiar", { n: 0 }) } : null,
    { rotulo: "Embaralhar", acao: () => acao("embaralhar") },
    "-", dano,
  ].filter(Boolean));
}

// ---------- janela de uma pilha (Eventos, histórico, cemitério, cargas) ----------

function abrirPilha(titulo, nomeZona) {
  S.modal = { titulo, zona: nomeZona };
  desenharModal();
}

function desenharModal() {
  const { titulo, zona } = S.modal;
  const lista = Z(zona);
  const conteudo = lista.length ? lista.map(cv => cartaEl(cv, zona, { arrastar: false }))
    : [el("div", { class: "dica" }, "Nenhuma carta.")];
  const aberto = $("#modal");
  if (aberto) {
    aberto.querySelector("h3").textContent = `${titulo} · ${lista.length}`;
    aberto.querySelector(".conteudo").replaceChildren(...conteudo);
    return;
  }
  const m = abrirModal(`${titulo} · ${lista.length}`, ...conteudo);
  const fechar = m.querySelector("header button");
  const original = fechar.onclick;
  fechar.onclick = () => { S.modal = null; original(); };
  m.addEventListener("click", ev => { if (ev.target === m) S.modal = null; });
}
document.addEventListener("keydown", ev => { if (ev.key === "Escape") S.modal = null; });

// ---------- início ----------

let ouvindo = false;
function ouvir() {
  if (ouvindo) return;
  ouvindo = true;
  ouvirMudancas(S.token, async d => {
    await acompanharAcervo(d.acervo);
    if (!S.v || d.versao !== S.v.versao) atualizar();
  });
}

async function iniciar() {
  await Acervo.carregar();
  S.decks = await API.get("/api/decks");
  S.token = lerToken();
  if (S.token) ouvir();
  await atualizar();
  setInterval(async () => {
    if (S.v && S.v.etapa === "sala") { S.decks = await API.get("/api/decks"); }
  }, 5000);
}
iniciar();
