# BACKLOG — pesquisa-orquestrada

Problemas e melhorias observados em uso real, com a evidência que os originou. Não é lista de desejos: cada item nasceu de uma pesquisa concreta e traz onde conferir.

Aberto em 12/08/2026, a partir das duas pesquisas para a apresentação de Medellín (`outputs/2026-08-12_energia-e-desenvolvimento/` e `outputs/2026-08-12_historia-uso-produtivo/`).

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
