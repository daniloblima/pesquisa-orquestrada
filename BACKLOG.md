# BACKLOG — pesquisa-orquestrada

Problemas e melhorias observados em uso real, com a evidência que os originou. Não é lista de desejos: cada item nasceu de uma pesquisa concreta e traz onde conferir.

Aberto em 12/08/2026, a partir das duas pesquisas para a apresentação de Medellín (`outputs/2026-08-12_energia-e-desenvolvimento/` e `outputs/2026-08-12_historia-uso-produtivo/`).

> Revisado às 16:35 do mesmo dia, contra o código e contra as sete pesquisas do histórico. O
> veredito item a item está na seção "Revisão de 12/08" no fim deste arquivo, e a apuração
> completa com números está no `CHANGELOG.md`, entrada de 12/08 16:35. Os itens 1, 2 e 4 tiveram
> o diagnóstico corrigido, e três itens novos entraram. Ler a revisão antes de mexer em qualquer
> item acima.

---

## 1. Citação numerada é tratada como ausência de citação

**Gravidade: alta. É o item que mais desperdiça dinheiro hoje.**

O Perplexity Deep Research cita em estilo acadêmico: marcador numerado no parágrafo, `[2][5][8]`, e a lista de URLs no fim. O script procura URL inline junto da afirmação, não encontra, e conclui que as fontes aparecem "apenas na lista final, sem trecho associado". Daí dispara o ALERTA GRAVE e invalida a contribuição inteira do motor.

**A informação está lá.** Verificado manualmente em 12/08 na pesquisa de energia e desenvolvimento: o mapeamento é posicional e exato.

| Marcador no texto | Posição na lista | Fonte |
|---|---|---|
| `[2]` | 2ª URL | GENI, "Global Energy Futures and Human Development" |
| `[5]` | 5ª URL | PNUD, "Energising Human Development" |
| `[6]` | 6ª URL | gráfico interativo de Luis Villa |
| `[8]` | 8ª URL | PNUD, World Energy Assessment |
| `[9]` | 9ª URL | Reflets de la Physique, 2024 |
| `[14]` | 14ª URL | meta-análise de Kalimeris, Richardson e Bithas |
| `[18]` | 18ª URL | meta-análise do Banco Mundial, 2026 |

Custo do erro nas duas pesquisas de 12/08: o Perplexity respondeu por US$ 1,72 de US$ 3,14 gastos, ou seja 55%, e entrou com peso zero de confirmação nas duas.

**Correção proposta.** Antes de decidir que não há trecho associado, procurar marcadores `[N]` no texto e resolvê-los contra a lista ordenada de URLs capturadas. Se o motor usa numeração consistente, cada afirmação passa a ter fonte e o alerta se dissolve sozinho.

**Salvaguarda necessária.** O mapeamento posicional precisa ser validado antes de ser confiado, não presumido. Uma checagem barata: se o maior `N` citado no texto for maior que o número de URLs da lista, a numeração não é posicional e o motor volta ao tratamento atual. Vale registrar no `config.json`, por motor, qual estilo de citação ele usa, em vez de assumir um estilo único para todos.

**Princípio que fica.** Motor não se trata igual. Estilo de citação é característica do motor, como índice e custo, e pertence ao config.

---

## 2. A conferência de assunto tem falso positivo grave

**Gravidade: alta.**

A verificação de `--termos` marca como "fora do tema" páginas que estão exatamente no tema. Na pesquisa de história, com os termos `watermill,windmill,moinho,molino,engenho,sailing,steam,milling`, foram reprovadas:

- `https://www.domesdaybook.net/domesday-book/data-terminology/manors/mills` — página sobre moinhos no Domesday Book, numa pesquisa sobre moinhos no Domesday Book
- `https://www.nationalarchives.gov.uk/help-with-your-research/research-guides/dome...` — guia de pesquisa do Domesday nos Arquivos Nacionais britânicos
- `https://www.encyclopedie-energie.org/en/energy-units/` — página sobre unidades de energia, num ângulo que pede exatamente história das unidades
- `https://www.iranicaonline.org/articles/mill/mill-i-mills-in-iran/` — Encyclopaedia Iranica, verbete sobre moinhos no Irã

Causas prováveis, em ordem de importância:

1. **Sem stemming e sem forma composta.** "milling" não casa com "mill" nem com "mills"; "watermill" não casa com "water mill" escrito em duas palavras. Páginas históricas em inglês usam "mill", "mills" e "water mill", quase nunca "watermill" ou "milling".
2. **Páginas renderizadas por JavaScript** devolvem HTML sem texto no início do documento, e a conferência lê só o começo. Suspeita para `hdr.undp.org/content/energising-human-development`, reprovada por termo tanto para o GPT quanto para o Perplexity na pesquisa de energia e desenvolvimento, sendo uma página real do PNUD e diretamente sobre o tema.

**Correção proposta.** Casar por raiz e não por palavra inteira, normalizar espaço e hífen antes de comparar, e ler mais do que o começo da página. Quando a página devolver corpo vazio ou quase vazio, o estado correto é "inconclusiva", não "fora do tema" — a diferença importa, porque hoje uma página boa e uma página errada recebem o mesmo carimbo.

**Sintoma de que a régua está errada, não a fonte:** quando o mesmo domínio é reprovado para dois motores diferentes na mesma pesquisa, a hipótese mais provável é falha de verificação, não coincidência de alucinação.

---

## 3. Perplexity truncado por limite de tokens nas duas rodadas

**Gravidade: média.**

`finish=length` nas duas pesquisas, com saída de 8.938 e 9.894 tokens contra `max_tokens_r1` de 12.000 no modo normal. O texto termina no meio de uma frase, e na pesquisa de energia e desenvolvimento a seção sobre painéis regionais fica cortada em "Dynamic Ordinary Least Squares (D".

A saída medida não atingiu o teto declarado, o que sugere que tokens de raciocínio do modelo de busca profunda contam contra o mesmo limite, ou que o limite é aplicado noutro ponto. Precisa ser investigado antes de simplesmente subir o número.

**Custo do erro:** paga-se o texto inteiro e perde-se o fim, que é onde costuma estar a síntese.

---

## 4. Grok não tem `reasoning_effort` declarado

**Gravidade: média, e é a suspeita para o estouro histórico de orçamento.**

O Gemini tem `reasoning_effort: low` no `config.json`, com nota explícita de que sem isso ele gasta o orçamento em raciocínio e devolve texto curto. O Grok não tem o campo.

Contraponto que precisa ser registrado antes de mexer: **em 12/08 o Grok não estourou.** Custou US$ 0,5668 e US$ 0,5523 contra teto estimado de US$ 0,5944, com entrada de 402.914 e 380.114 tokens, dentro da faixa de 420 a 490 mil registrada no config. Ou seja, o estouro não é constante, e mexer no config sem entender a variação pode piorar a qualidade sem resolver o custo.

**Antes de mudar:** levantar o custo real por rodada do Grok nas pesquisas anteriores e ver em quais ele passou do teto e o que essas tinham em comum.

---

## 5. A estimativa do Grok usa custo típico fixo

**Gravidade: baixa, mas é a origem da sensação de estouro.**

O `custo_tipico_usd: 0.5` é constante, enquanto a entrada medida varia entre 380 e 490 mil tokens. A estimativa não acompanha essa variação, então erra para os dois lados e a faixa entre típico e teto fica estreita demais (US$ 0,5809 a 0,5944) para um motor cuja entrada varia 25%.

**Correção proposta.** Estimar o Grok por faixa de entrada observada em vez de valor único, e alargar a distância entre típico e teto para refletir a variância real.

---

## 6. O ALERTA GRAVE é binário e desqualifica o motor inteiro

**Gravidade: alta, e decorre do item 1.**

Hoje a regra é: se todas as fontes reprovadas de um agente aparecem só na lista final, nada daquele agente conta como confirmação. É desproporcional. O agente pode ter trinta afirmações bem citadas e quatro fontes reprovadas sem trecho, e perde as trinta.

**Correção proposta.** Graduar. A quarentena deve alcançar as afirmações que dependem das fontes reprovadas, não a contribuição inteira do motor. Quando não der para saber quais são, o alerta deve dizer quantas afirmações ficaram sem rastro, e não invalidar o resto por precaução.

---

## 7. Perda de árbitro em tempo de execução não é avisada

**Gravidade: média.**

O script avisa na composição quando se escolhem dois motores, porque aí não há árbitro para contradição. Não avisa quando o conjunto começa com três e perde um por falha de qualidade durante a rodada.

Foi o que aconteceu em 12/08: escolhidos Grok, GPT e Perplexity, e o Perplexity saiu do jogo pelo ALERTA GRAVE. A pesquisa passou a ter dois motores efetivos, e nada no log disse isso.

**Correção proposta.** Ao fim da rodada 1, recontar quantos motores continuam elegíveis para sustentar consenso e repetir o aviso de composição com o número efetivo.

---

## Dados de custo real, para calibrar

| Data | Pesquisa | Motores | Estimado (teto) | Real |
|---|---|---|---|---|
| 12/08/2026 | energia e desenvolvimento | grok, gpt, perplexity | US$ 1,88 | US$ 1,4737 |
| 12/08/2026 | história do uso produtivo | grok, gpt, perplexity | US$ 1,88 | US$ 1,6696 |

Por motor, somando as duas: Grok US$ 1,1191 · GPT US$ 0,3041 · Perplexity US$ 1,7199.

---

# Revisão de 12/08, 16:35

Conferência dos sete itens contra o código em `skill/scripts/` e contra os sete `r1.json` e
`r2.json` do histórico, de 03/08 a 12/08. As quatro URLs acusadas de "fora do tema" foram baixadas
com `curl` para medir tipo de conteúdo, texto legível e posição dos termos. Apuração completa, com
tabelas e números, no `CHANGELOG.md`, entrada de 12/08 16:35.

## Veredito item a item

| Item | Veredito | O que muda |
|---|---|---|
| 1. Citação numerada | Confirmado, com causa trocada | O mapeamento posicional é real (7 de 7 testados) e estrutural: as URLs vêm das `annotations` na ordem de citação, e o corpo do Perplexity não tem URL nenhuma. Mas este item não é o gatilho do alerta, e sim o que impede o resgate do trecho depois que o item 2 reprova. Risco novo: `extrair_urls` deduplica, e URL citada duas vezes desloca todos os índices seguintes — a salvaguarda proposta não pega esse caso |
| 2. Falso positivo de tema | Confirmado, e é a raiz | São três causas, com conserto diferente para cada uma. Ver abaixo |
| 3. Perplexity truncado | Confirmado, e é sistemático | Corta sempre entre 75% e 80% do teto, nos dois modos. Compatível com tokens de raciocínio contando contra o limite sem aparecer em `completion_tokens`. Teste de graça: salvar o `usage` bruto |
| 4. Grok sem `reasoning_effort` | Cai | O custo do Grok é 89% entrada. `reasoning_effort` mexe na saída e economizaria cerca de cinco centavos, com risco de qualidade. Absorvido pelo item 5 |
| 5. Estimativa do Grok | Confirmado, e sobe de prioridade | É a alavanca real. O estouro de 05/08 foi entrada de 563.513 tokens contra a faixa de 420 a 490 mil do config |
| 6. Alerta binário | Confirmado | Mesmo conserto do item 1, e deve ser feito junto |
| 7. Perda de árbitro | Confirmado | Sem alteração |

## Item 2, detalhado: três causas e não duas

| URL reprovada | Tipo devolvido | Texto legível | Causa real |
|---|---|---|---|
| `domesdaybook.net/.../mills` | text/html | 16.950 chars, com "mill" no começo | o termo passado foi `watermill` e `milling`, nunca a raiz `mill` |
| `hdr.undp.org/content/energising-human-development` | text/html | 8.467 chars | os termos aparecem depois dos 4.000 chars que o script lê |
| `elibrary.imf.org/.../article-A005-en.xml` | text/html | 28.502 chars | mesma causa, agravada por 622 KB de HTML bruto |
| `econstor.eu/.../1694107760.pdf` | text/html, 4.732 bytes | 1.655 chars | parede de cookie no lugar do PDF |

Duas precisões sobre o que já existe no código. O casamento em `buscar.py:529` já é por prefixo,
então `mill` pegaria "mills" e "milling": o que faltou foi passar a raiz em `--termos`, e isso se
corrige na instrução de uso, sem tocar em código. E o estado "inconclusiva" para página vazia já
existe em `buscar.py:525`, com limiar de 250 caracteres — o intersticial do econstor tem 1.655 e
passa por página real.

## 8. Estado inconclusivo é tratado como fonte reprovada

Gravidade: alta, e é bug puro.

Uma URL que não deu para verificar por falha do próprio verificador (SSL, timeout, conexão
resetada) entra em `urls_problematicas` como qualquer outra. Dois efeitos:

- Conta no denominador do ALERTA GRAVE. Em 05/08, na pesquisa dos 75 kW, um motor foi invalidado
  inteiro tendo como únicas reprovações duas URLs inconclusivas.
- `qualidade.py:75` soma `len(urls_problematicas)` no contador de reprovadas, sem separar estado.

Correção: excluir "inconclusiva" dos dois lugares. Falha do verificador não é evidência contra o
motor.

## 9. A régua de qualidade está viciada, e sustentou decisão tomada hoje

Gravidade: alta, e o efeito vaza para fora do projeto.

Das 145 reprovações do histórico, 71 são "fora do tema" (49%) e 17 são "inconclusiva" (12%). O
índice de precisão trata as 145 como equivalentes.

| Motor | URLs | Reprovadas | Precisão registrada | Só falhas duras |
|---|---|---|---|---|
| Grok 4.20 Multi-Agent | 479 | 40 | 0,916 | 0,975 |
| GPT-5.6 Terra | 343 | 39 | 0,886 | 0,959 |
| Perplexity Deep Research | 114 | 19 | 0,833 | 0,947 |
| Gemini 3.1 Pro | 110 | 47 | 0,573 | 0,773 |

A decisão de hoje de tirar o Gemini do padrão continua de pé: ele é o pior em qualquer régua e é o
único com URL inventada (7, contra zero dos outros dois motores padrão). O número que a justificou
é que está errado. Quem merece reexame é o Grok, que tem a melhor precisão da série e saiu do
padrão por custo.

Correção: recalcular `qualidade-motores.json` depois dos itens 2 e 8, e só então rediscutir
composição de motores.

## 10. O alerta grave alcança qualquer motor, e disparou em seis das sete pesquisas

Gravidade: média, e serve para dimensionar o prejuízo.

Não é fenômeno do Perplexity. Disparou para dois motores em 05/08 e para o Grok na pesquisa de
contingência de LLM de hoje, que fundamentou a decisão sobre OpenRouter. O custo real do bug é
maior que os US$ 1,72 contabilizados acima.

## Ordem de correção

1. Item 2, que é o gatilho da cascata. Três consertos em `verificar_tema` e `_texto_do_html`, mais
   uma linha no `SKILL.md` sobre passar raiz em `--termos`.
2. Item 8, excluindo "inconclusiva" do gatilho e do contador. Duas linhas.
3. Itens 1 e 6 juntos: resolver `[N]` pelo índice de annotation e graduar a quarentena para as
   afirmações afetadas em vez do motor inteiro.
4. Recalcular `qualidade-motores.json` com a régua corrigida.
5. Item 3, salvando o `usage` bruto.
6. Item 5, estimativa do Grok por faixa de entrada. O item 4 morre aqui.
7. Item 7, aviso de perda de árbitro.

Lembrete de operação: edição em arquivo de skill não alcança sessão já aberta. Qualquer correção
aplicada aqui vale a partir da próxima sessão do Claude Code, não da próxima pesquisa desta.

---

## 8. A estimativa não desconta o tamanho do trabalho da rodada 2

**Gravidade: baixa.**

A rodada 2 de 12/08 foi estimada em US$ 1,73 a 1,76 por pesquisa, praticamente o mesmo da rodada 1 (US$ 1,79 a 1,88), apesar de os prompts serem cinco vezes menores e o teto de saída ser 5.000 tokens contra 12.000. O estimador projeta pelo custo típico do motor, não pelo trabalho pedido.

Real medido: US$ 1,0516 e US$ 1,4126, ou seja 40% e 20% abaixo do teto. A estimativa serve como teto pessimista e não como previsão.

## 9. O estouro do Grok, medido

**Fecha o item 4 com dado em vez de suspeita.**

Na rodada 2 da pesquisa de história, o Grok consumiu **561.761 tokens de entrada**, acima da faixa de 420 a 490 mil declarada no `config.json`, e custou **US$ 0,7349 contra teto estimado de US$ 0,5761 — 27,6% acima**.

Nas outras três chamadas do dia ficou dentro: 402.914 tokens e US$ 0,5668; 380.114 e US$ 0,5523; 389.322 e US$ 0,5046.

O padrão que aparece: a chamada que estourou foi a de **prompt de verificação com oito itens distintos**, cada um exigindo busca própria. Hipótese a testar — o consumo do Grok escala com o número de perguntas independentes no prompt, não com o tamanho do texto do prompt. Se confirmar, a correção não é `reasoning_effort`, é limitar itens por prompt de rodada 2.

## 10. Pedir o formato ao Perplexity não resolve

**Confirma que o item 1 tem de ser resolvido no parser.**

Nos prompts da rodada 2 foi incluída instrução explícita: "coloque a URL completa entre parênteses no próprio parágrafo de cada item, junto da afirmação que ela sustenta. Não use apenas marcadores numerados remetendo a uma lista no fim."

O Perplexity ignorou nas duas pesquisas e manteve os marcadores `[N]`. O ALERTA GRAVE disparou de novo nas duas.

**Conclusão: o estilo de citação do Perplexity não é ajustável por prompt.** Ou o parser aprende a ler numeração posicional, ou o motor continua sendo pago e descartado.

## 11. Perplexity truncado com saída mínima na rodada 2

**Gravidade: alta, é desperdício direto.**

Saída de **1.373 tokens** na pesquisa de energia e desenvolvimento e de **622 tokens** na de história, ambas com `finish=length`. Na de história ele não entregou veredito utilizável para nenhum dos seis itens, e ainda assim custou **US$ 0,5965**.

Quatro dos itens que ficaram sem segunda fonte por causa disso eram justamente os latino-americanos — Potosí, Capoche, molinos de Río Arriba — que foram para ele por ser o mais forte em fonte acadêmica.

Somado ao item 3, são quatro truncamentos em quatro chamadas. **O Perplexity nunca completou uma resposta em 12/08.**

---

## Balanço de custo do dia 12/08

| Rodada | Pesquisa | Estimado (teto) | Real |
|---|---|---|---|
| 1 | energia e desenvolvimento | US$ 1,88 | US$ 1,4737 |
| 1 | história do uso produtivo | US$ 1,88 | US$ 1,6696 |
| 2 | energia e desenvolvimento | US$ 1,76 | US$ 1,0516 |
| 2 | história do uso produtivo | US$ 1,76 | US$ 1,4126 |
| | **Total** | **US$ 7,28** | **US$ 5,61** |

Por motor, somando as quatro chamadas: **Perplexity US$ 2,6988** (48% do gasto, quatro truncamentos, zero confirmações aceitas pelo script) · **Grok US$ 2,3586** (42%, um estouro de teto) · **GPT US$ 0,5698** (10%, nenhuma falha).

O GPT custou um décimo do total e foi o único que completou todas as respostas.
