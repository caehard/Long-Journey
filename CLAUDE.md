# Card game: contexto do projeto

Jogo de cartas multiplayer (um vencedor) em que cada jogador conduz um personagem, o "rosto do deck", por até 3 atos. Idioma do projeto: português do Brasil.

## Onde está cada coisa

- `livro-de-regras.md`: livro de regras (rascunho v0.5), exportado do doc "Livro de Regras" no claude.ai. É a fonte de verdade das regras. Em conflito entre este arquivo e o livro, vale o livro.
- `Frames das Cartas.pdf`: rascunho visual anterior dos frames (só a ação já estava no layout novo).
- `cards/`: dados das cartas (um arquivo JSON por carta, ver esquema abaixo). Arquivos começando com `_` são ignorados.
- `arte/`: artes das cartas, referenciadas pelo campo `arte` (caminho relativo à raiz).
- `frames/`: templates das cartas (Jinja2 + CSS). `carta.html` + `layout.css` são o frame comum de todos os tipos (nascido do personagem); o que muda por tipo vem dos dados (`dados._pano`, `dados._layout`). `frame.css` ainda guarda peças usadas por ele (véu, vinheta, gemas, selos, pentágono do ato) e regras do frame antigo, cujos templates estão em `frames/antigo/` (sem uso). `carta.css` tem fontes, cores e peças soltas. `config.json` tem elementos, classes, palavras-chave, subtipos e slots. Ícones em `frames/icones/<categoria>/<chave>.svg` substituem as siglas.
- `gerador/` + `gerar.py`: o gerador (Python + Playwright, usa o Edge/Chrome instalado). Ver `python gerar.py --help`.
- `out/`: imagens e PDFs gerados (`png/`, `pdf/`, `folha-a4.pdf`).
- `app.py` + `app/index.html`: app local de teste (`python app.py`, abre http://localhost:8765; `--porta N` usa outra porta, útil para testar sem fechar o app já aberto). Mudanças em Python só valem depois de reiniciar o app; templates e CSS valem na hora. Formulário próprio para cada tipo, só com os campos que o livro permite (o personagem único tem abas Frente e Verso, cada face com seus campos e sua arte, e a pré-visualização mostra as duas faces com legenda; marcar "aliado comum" vira a ficha de uma face), pré-visualização ao vivo com o template real, validação, envio de arte, salvar em `cards/` e exportar via `gerar.py`. Editor de JSON para o resto.

## Gerador

- `python gerar.py`: PNG de todas as cartas. `--pdf` (um PDF por carta), `--folha` (A4 3x3 com marcas de corte), `--sangria 3`, `--escala 2`, `--observar`.
- `python gerar.py nova <tipo> "Nome"`: cria o JSON a partir do modelo. `python gerar.py validar`: só confere.
- Escala dos templates: 10 px = 1 mm (630 x 880 px). Nomes e textos longos encolhem sozinhos; o que não couber vira aviso.
- Marcação nos textos: `**negrito**`, `*itálico*`, quebra de linha = novo parágrafo.

## Resumo das regras (para orientação rápida)

- Cada jogador tem dois decks: Jornada (embaralhado, só ações, serve de mão, recurso e vida) e Eventos (fechado, secreto, entra em jogo por puxada).
- Balanceamento pelo Star System: 100 estrelas por jogador somando herói, Jornada e Eventos.
- Turno: Epílogo, Hiato, Conto, Saga, Prólogo. Efeitos usam pilha (último a entrar resolve primeiro) e todo dano só é aplicado quando a pilha esvazia.
- 3 runas por jogador (personagem, campo, retiro). Cada ação exaure ao menos 1 runa.
- Vitória: ascender, ou ter mais níveis quando a quest do ato 3 termina, resta um vivo, ou o tempo acaba.

## Cartas: decisões de design dos frames

- Formato: 63 x 88 mm. Os templates usam 630 x 880 px como base.
- Estilo desejado: limpo, com foco na arte, arte sangrando até a borda e moldura de linha fina vazada por cima.
- Frame comum (a partir de um esboço da carta de ação do usuário, que é referência e não planta exata; `frames/base.html` + `frames/frame.css`), de cima para baixo:
  1. Barra fina do nome (centralizado), com o pentágono do ato (I, II, III; parte retangular estreita, ponta virada para a direita) por cima da ponta esquerda e o círculo grande de elementos/custo de carga por cima da ponta direita.
  2. Arte sangrando até a borda, ocupando a carta toda.
  3. Pouco acima do meio: estandarte grande da classe pendurado na ponta esquerda da barra de tipo; "Ação" centralizado na barra; subtipos só como símbolos em círculos na ponta direita (sem texto).
  4. Texto de efeito e ambientação sem caixa, direto sobre a arte, que continua atrás com um véu escuro meio opaco.
  5. Base em trapézio sólido na cor do tema (da borda de baixo até ~50 px acima), com número à esquerda, estrela (custo em estrelas) no centro e edição à direita. A estrela é escura, com contorno na cor do tema escurecida 35% (com 2 elementos, metade de cada, acompanhando a divisão do trapézio; com 3, a cor do meio). A cor do texto se ajusta ao contraste.
- Moldura: linha fina (6 px) nas laterais e no topo, na borda da carta, com o mesmo tema de cor (sem a moldura vazada antiga); a base é o trapézio, e os cantos de baixo ao lado dele (os chanfros) são preenchidos com a cor do tema escurecida, em todos os tipos.
- Tema de cor (`simbolos.tema`): prateado só para carta sem elemento (o dourado lembrava demais Riftbound). Com 1 elemento, barras, pentágono, estandarte e trapézio usam a cor dele; com 2 ou 3, as cores se dividem em partes iguais da esquerda para a direita, na ordem do círculo (estandarte e pentágono pegam a 1ª). No CSS: `--prata` = 1ª cor, `--tema-grad` = divisão. Os estandartes são desenhados inline para poder mudar de cor.
- Personagem único: carta de duas faces (forma base na frente, evoluída no verso), com o mesmo custo em estrelas.
- Elementos (definidos): Mecha (máquinas, cobre, engrenagem), Mana (magia, azul, centelha), Divino (deuses, marfim, olho radiante), Gaia (natureza, verde, broto), Alma (violeta, espiral), Caos (carmim, estrela do caos). Símbolos circulares em `frames/icones/elementos/`: anel externo comum + glifo interno, traço grosso, uma cor por elemento. Círculo de elementos (gerado em `gerador/simbolos.py`, usado em todas as cartas): 1 elemento = símbolo inteiro; 2 = corte a 45°, um glifo em cada metade; 3 = cortes a 90°, 210° e 330°, um glifo em cada setor. Um círculo só: com custo de carga, o número aparece grande por cima, no centro (contorno escuro), e os símbolos ficam esmaecidos atrás.
- Classes (definidas): Mago (chapéu), Guerreiro (espada), Besta (garras), Mercador (bolsa de moedas), Ladino (máscara), Guardião (escudo). Símbolo em forma de estandarte (haste + pentágono alongado com a ponta para baixo), todos em prateado: a cor fica reservada aos elementos. Arquivos em `frames/icones/classes/`; aparecem na faixa do meio. Dupla classe (exatamente 2 classes): um estandarte do tamanho normal, partido ao meio por uma linha vertical; cada glifo mantém tamanho e lugar, mas só aparece a metade esquerda da 1ª classe e a metade direita da 2ª (gerado em `gerador/simbolos.py`). `"classe_dupla": false` no JSON volta a dois estandartes separados.
- Subtipos de ação (definidos): Ataque (flecha diagonal), Reação (raio), Leve (pena). Glifo creme dentro do quadrado de borda cinza da faixa do meio, terceira família visual (elementos = círculo colorido, classes = estandarte dourado). Arquivos em `frames/icones/subtipos/`.
- Palavras-chave (ícones definidos): Interceptar (barra no caminho da flecha), Escudo (escudo cheio), Perfurante (flecha pela brecha), Elusivo (mira riscada), Perceptivo (lupa), Distante (arco), Espinhos (três espinhos), Regenerar (seta circular com cruz), Invasor (flecha entrando num portal), Ataque de oportunidade (golpe em meia-lua com exclamação). Quarta família visual: selo hexagonal. Só aparecem no personagem (são habilidades de unidade).
- Slots de item (ícones definidos, `frames/icones/slots/`): arma de 1 mão (espada curta), arma de 2 mãos (machado), acessório (anel com gema), bota, peitoral, elmo, luvas. Glifo creme, mesma família dos subtipos.
- Ainda sem decisão: identidade visual final.

## Esquema de dados proposto (carta de ação)

```json
{
  "tipo": "acao",
  "nome": "",
  "estrelas": 0,
  "ato_minimo": 1,
  "elementos": [],
  "custo_carga": 0,
  "classes": [],
  "subtipos": ["ataque", "leve"],
  "texto": "",
  "ambientacao": "",
  "arte": "arte/nome.png"
}
```

Regras que o esquema precisa respeitar: no máximo 3 elementos distintos por carta, sem elemento duplicado; ação sem elemento é válida; ação pode ter várias classes; subtipos possíveis de ação: reação, ataque, leve.

Campos comuns a todos os tipos: `numero`, `arte_posicao` (CSS, ex.: `"50% 30%"`), `arte_zoom`. Os campos de cada tipo seguem o livro; o validador (`CAMPOS` e `PROIBIDOS` em `gerador/dados.py`) dá **erro**, citando a regra, para campo que o livro não permite. Ver `cards/exemplo-*.json` e `MODELOS`.

- `personagem` único: sempre duas faces e 1 `elemento` (obrigatório). Comuns: `classes`, `raca`, `cla`, `funcao` (`enredo` é sempre 5; só aceito para aviso; palavras-chave vão no `texto` da face). Faces: `frente` (`poder`, `texto`, `evolui_nivel` = nível mínimo para evoluir, `evolui` = condição, `arte`) e `verso` (`nome`, `poder`, `ascensao_nivel` 6 a 11, `ascende` = condição, `texto`, `arte`); a face herda os comuns e pode sobrescrevê-los.
- `personagem` com `"ficha": true` = aliado comum: uma face, `poder`, `raca` e opcionalmente `cla`, `funcao`, `classes`; palavras-chave no `texto`. Sem elemento, nível, enredo, verso nem estrelas (livro, seção 10).
- `item`: `slot` (ver `config.json`), `custo_moedas` (opcional), `ato_minimo` (opcional). Sem classe (classe é só de ação e personagem). Com `"ficha": true` vira item comum, sem estrelas. A moeda em si é uma ficha de item acessório (`cards/exemplo-moeda.json`).
- `campo`, `retiro`: `elemento` (obrigatório, 1), `avancado`, `ato_minimo` (opcional). Nunca ficha.
- `runa`: `elemento`, `avancado`, `ato_minimo` (opcional). Básica é sempre ficha e avançada nunca é (livro, seção 6).
- `quest`: `atos` = lista com 3 textos, um por ato (condição de conclusão, inimigo neutro etc.). `recompensa` (opcional) = recompensa adicional. A pilha é embaralhada, então a mesma quest pode sair em qualquer ato, e dá níveis iguais ao ato em que for concluída (livro, seções 4 e 11). Sem `texto` nem `inimigo`.
- Ficha só existe em aliado comum, item comum e runa básica (livro, seções 6 e 10 e glossário). Ação, campo, retiro e quest não podem ser ficha.

## Frames por tipo (todos no frame comum novo)

O frame antigo (barra do nome no topo, faixa de tipo, trapézio na base; descrito na seção de design acima) não é mais usado; seus templates estão em `frames/antigo/`.

- Frame comum (`carta.html` + `layout.css`), a partir de um esboço do usuário para o personagem; o personagem tem tudo, os outros tipos usam parte. Sem faixa de tipo e sem trapézio. De cima para baixo (no personagem):
  - Moldura na cor do tema, um pouco para dentro da borda (~20 px), por cima da arte, com chanfro de 45° nas quinas e espessura variável: fina nas laterais (2,6 px) e engrossando até 8 px no chanfro, ao longo de ~74 px de cada lado (`simbolos.linha_moldura`, polígonos cheios). Onde há caixa ou estandarte por cima (estandarte, barra do nome, caixa de evolução), a linha não existe: ela é desenhada em trechos que param nesses lugares (`_cortes_moldura` em `dados.py`, com as medidas `PJ_*`, que precisam acompanhar `layout.css`). Máscara CSS não serve: falhou no navegador do app.
  - Canto de cima à esquerda: raça na vertical (Cinzel, `writing-mode: vertical-rl`); a 2ª linha, junto da borda, é "Clã · Função" (os dois têm o mesmo peso); sem clã nem função, a raça fica sozinha nessa posição. Encolhe sozinha (`.ajustar-vertical` em `AJUSTE_JS`).
  - Canto de cima à direita: estandarte pendurado do topo (`simbolos.bandeira_personagem`). No alto, centralizado, o medalhão do elemento: círculo de elementos maior, num disco escuro com anel externo fino, entalhes, 4 losangos e filete interno. A coroa de personagem único fica num círculo menor preso ao medalhão, embaixo à direita e por trás dele (o único é subordinado ao elemento). Abaixo, o símbolo da classe direto no pano, sem moldura, centralizado e grande; com 2 classes, as duas menores, uma para cada lado (sem o estandarte partido). Aliado comum: estandarte estreito só com a classe; sem classe, nada.
  - Pouco abaixo do meio (~490 px): barra do nome saindo da borda esquerda (até 350 px; nomes longos encolhem) e, logo depois dela, o poder no hexágono lapidado (`simbolos.hexagono_poder`, 76 x 84 px).
  - Texto à esquerda, abaixo do nome; a ambientação entra embaixo só se couber sem reduzir o efeito (`.ambientacao.opcional`). À direita, a colmeia de palavras-chave: as que têm glifo em `frames/icones/palavras-chave/` são achadas no texto (sem diferenciar maiúscula/acento, com valor: "Escudo 2", "Elusivo X") e viram selos hexagonais encostados uns nos outros, até 5, em ordem de leitura: 2 em cima, 2 no meio deslocados meio selo, 1 embaixo (`POSICOES_CHAVES` em `dados.py`). Glifo grande (72% do selo); com valor, o glifo sobe e fica em 54%, e o número fica dentro do hexágono, embaixo. Excesso vira aviso.
  - Embaixo à direita, a caixa de evolução (frente) ou ascensão (verso), do topo em 700 px e de ~234 px (embaixo) até as bordas de baixo e da direita, com a borda esquerda inclinada (60 px mais para dentro no topo, 1 px a cada 3; `PJ_CAIXA_*` em `dados.py`, que a linha da moldura segue). O título fica numa aba em paralelogramo (lados paralelos à borda inclinada) montada sobre a linha do topo e deslocada para a esquerda, passando da borda (relevo), preenchida com a cor do tema para contrastar, texto escuro ou claro conforme o contraste; a condição no meio. Bem transparente (a arte aparece atrás, só levemente tingida pela cor do elemento). Na quina de baixo à direita da carta, um quarto de círculo na mesma cor da aba com o ícone (`simbolos.simbolo_quina`): evolução (`frames/icones/marcas/evolucao.svg`, divisas giradas para apontar para a direita) na frente, ascensão (`ascensao.svg`, estrela radiante) no verso. O nível mínimo (`evolui_nivel`, `ascensao_nivel`) continua nos dados e no validador, mas não aparece na carta. O aliado comum não tem caixa.
  - Poder e estrela com brilho em volta suave (mais fraco que o padrão das gemas).
  - Embaixo à esquerda, fora da linha: a estrela do custo, lapidada com o mesmo detalhamento do poder (`simbolos.estrela_lapidada`; usa `_gema_lapidada`, no estilo do hexágono de poder: uma faceta por aresta sombreada pela luz de cima à esquerda, mesa central, reflexo, filete e contorno; também no verso) e, pequenos ao lado, número e edição (ficha: a marca "Ficha").
  - Enredo é sempre 5 e não aparece (o validador avisa se vier diferente: mudança de enredo vai no texto).
- Estandarte nos outros tipos (`simbolos.bandeira`: medalhão + círculo preso a ele + classe; avançado troca o anel do medalhão pela estrela rúnica de 8 pontas). Texto vertical = tipo na 1ª linha e subtipo na 2ª. O nome fica na mesma altura do personagem, o texto abaixo dele; sem caixa de evolução, a moldura fecha embaixo.
  - Ato mínimo (ação sempre; item, campo, retiro e runa quando tiverem `ato_minimo`): o pentágono do ato (I, II, III, ponta para a direita, a moldura de antes) colado ao fim da barra do nome, onde o personagem tem o poder.
  - Estrela lapidada (ou "Ficha") centralizada embaixo, com o número à esquerda e a edição à direita, em todos os tipos menos o personagem único (lá ela fica embaixo à esquerda, porque a caixa de evolução ocupa a direita). O aliado comum também usa a base centralizada.
  - Ação: medalhão = círculo de elementos com o custo de carga por cima; classe(s) embaixo. Texto vertical "Ação" e os subtipos ("Ataque · Leve").
  - Item: medalhão = ícone do slot (item comum sem os detalhes do anel); preso a ele, o custo em moedas (se houver). Texto vertical "Item" ou "Item comum" e o slot.
  - Campo, retiro: medalhão = elemento; embaixo dele, separado e do mesmo tamanho (menos importante que o elemento), um segundo medalhão com o ícone do tipo (`frames/icones/locais/`: campo = bandeira de guerra fincada num monte; retiro = tenda; `segundo` em `simbolos.bandeira`). Avançado: a estrela rúnica fica no medalhão do ícone, não no do elemento. Texto vertical "Campo de batalha"/"Retiro" e "Básico"/"Avançado".
  - Runa: sem estandarte e sem texto vertical. O nome fica no alto (`PJ_NOME_TOPO_RUNA`). O elemento fica embaixo, no centro, num medalhão solto (`simbolos.medalhao_solto`) sobre a linha de baixo da moldura, que sobe (`PJ_RUNA_BASE`) e se abre em volta dele (`PJ_RUNA_VAO`); a estrela do custo fica logo abaixo. Só o símbolo diz se é avançada: avançada com a estrela rúnica em volta do elemento, básica com o anel simples. Básica (ficha) sem texto; avançada com o texto entre a arte e o elemento.
  - Quest: sem estandarte; o nome sobe (`PJ_NOME_TOPO_QUEST`) e embaixo dele vêm as 3 caixas dos atos, cada uma com o pentágono do ato (I, II, III), e a recompensa adicional, se houver. Texto vertical "Quest".
- Moldura com 2 ou 3 elementos: as cores se dividem em partes iguais da esquerda para a direita (gradiente SVG com `tema.paradas`); estandarte, nome e o resto usam a 1ª cor.
- Aliado comum com 2 ou mais classes: estandarte estreito com as classes empilhadas.

## Próximos passos

1. Levar ao livro de regras: (a) item, campo, retiro e runa também podem ter ato mínimo (o livro, seção 6, ainda diz que só ações travam por ato; o gerador já aceita); (b) a mecânica de moedas: itens com custo em moedas, moedas como fichas de item acessório geradas por cartas (foco na classe Mercador), e "Abra o mercado" para gastar moedas e trazer o item ao jogo (a forma mais comum, não a única; nem todo item tem custo em moedas). Hoje ela só existe nos frames e no gerador.
2. Identidade visual final.
3. Fechar os pontos em aberto do livro (seção 15). Cartas de quest: o frame já tem um texto por ato; falta definir no livro as condições, estrelas e inimigos neutros.
