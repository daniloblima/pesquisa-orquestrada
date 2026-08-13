# CHANGELOG — Orquestrador de Pesquisa Profunda

> Registra todos os problemas, bugs, decisões técnicas e soluções encontradas durante o desenvolvimento.
> Consultado obrigatoriamente após cada compactação de contexto.

---

## [2026-03-06] — Sessão de Planejamento Inicial

### OBJETIVO

Definir o escopo completo do projeto antes de escrever qualquer linha de código.
Produzir os documentos de planejamento que vão guiar a execução.

### DECISÕES TÉCNICAS

**Stack escolhida: Python + OpenRouter SDK**
- Python via Homebrew já instalado na máquina
- OpenRouter como único hub de APIs (uma chave, um cliente, todos os modelos)
- OpenAI SDK apontando para `https://openrouter.ai/api/v1` — compatível com todos os modelos

**Por que não FastAPI + Streamlit:**
- V1 é terminal apenas — backend puro sem interface
- Streamlit é o framework para V2 (interface web)
- FastAPI + Streamlit juntos seria redundante — Streamlit já é full-stack

**Modelos escolhidos para V1:**
- Agente A: `perplexity/sonar-deep-research` — web search nativo com citações
- Agente B: `openai/o3` (usar `openai/o3-mini` em testes para economizar)
- Agente C e Orquestrador: `google/gemini-2.5-pro` — bom custo-benefício, contexto grande

**Modelo orquestrador: Gemini 2.5 Pro**
- Decisão: usar modelo com maior raciocínio para perguntas esclarecedoras, análise de gaps e consolidação
- Justificativa: o custo é baixo nessas etapas (pouco volume de tokens), mas o impacto é alto
- Gemini 2.5 Pro tem janela de contexto grande — necessária para ler 3 relatórios simultâneos

**Modos de pesquisa:**
- Sempre 3 agentes — diferença entre modos é exclusivamente o `max_tokens`
- V1 implementa apenas o modo Rápida
- Modo Normal e Profunda chegam na V2 com mudança mínima (só config)

**Passo intermediário é core da V1:**
- Não é feature adicional — é o principal diferencial do produto
- Sem ele, o produto equivale a usar Perplexity + ChatGPT manualmente (já disponível grátis)
- O orquestrador lê os 3 resultados, identifica lacunas, pergunta ao usuário, redireciona

### ESTRUTURA DE ARQUIVOS PLANEJADA

```
pesquisa-orquestrada/
├── PRD.md
├── implementation_plan.md
├── tasks.md
├── rules.md
├── design_guidelines.md
├── CHANGELOG.md
├── .env.example
├── .gitignore
├── requirements.txt
├── config.py
├── main.py
├── src/
│   ├── client.py
│   ├── orchestrator.py
│   ├── agents.py
│   ├── terminal.py
│   └── output.py
└── outputs/          (excluída do git)
```

### LIÇÕES / RISCOS IDENTIFICADOS

- `sonar-deep-research` pode levar 3–10 minutos por chamada — avisar usuário antes de confirmar
- `openai/o3` é o modelo mais caro — usar `o3-mini` em testes iniciais
- Falha de um agente não deve quebrar o fluxo — tratar exceção por agente individualmente
- Estimativa de custo via API do OpenRouter deve ser feita antes de confirmar o início

---

## [2026-03-10] — Revisão de Fluxo Após Testes Manuais

### OBJETIVO

Refinar o fluxo de orquestração com base em testes manuais feitos pelo usuário.

### PROBLEMA

O fluxo anterior (v0.2) previa que cada agente lesse os resultados completos dos outros dois para fazer cross-review. Isso foi identificado como ineficiente: consumo alto de tokens, baixo ganho incremental, e a troca de resultados completos entre agentes não é o que gera valor.

### DECISÃO TÉCNICA — Novo modelo de orquestração

O orquestrador (não os agentes) centraliza toda a inteligência comparativa:

1. Rodada 1: três agentes pesquisam com o mesmo prompt mestre (criado pelo orquestrador)
2. Orquestrador analisa os três resultados e extrai:
   - Consensos (confirmados por 2+ fontes) → vão direto para o relatório
   - Divergências (1 fonte apenas, ou contradições) → geram prompts cirúrgicos
3. Rodada 2: cada agente recebe APENAS o que precisa validar — não os resultados completos dos outros
4. Orquestrador consolida tudo no relatório final

Benefício: tokens da Rodada 2 são muito menores (prompt cirúrgico vs. três relatórios completos).

### DECISÃO TÉCNICA — Mudança do modelo orquestrador

- **Antes:** `google/gemini-2.5-pro` como orquestrador
- **Depois:** `anthropic/claude-sonnet-4-6` como orquestrador

Justificativa: melhor custo-benefício para análise comparativa de múltiplos textos. Gemini 2.5 Pro permanece como Agente C de pesquisa.

### DECISÃO TÉCNICA — Lógica de confiabilidade explícita

Definida regra clara para o relatório:
- 2+ fontes confirmam → apresentado como fato
- 1 fonte apenas → disclaimer obrigatório: "(fonte única — recomenda-se verificação adicional)"
- Contradição não resolvida → seção própria no relatório

### DECISÃO TÉCNICA — Coleta de URLs obrigatória

- Todas as URLs de todos os agentes em todas as rodadas devem ser coletadas
- Prompt enviado aos agentes inclui instrução explícita de retornar URLs em seção separada
- Relatório sem seção de referências é considerado incompleto

### DECISÃO TÉCNICA — APIs futuras

Para V1: tudo via OpenRouter com uma única chave.
Para V2 (futuro): chaves individuais para Anthropic, OpenAI, Google e Perplexity.

### LIÇÕES

- Testes manuais antes de codificar evitaram construir a arquitetura errada
- A lógica de valor está no orquestrador, não na troca entre agentes
- Prompts cirúrgicos na Rodada 2 são mais eficientes que envio de resultados completos

---

## [2026-08-03 16:13] — Virada de app standalone para skill do Claude Code

### OBJETIVO

Transformar o projeto, planejado como aplicação de terminal em Python, em uma skill
acionável por `/pesquisa` dentro do Claude Code, consumindo crédito do OpenRouter só
onde for indispensável.

### DECISÃO DE ARQUITETURA — quem orquestra

O PRD punha `claude-sonnet-4-6` via OpenRouter como orquestrador, responsável por
clarificação, análise de consenso, prompts cirúrgicos e consolidação. Dentro do Claude
Code esse papel passa a ser do próprio Claude Code, sem custo adicional de API.

O OpenRouter passa a pagar exclusivamente as chamadas de pesquisa, que é o que o Claude
Code não consegue fazer sozinho: acessar motores heterogêneos com índices independentes.

Ganhos: a clarificação vira conversa de verdade em vez de `input()` no terminal; a
consolidação roda em modelo mais forte; a lógica vive em markdown editável, sem exigir
que o Danilo mexa em Python para ajustar um critério. A economia de custo é secundária,
na ordem de US$ 0,20 por pesquisa.

Perda aceita: não roda fora do Claude Code.

### PROBLEMA 1 — o plugin de busca web é ignorado em silêncio pelos modelos Google

Sintoma: no primeiro teste real, o agente C (`google/gemini-3.1-pro-preview`) devolveu
`prompt_tokens=22` e nenhuma URL, enquanto o agente B (`openai/gpt-5.6-terra`) devolveu
`prompt_tokens=70244` e 5 URLs. O C tinha respondido inteiramente de memória.

Gravidade: este é o pior modo de falha possível para este produto. Um agente que não
pesquisa produz texto plausível sem fonte, e o orquestrador o contaria como segunda
fonte confirmando o primeiro. O resultado seria pior que inútil, seria enganoso.

Causa: o plugin `{"id": "web"}` sem o campo `engine` explícito não é aplicado nos modelos
Google. Não há erro, não há aviso — a chamada simplesmente retorna sem busca.

Teste que isolou a causa (quatro variantes em paralelo):

| Variante | prompt_tokens | citações | buscou |
|---|---|---|---|
| pro + plugin sem engine | 22 | 0 | não |
| pro + plugin engine=exa | 1.479 | 3 | sim |
| pro + sufixo `:online` | 10.257 | 3 | sim |
| pro + plugin engine=native | 11.067 | 0 | sim |
| flash 3.5 + plugin sem engine | 22 | 0 | não |

Solução: declarar `engine` sempre, no `config.json`, por agente.

### DECISÃO — cada motor com o índice da própria família

Escolhido `engine: "native"` para B e C, em vez do Exa, que seria mais barato.

Razão: se todos os agentes usassem o mesmo motor de busca, leriam as mesmas páginas e a
concordância entre eles viraria artefato do método, não validação independente. O núcleo
do produto exige índices distintos: Perplexity para o A, OpenAI para o B, Google para o C.

Verificação: rodada real com B e C sobre o mesmo tema devolveu 6 e 7 URLs, com zero
sobreposição entre os dois conjuntos. A premissa se sustenta.

### PROBLEMA 2 — Gemini queimando o orçamento em raciocínio

Sintoma: `completion_tokens=2996` para apenas 436 caracteres de texto útil, a US$ 0,098.
Em outra execução, `finish_reason=length` com o conteúdo truncado.

Causa: sem limite de raciocínio, o modelo gasta quase todo o orçamento de saída pensando
e sobra pouco para a resposta.

Solução: `reasoning: {"effort": "low"}` por agente, configurável. Pesquisa quer cobertura
e síntese de fontes, não cadeia longa de raciocínio.

Resultado: de 436 para 2.765 caracteres, com 8 URLs, a US$ 0,0498. Rendimento saltou de
cerca de 4.400 para 55.000 caracteres por dólar.

### PROBLEMA 3 — URLs opacas do grounding do Google

Sintoma: o agente C devolvia apenas links `vertexaisearch.cloud.google.com/grounding-api-redirect/...`,
que não dizem nada a quem lê o relatório e expiram com o tempo.

Solução: `resolver_redirects()` segue o 302 e troca pela URL real, em paralelo, com falha
silenciosa que preserva a original. Verificado: 6 de 6 links resolvidos para fontes
legíveis (infomoney, canalsolar, brasilenergia e outras).

### PROBLEMA 4 — estimativa de custo subestimava em 3 vezes

Sintoma: teto estimado de US$ 0,06 contra custo real de US$ 0,18.

Causa: a estimativa contava só o prompt e o teto de saída. Os resultados de busca entram
como input e são a maior parte da conta — 43 mil tokens numa chamada cuja pergunta tinha 90
caracteres.

Solução: `tokens_input_busca_estimados` de 40.000 no `config.json`, somado ao input de cada
agente que faz busca. Nova verificação: teto US$ 0,19 contra real US$ 0,14.

### TRAVA DE QUALIDADE ADICIONADA

Agente que retorna zero URLs é marcado com `sem_fontes: true` no JSON, recebe alerta no log
e um aviso no topo do próprio markdown. O `SKILL.md` proíbe usá-lo como confirmação de
qualquer coisa. É a defesa contra o Problema 1 voltar por outro caminho.

### ESTRUTURA ENTREGUE

```
~/.claude/skills/pesquisa/
├── SKILL.md                        fluxo de orquestração e regras duras
├── config.json                     modelos, engines, preços, modos
├── scripts/buscar.py               única parte que gasta crédito
└── references/
    ├── prompt-mestre.md            template das duas rodadas
    └── formato-relatorio.md        estrutura e critérios do entregável
```

`buscar.py` usa apenas a biblioteca padrão do Python. Nada a instalar.

Chave do OpenRouter em `~/.claude/.env`, permissão 600, fora de qualquer repositório git.
O script procura primeiro na variável de ambiente, depois nesse arquivo.

### RESULTADOS MEDIDOS

- Custo real das duas rodadas, modo normal, projeção: US$ 1 a 2 por pesquisa, contra o teto
  de US$ 5 do critério de sucesso do PRD
- Rodada de teste com dois agentes: 38 segundos, US$ 0,14
- Sobreposição de URLs entre índices diferentes: zero
- Gasto total dos testes desta sessão: cerca de US$ 0,85

### LIÇÕES APRENDIDAS

Recurso de API que falha em silêncio é mais perigoso que recurso que dá erro. O plugin de
busca retornava HTTP 200 com resposta bem formada e nenhuma pesquisa feita. Só a inspeção
de `prompt_tokens` revelou. Toda integração com busca precisa de um sinal verificável de
que a busca ocorreu — aqui, contagem de URLs e volume de input.

Diversidade de fontes é decisão de arquitetura, não detalhe de configuração. A escolha do
engine mais barato teria mantido o produto funcionando e destruído o motivo dele existir.

Testar com dois modelos antes de rodar os três economizou dinheiro e revelou os quatro
problemas. O agente A, mais caro e mais lento, nunca foi acionado durante a depuração.

### PENDENTE

- Rodada completa com os três agentes, incluindo `sonar-deep-research`, num tema real
- Verificar carregamento do relatório final no NotebookLM
- Confirmar comportamento do modo `profunda`, ainda não exercitado

---

## [2026-08-03 17:34] — Primeiro uso real e painel de acompanhamento

### CONTEXTO

Primeira pesquisa de verdade, rodada em outra sessão do Claude Code com contexto
carregado, sobre um tema acadêmico. Serviu de teste de campo e derrubou três suposições.

### PROBLEMA 5 — o agente A caiu com 502 da Perplexity

Sintoma: `Upstream error from Perplexity: The inference server returned an error or
timed out`, código 502, após 149 segundos. Agente A perdido, rodada seguiu com dois.

Causa: falha transitória do provedor, não do script. O `sonar-deep-research` trabalha
por minutos e a conexão às vezes cai.

Solução: `MAX_TENTATIVAS = 3` com espera de 10 e 30 segundos, e a função `vale_retentar()`,
que só reenvia em falha de infraestrutura (408, 429, 5xx, timeout, connection reset). Erro
de conteúdo ou de pedido não se reenvia, porque repetir não muda o resultado e custa.

Verificação: a outra sessão reexecutou o agente A por conta própria e ele completou na
segunda tentativa, com 17 fontes e 23.663 caracteres. A falha era mesmo passageira.

### PROBLEMA 6 — sonar-deep-research custa cinco vezes mais do que o estimado

Medição real: US$ 1,1164 numa única chamada, contra os US$ 0,20 de taxa fixa que o
`config.json` previa.

Decomposição: `in=1911`, `out=5899`, que aos preços de tokens dariam US$ 0,051. A
diferença de US$ 1,06 é cobrança de busca do deep research, que roda dezenas de
consultas internas por chamada.

Efeito na conta: o agente A sozinho custa quatro vezes os outros dois somados. A pesquisa
completa fechou em US$ 1,40, sendo US$ 1,12 dele.

Solução: `taxa_fixa` corrigida para 1.05. A estimativa agora não engana mais.

Decisão pendente: manter o A a esse preço ou trocar por `perplexity/sonar-pro-search`.
Ele traz busca genuinamente independente e profunda, que é o núcleo do produto, mas
dobra o custo por pesquisa sozinho.

### PROBLEMA 7 — truncamento nos três agentes

Sintoma: `finish_reason=length` em A e B. O B bateu exatamente nos 8.000 tokens do modo
normal e teve o relatório cortado no meio, com as fontes finais perdidas.

Causa: tetos calibrados no escuro, antes de qualquer execução real.

Solução: modo rápida subiu de 4.000 para 6.000, normal de 8.000 para 12.000 e profunda de
16.000 para 20.000 na rodada 1.

Lição: relatório truncado é pior que relatório curto, porque a seção de fontes fica no fim
e é a primeira coisa a se perder.

### DUAS SESSÕES NA MESMA PASTA

Enquanto a sessão de lá reexecutava o agente A, esta sessão disparou a mesma recuperação em
segundo plano. Trabalho duplicado, crédito gasto à toa. Processo interrompido assim que a
duplicação foi percebida, pela presença de um `r1_retry_A.json` que não era desta sessão.

Lição operacional: antes de escrever numa pasta de pesquisa, verificar se outra sessão está
trabalhando nela. Arquivo recente com nome que não foi você que escolheu é o sinal.

### PAINEL DE ACOMPANHAMENTO

Novo `scripts/dashboard.py`. Varre `outputs/`, lê os JSON de todas as rodadas e gera um
`dashboard.html` autocontido, que abre com duplo clique, sem servidor.

Mostra: número de pesquisas, custo acumulado e médio, fontes coletadas, domínios distintos,
tempo total; histórico com tema, modo, estado de cada motor, fontes e custo por pesquisa;
e as fontes mais recorrentes em barras, quando há repetição suficiente para revelar padrão.

Decisões de visualização, seguindo a skill `dataviz`:

- Números-chave viraram fila de stat tiles, não gráfico de barra de um valor só
- Histórico é tabela, porque são sete atributos por pesquisa que carregam significado
- Barras de domínio usam hue única sequencial, porque o trabalho é comparar magnitude
- Estado dos motores nunca depende só de cor: cada marcador traz o texto ao lado
- Cor de alerta trocada de `#fab219` para `#ec835a`, que tem contraste 2,57 contra 1,79
  no fundo claro

O `SKILL.md` ganhou o passo 7, que grava `meta.json` com tema, objetivo, hipótese e as
contagens de fonte única e divergências abertas, e regenera o painel ao fim de cada pesquisa.
Pesquisas anteriores sem `meta.json` continuam aparecendo, com o tema inferido do título do
relatório.

### RESULTADOS DA PRIMEIRA PESQUISA

- 51 fontes únicas, 32 domínios distintos
- Custo total US$ 1,40, sendo US$ 1,12 do agente A
- Cerca de 6 minutos de chamadas
- Perfil das fontes: predominantemente acadêmicas — sciencedirect, nber.org, ssrn, doi.org

### LIÇÕES APRENDIDAS

Estimativa de custo feita sobre preço de token ignora o que realmente pesa em modelo de
pesquisa, que é a cobrança por busca. Só a medição real revelou a diferença de cinco vezes.

Todo teto de tokens calibrado antes da primeira execução real está errado. Os três agentes
truncaram na estreia.

O painel de fontes recorrentes virou informação de qualidade sem ter sido pensado para isso:
saber que uma pesquisa se apoiou em bases acadêmicas, ou em blogs de fornecedor, diz sobre a
confiabilidade do resultado tanto quanto a contagem de confirmações.

---

## [2026-08-03 17:59] — URL falsa, estimativa por motor e medição de contribuição

Entrada motivada pelas ressalvas que a sessão que rodou a pesquisa trouxe. Os três achados
foram conferidos contra os dados desta sessão antes de virar mudança.

### PROBLEMA 8 — a trava de fontes protegia contra o caso benigno, não contra o grave

Relato: o Gemini entregou uma URL construída para parecer plausível, com o próprio modelo
anotando entre parênteses que havia substituído o link, mais o domínio raiz de um serviço de
hospedagem listado como página consultada. O script contou dez URLs e não sinalizou nada. O
estudo que essas URLs sustentavam foi declarado inexistente por dois motores na rodada
seguinte, incluindo o próprio Gemini.

Análise: a trava do Problema 1 dispara com zero URL. Esse é o caso visível e recuperável.
URL presente apontando para página inventada é o caso oposto: parece verificada, entra nas
referências, e ninguém confere. É o pior modo de falha que o produto pode ter, porque a
promessa dele é justamente confiabilidade de fonte.

Solução: `verificar_urls()`, com três checagens independentes.

1. Existência real, por requisição HEAD com queda para GET quando o servidor recusa HEAD.
   404 e 410 marcam como inexistente; domínio que não resolve também; 403 e 429 ficam como
   inconclusivos, porque bloqueio de robô não é prova de invenção.
2. Forma da URL. Domínio raiz sem caminho não é página consultada. Lista de domínios de
   hospedagem e encurtadores marca o caso do serviço genérico citado como fonte.
3. Confissão no texto. O modelo às vezes admite ao lado do link que o construiu, com
   palavras como "substituí", "aproximado", "ilustrativo", "hipotético".

O resultado entra em `urls_inexistentes` e `urls_suspeitas`, com alerta no log e um bloco no
topo do markdown do agente. O `SKILL.md` ganhou a regra dura: afirmação apoiada só em URL
reprovada não entra no relatório, vai para limitações com o motivo.

Falso positivo encontrado no teste e corrigido: a janela de contexto de 260 caracteres em
volta do link vazava para outras linhas, e um "substituí" numa linha reprovava a URL legítima
da linha seguinte. Duas fontes boas foram marcadas indevidamente. Janela reduzida para 150
caracteres, só antes do link e travada na quebra de linha ou no ponto final mais próximo.
Reteste: seis URLs, quatro reprovadas corretamente, duas legítimas aprovadas, zero falso
positivo.

### PROBLEMA 9 — a estimativa de custo errava por fator de 2 a 3 nas duas direções

Relato: teto apresentado de US$ 0,62 contra US$ 1,40 reais.

Causa, confirmada nas medições: a fórmula usava um único valor de input, 40 mil tokens, para
todos os agentes, e supunha que a saída chegaria ao teto. Os perfis são opostos.

| Motor | Input real medido | Como cobra |
|---|---|---|
| `gpt-5.6-terra` | 36 mil a 82 mil | resultados de busca entram no prompt |
| `gemini-3.1-pro` | 22 a 1.730 | busca do lado do provedor |
| `sonar-deep-research` | 1.911 | busca do lado do provedor, cobra por consulta |

Para o Perplexity, 40 mil superestimava o input em vinte vezes e ao mesmo tempo a estimativa
subestimava o total, porque o que pesa nele é cobrança por busca, não token. Errado nas duas
pontas ao mesmo tempo.

Solução: `tokens_input_busca` por modelo no `config.json`, com os valores medidos, e a
estimativa passou a devolver faixa em vez de número único, usando `fracao_saida_tipica` de
0,55 para o piso e o teto de tokens para o topo.

Verificação: a mesma pesquisa agora estima entre US$ 1,29 e US$ 1,43. O real foi US$ 1,395.

### MEDIÇÃO DE CONTRIBUIÇÃO POR MOTOR

O painel media alcance, com fontes exclusivas, e alcance não é utilidade: uma página que
ninguém mais viu pode não ter acrescentado nenhuma informação.

O `meta.json` ganhou `contribuicao_por_motor`, com quatro contagens por motor — afirmações que
entraram no relatório, quantas outro motor confirmou, quantas ficaram apoiadas só nele e
quantas foram descartadas. A contagem já era feita na análise de consenso do passo 4, apenas
não era gravada.

Métrica final derivada: custo por afirmação confirmada. É comparável entre motores, entre
pesquisas e ao longo do tempo, e não depende de ninguém preencher formulário.

Instrução explícita no `SKILL.md`: se não der para separar com honestidade, gravar `null` em
vez de estimar. Número inventado aqui contamina a série inteira e é pior que campo vazio.

`nota_manual` de 1 a 5 fica como campo opcional. Nota subjetiva pedida a cada pesquisa não
sobrevive à terceira, e mede mais a satisfação com o resultado geral do que o desempenho de
cada motor.

### AJUSTES DE PAINEL PEDIDOS PELO DANILO

- Motores aparecem pelo nome, não como A, B e C. O identificador do modelo fica no tooltip
- Modo ganhou legenda dizendo o que significa em tokens e resultados por motor
- Cada linha do histórico tem link para o relatório e para a pasta
- Seção "Desempenho por motor", agregada por modelo e não por slot, para que a troca de um
  motor apareça como duas linhas comparáveis
- URLs reprovadas aparecem como alerta na linha do motor

Observação do Danilo que fica anotada: os indicadores de fontes coletadas e tempo total
perdem utilidade com o volume. Substitutos propostos para quando isso acontecer: taxa de
confirmação do relatório e taxa de falha dos motores.

### DECISÃO EM ABERTO — o Perplexity fica na rodada 1?

Recomendação da sessão que rodou: tirar da rodada 1 e usar só para arbitrar contradição.
Fundamentos, todos confirmados aqui: US$ 1,86 contra US$ 0,36 do GPT, mais lento (149 a 178
segundos contra 20 a 40), truncou nas duas rodadas e falhou uma vez. Foi melhor em honestidade
sobre o que não conseguiu verificar e na leitura interpretativa da arbitragem.

Contraponto que os dados desta sessão acrescentam: ele trouxe 36 fontes exclusivas, 95% do
que alcançou. Ninguém mediu ainda se essas fontes sustentaram alguma afirmação do relatório
final, que é exatamente a pergunta que a contribuição por motor passa a responder.

Encaminhamento: manter na rodada 1 por mais uma ou duas pesquisas, agora com a medição ligada,
e decidir com dado. O custo dessas rodadas extras é da ordem de US$ 3, baixo diante de
desligar às cegas o motor que traz mais fonte exclusiva.

### LIÇÕES APRENDIDAS

Trava de qualidade tende a ser escrita contra o caso que é fácil de imaginar. Zero URL é fácil
de imaginar. URL que existe na forma e não no mundo é o que realmente machuca, e só apareceu
em uso real.

Detector novo precisa ser testado com material que deve passar, não só com material que deve
falhar. O primeiro teste só tinha URL ruim, e por isso o falso positivo passou despercebido
até a rodada com fontes legítimas misturadas.

Estimativa de custo com parâmetro único para provedores diferentes está errada por construção
quando os modelos de cobrança são diferentes. Aqui um cobra por token de input e outro por
consulta de busca, e nenhuma média serve para os dois.

---

## [2026-08-04 09:00] — Troca do motor A, catálogo persistente e o que a literatura já sabia

### TROCA — Perplexity sai da rodada 1, Grok entra

Slot A passou de `perplexity/sonar-deep-research` para `x-ai/grok-4.20-multi-agent`.

Medições que sustentam: US$ 1,12 contra US$ 0,32 por chamada, ambos com busca real
confirmada. O Grok multi-agent leu 232 mil tokens de entrada numa chamada e devolveu oito
fontes — é o que mais se aproxima de busca profunda fora da Perplexity. A cobrança dele é
toda em token, sem taxa por consulta, o que torna a estimativa previsível.

O Perplexity continua em `motores_disponiveis` e volta trocando uma linha. A decisão é
provisória, para acumular série comparável com a medição de contribuição ligada.

### CATÁLOGO PERSISTENTE DE MOTORES

`motores.py` reescrito. Antes consultava a API e imprimia tudo a cada execução. Agora
mantém `catalogo-motores.json`: classifica o catálogo inteiro na primeira execução e nas
seguintes trabalha só o diferencial — modelos novos entram para classificação, os que
sumiram são marcados, mudanças de preço são detectadas mesmo em modelo já conhecido.

Primeira classificação: 338 modelos. 6 deep-research, 46 busca-nativa, 198 sem busca,
88 descartados. Os 6 de busca profunda são cinco da Perplexity mais o Grok multi-agent.

A classificação é heurística e revisável à mão. Correção manual sobrevive à próxima
execução, que é o ponto de guardar em arquivo.

Dois filtros descobertos no uso: modelos de peso aberto rodam em provedor terceiro e por
isso não têm o índice de busca da família, apesar do prefixo; e preço de saída zerado
indica modelo que não gera texto cobrado por token — foi assim que dois modelos de música
entraram como candidatos a motor de pesquisa na primeira rodada.

### SELEÇÃO DE MOTORES NA CLARIFICAÇÃO

A última aba do `AskUserQuestion` passa a ser a escolha dos motores, montada a partir de
`motores_disponiveis`, com seleção múltipla. Regras escritas no `SKILL.md`: um índice por
família, três como número de trabalho, aviso quando a escolha sai disso e mudança para
combinações por perfil quando a lista passar de quatro opções.

Escolha diferente do padrão não edita o `config.json` — vai por `--agentes` e fica
registrada no `meta.json`.

### O QUE A LITERATURA JÁ SABIA

Busca por trabalho anterior, a pedido do Danilo. O achado relevante não foram os projetos
parecidos, e sim a pesquisa que mede exatamente o Problema 8.

Estudos recentes de verificação de citação em agentes de pesquisa (arXiv 2604.03173 e
2605.06635) mediram mais de 50 mil URLs do DRBench e 168 mil do ExpertQA: de 3% a 13% das
URLs citadas são alucinadas, sem registro no arquivo da internet e provavelmente nunca
existiram, e de 5% a 18% não resolvem. Outros trabalhos relatam de 11% a 57%.

Duas consequências diretas:

O que aconteceu com o Gemini não foi azar, é taxa base conhecida. Qualquer sistema que
cite fontes sem verificá-las carrega esse percentual.

E o dado mais desconfortável: agentes de busca profunda geram mais citações por consulta
que modelos com busca simples, e alucinam URL a taxas maiores. Ou seja, o motor mais caro
e mais completo é também o mais propenso ao modo de falha grave. Isso reforça a verificação
como obrigatória, não como refinamento.

### MELHORIA VINDA DA LITERATURA — arquivo da internet

Os papers usam o Wayback Machine para separar dois casos que a resposta HTTP confunde:
página que existiu e saiu do ar contra URL que nunca existiu. Só a segunda indica invenção.
Uma reportagem removida do site continua sendo evidência de que a informação foi publicada.

Implementado: URLs que dão 404 ou não resolvem passam pelo arquivo. Com registro, viram
`removida`; sem registro, viram `inventada`.

Duas travas descobertas no teste. O archive.org devolve 429 sob paralelismo, então a
consulta virou sequencial com pausa de 1,2 segundo e teto de 12 URLs por agente. E quando
o arquivo não responde, o estado permanece `inexistente` em vez de concluir invenção —
falha de checagem nunca vira acusação.

Erro cometido no próprio teste, que vale registrar: usei como controle positivo uma URL do
NYTimes que eu mesmo fabriquei, e o detector a classificou como inventada. Passei alguns
minutos achando que era falso positivo do código quando era falso positivo do meu teste.
Controle de teste também precisa ser verificado.

### PROJETOS PARECIDOS

Existem motores de consenso multimodelo — K-LLM, duh, mLLMCelltype — mas resolvem outro
problema: divergência de opinião ou de julgamento entre modelos, com síntese ao final.
Nenhum trata fonte como objeto de primeira classe nem verifica se a citação existe. A
diferença de propósito é essa: aqui o que se valida é a evidência, não a resposta.

---

## [2026-08-04 09:15] — Conferência de assunto: a página existe, mas fala do quê?

### PERGUNTA DO DANILO

Verificar se cada fonte sustenta o que o motor diz que ela sustenta, levado ao limite, vira
uma pesquisa para validar a pesquisa. Ele pediu o meio do caminho: conferir que a fonte
existe, é real e fala sobre o tema.

### BALANÇO ANTES DE IMPLEMENTAR

| Nível | O que pega | Custo API | Tokens do Claude | Tempo |
|---|---|---|---|---|
| Existência (já existia) | URL que não resolve ou nunca existiu | zero | zero | 10 a 20 s |
| **Assunto (implementado)** | página real que trata de outra coisa | **zero** | **zero** | **menos de 5 s** |
| Sustentação por LLM | página do tema que não prova a afirmação | ~US$ 0,01 | zero | ~20 s |
| Leitura completa | tudo | zero | alto | minutos |

O nível de assunto foi escolhido por dominar os outros na relação entre o que pega e o que
custa. O de sustentação ficou desenhado e não implementado: o custo em dólar é desprezível,
mas exige mapear cada afirmação à fonte certa, e um julgamento errado vira acusação falsa
contra uma fonte boa. Sem evidência de que o nível de assunto não basta, implementá-lo seria
otimizar no escuro.

### IMPLEMENTAÇÃO

`verificar_tema()` baixa os primeiros 120 KB de cada página, extrai título, meta descrição,
og:tags, h1 e o começo do corpo, normaliza sem acento e procura os termos centrais da
pesquisa. Página que não menciona nenhum vira `fora do tema`.

Novo argumento `--termos`, com cinco a oito substantivos centrais do tema. Sem ele a
conferência não roda e o log diz isso.

Degradações que nunca viram acusação, porque falha de checagem não é prova de nada:
conteúdo que não é HTML, como PDF; página com menos de 250 caracteres de texto legível,
típico de site que monta tudo por script ou de paywall; e qualquer erro de rede.

### TESTE

Quatro URLs reais, duas do tema e duas de assunto alheio, com os termos de uma pesquisa
sobre baterias:

- `gov.br/aneel` e uma matéria sobre BESS — aprovadas
- um paper de economia do NBER e o verbete de panificação da Wikipédia — `fora do tema`

Tempo total: 0,8 segundo para quatro páginas. Zero falso positivo, zero custo de API.

### O QUE ISTO PEGA QUE O RESTO NÃO PEGAVA

O caso em que o modelo acerta o domínio e inventa o caminho, que é frequente e passava por
todas as travas anteriores: o domínio resolve, a URL tem forma de fonte, o modelo não
confessa nada, e o servidor devolve 200 numa página de erro ou na home. Também pega citação
trocada, quando a URL é real mas pertence a outro assunto.

### LIÇÃO

A verificação mais barata não era a mais fraca. Comparar palavras do tema com o texto da
página não julga nada de sofisticado e mesmo assim cobre o modo de falha mais comum, a
custo nenhum. Vale medir o alcance de uma checagem simples antes de partir para julgamento
semântico.

---

## [2026-08-04 10:30] — Fonte reprovada manda a afirmação para revalidação, não para o lixo

### O FURO APONTADO PELO DANILO

A regra anterior mandava descartar a afirmação apoiada em fonte reprovada. Descarte é perda
de informação: o modelo pode ter lido algo verdadeiro e citado a fonte errada. Pior, o
descarte era silencioso — a afirmação sumia do relatório e nem o leitor nem o Danilo ficavam
sabendo que ela existiu.

Nas palavras dele: não adianta descartar, porque a pesquisa continua falsa em algumas
partes. O que faltava era carregar o diagnóstico para a rodada 2 e mandar validar a
informação, não a URL.

### IMPLEMENTAÇÃO

`contexto_da_url()` recupera o trecho em que cada fonte reprovada foi usada como prova.
Localiza a URL no texto, ignora as ocorrências que estão depois do cabeçalho da lista de
fontes — ali é item de lista, não uso — e devolve o parágrafo em volta.

O resultado entra em `afirmacoes_a_revalidar`, no JSON de cada agente, com URL, estado,
motivos e o trecho. O markdown do agente ganhou uma seção com esses trechos, para leitura
direta.

Quando a URL só aparece na lista de fontes, não há afirmação colada nela e o campo fica
vazio. O log diz quantas ficaram sem contexto, para que a lacuna não passe despercebida.

### TRÊS REGRAS DE DESENHO, TODAS NO SKILL.md

**Quem citou não valida a própria citação.** A afirmação vai para os outros motores. Quem
produziu o link tende a defendê-lo, e aí o teste deixa de testar.

**Não se conta ao motor que a fonte era falsa.** O item vai como qualquer outro: o trecho e
o que se procura. Avisar que a citação anterior caiu induz o modelo a concordar com a
reprovação em vez de pesquisar — e um número correto seria descartado junto com a fonte
ruim.

**Afirmação em quarentena não vira consenso.** Mesmo que outro motor diga algo parecido, ela
espera a rodada 2. Sem isso, uma afirmação com fonte inventada poderia ser promovida a fato
por semelhança com outra.

### O QUE MUDA NO RELATÓRIO

Antes: a afirmação sumia.

Agora: vai para a rodada 2 e recebe um dos dois destinos. Confirmada por fonte que existe,
entra normalmente. Não confirmada, vai para limitações, nomeada, dizendo o que se tentou
verificar e o que aconteceu. O `formato-relatorio.md` traz o exemplo redigido.

### TESTE

Texto com duas afirmações apoiadas em URLs falsas, mais a lista de fontes ao final. As duas
URLs foram reprovadas, os dois trechos recuperados com número e data intactos, e a URL que
aparecia somente na lista de fontes foi corretamente identificada como sem contexto.

### CUSTO

A rodada 2 fica um pouco maior, com mais itens no prompt cirúrgico. Prompt cirúrgico é a
parte barata do sistema, e o que se compra com isso é a diferença entre um relatório que
perde informação boa em silêncio e um que diz o que não conseguiu verificar.

### LIÇÃO

Uma trava que só sabe rejeitar não é uma trava completa. Detectar o problema é metade do
trabalho; a outra metade é o que se faz com o que foi detectado. A primeira versão da
verificação de fontes estava tecnicamente correta e mesmo assim degradava o produto, porque
tratava descarte como se fosse solução.

---

## [2026-08-04 18:50] — Segunda pesquisa real: o que funcionou e os quatro furos

Pesquisa sobre B-optante com geração distribuída, duas rodadas completas, três motores.
Primeira execução com todas as travas ligadas.

### NÚMEROS

| | Rodada 1 | Rodada 2 |
|---|---|---|
| Duração | 258 s | 159 s |
| Custo real | US$ 0,807 | US$ 0,786 |
| Custo estimado | US$ 0,57 | US$ 0,42 |
| Agentes com falha | nenhum | Gemini |

Contribuição declarada no `meta.json`: GPT com 22 afirmações e 11 confirmadas, Grok com 14 e
10, Gemini com 9 e 5. Doze afirmações ficaram como fonte única e duas divergências não se
resolveram.

### O QUE FUNCIONOU

O ciclo fechou pela primeira vez de ponta a ponta. Uma afirmação sobre identificação do
B-optante na fatura da Enel perdeu a fonte na verificação, foi para a rodada 2, não se
confirmou e chegou ao relatório na seção de limitações, nomeada, com a consequência prática
explicada. Antes ela teria sumido sem deixar rastro.

Melhor ainda: a rodada 2 **refutou** uma afirmação sobre a Consulta Pública ANEEL 7/2025 e a
Nota Técnica 148/2025 tratarem do regime do B-optante. Informação falsa que teria entrado no
relatório como fato foi barrada pela segunda rodada. É exatamente o que o desenho existe
para fazer.

### TAXA DE URL FALSA POR MOTOR — o dado mais relevante

| Motor | URLs | Inventadas | Fora do tema | Total reprovado |
|---|---|---|---|---|
| Grok 4.20 multi-agent | 14 | 0 | 0 | 0 |
| GPT-5.6 Terra | 38 | 3 | 2 | 5 |
| Gemini 3.1 Pro | 23 | 7 | 1 | 11 |

O Gemini inventou 7 de 23 URLs, cerca de 30%, muito acima da faixa de 3% a 13% que a
literatura reporta. O Grok não produziu nenhuma reprovação em 14. Uma pesquisa não decide
nada, mas é o primeiro sinal comparável entre motores, e ele é forte.

### FURO 1 — a revalidação não alcançou o motor que mais precisa dela

O Gemini teve 7 URLs inventadas e **zero afirmações extraídas para revalidação**.

Causa: ele lista todas as URLs apenas na seção final de fontes, sem citar nada no corpo. A
posição do cabeçalho no texto era 6.878 de 7.718 caracteres, e todas as URLs reprovadas
estavam depois disso. A função `contexto_da_url` ignora, por desenho, ocorrências dentro da
lista final — ali é item de lista, não uso — e devolveu vazio para todas.

O mecanismo estava tecnicamente correto e inútil na prática. Fonte solta no rodapé não prova
nada e não dá para verificar: não há como saber o que se apoiava nela.

Correção na raiz: o prompt mestre passa a exigir que cada afirmação relevante traga a URL no
próprio parágrafo, e diz que afirmação sem link ao lado será tratada como não verificada.
Verificado logo depois num teste barato — com citação inline exigida, o trecho foi recuperado.

Defesa para quando isso falhar de novo: `reprovadas_sem_rastro` marca o agente em que todas
as fontes reprovadas ficaram sem trecho, com alerta grave no log, e nada dele pode contar
como confirmação.

Nota: a sessão que conduziu a pesquisa percebeu a limitação sozinha e escreveu nas limitações
do relatório que as URLs reprovadas do Gemini não sustentavam trecho específico. O relatório
saiu honesto apesar da falha do mecanismo.

### FURO 2 — falha do provedor entrando como sucesso

O Gemini na rodada 2 devolveu `finish_reason=error`, 700 caracteres, zero URLs — e entrou em
`agentes_ok`, porque o campo `erro` estava nulo. A rodada parecia ter dado certo nos três.

Correção: `finish_reason == "error"` passa a marcar o agente como falho.

### FURO 3 — estimativa ainda subestimando

US$ 0,57 estimado contra US$ 0,807 real na rodada 1, e US$ 0,42 contra US$ 0,786 na rodada 2.

Causa: o Grok lê muito mais do que o medido no primeiro teste — 422 mil tokens de entrada na
rodada 1 e 486 mil na rodada 2, contra os 232 mil que calibraram o `config.json`. E ele não
economiza na rodada 2: o prompt cirúrgico é pequeno, mas a busca dele não.

`tokens_input_busca` do Grok subiu de 200 mil para 450 mil. Nova estimativa para a mesma
pesquisa: entre US$ 0,77 e US$ 0,88, contra US$ 0,807 reais.

### FURO 4 — log que morria com a sessão

Apontado pelo Danilo. Todo o diagnóstico existia apenas na tela: fechada a sessão, não havia
como saber o que quebrou, onde nem por quê. Esta própria análise dependeu de reconstituir
tudo a partir dos JSON.

`abrir_log()` grava o log em arquivo ao lado do JSON da rodada, com cabeçalho de data e o
comando completo que originou a execução. Escrita protegida por trava, porque os agentes
rodam em paralelo. `log_excecao()` registra a pilha inteira. Falha ao gravar log nunca
derruba a pesquisa.

### CUSTO ACUMULADO

Duas pesquisas, US$ 4,00. A segunda saiu por US$ 1,59 com os três motores, contra US$ 2,57
da primeira — a troca do Perplexity pelo Grok economizou cerca de 40%.

### LIÇÃO

Uma trava pode estar correta linha a linha e não alcançar o caso que motivou sua criação. A
extração de contexto funcionava exatamente como especificada e produziu zero resultado no
motor com 30% de URLs inventadas, porque o formato de citação dele estava fora do que o
desenho pressupunha. Vale sempre perguntar em que formato de entrada a defesa deixa de valer.

---

## [2026-08-05 09:20] — Número variável de motores e o limite da validação cruzada

Entrada em resposta à nota da sessão do NossEnergia, que teve de editar o `config.json` no
meio de uma pesquisa para cumprir uma escolha do Danilo.

### O QUE A OUTRA SESSÃO ENCONTROU

O Danilo quis rodar com quatro motores, incluindo o Perplexity. O `config.json` tinha três
slots nomeados A, B e C, e o `buscar.py` só aceitava subconjunto dos slots existentes. Sem
slot, não havia como cumprir a escolha, e o `SKILL.md` mandava justamente não editar o
config — instrução que pressupunha um slot que não existia.

A saída foi criar um slot D à mão. Correta como remendo, perigosa como estado permanente:
`--agentes` era opcional, então qualquer execução futura que o omitisse passaria a chamar
quatro motores e a gastar US$ 1,15 a mais por rodada, sem ninguém pedir. A mitigação era um
aviso dentro de um campo de texto que nenhum código lê.

### CAUSA

O número de motores estava amarrado em dois lugares: as letras de slot no `config.json` e as
mesmas letras como chaves do `prompts_r2.json`. Havia ainda uma duplicação silenciosa —
`agentes` definia quem podia ser chamado e `motores_disponiveis` definia o cardápio oferecido
na clarificação. Os dois podiam divergir, e divergiram: o Perplexity estava no cardápio e não
era chamável.

### SOLUÇÃO — identificação por id, lista aberta

`agentes` e `motores_disponiveis` viraram uma lista só, `motores`, em que cada item tem um
`id` curto: `grok`, `gpt`, `gemini`, `perplexity`. O id é o mesmo nome usado em `--motores` e
nas chaves do `prompts_r2.json`. Acrescentar motor é acrescentar item na lista, sem tocar em
código e sem teto de quantidade.

`--motores` substitui `--agentes`, que continua aceito como apelido. Aceita o id ou o nome
completo do modelo, e erra com a lista de disponíveis quando o nome não existe.

**Só entra quem é `padrao: true` quando `--motores` é omitido.** É o que impede motor caro de
entrar por esquecimento, substituindo o aviso em campo de texto por comportamento de código.

`avisar_composicao()` passou a calcular as regras de desenho sobre o número escolhido, em vez
da constante três: motores repetindo o mesmo índice, ausência de árbitro com dois, análise
mais rasa acima de três, e o custo típico somado. Os avisos informam, não bloqueiam.

Verificação, com o Perplexity presente no config: sem `--motores`, rodam três e o custo
estimado fica em US$ 0,77 a 0,88; com os quatro, sobe para US$ 1,88 a 2,03 e o aviso de
análise mais rasa aparece. Um quinto motor, acrescentado só no config para teste, entrou sem
nenhuma alteração de código.

Efeito colateral pego na hora: o `motores.py` quebrou com `KeyError: 'agentes'`. Corrigido.
É o tipo de coisa que só aparece rodando os três scripts depois de mexer no formato do config.

### O ACHADO MAIS SÉRIO — consenso sobre ausência não é prova de ausência

Da mesma nota: na pesquisa de 04/08, os três motores afirmaram que nenhum dispositivo impunha
teto de 75 kW à potência de geração. O art. 23, § 6º, da REN ANEEL 1.000/2021 diz exatamente
isso. Nenhum dos três o localizou, e o erro só apareceu na conferência manual do texto
oficial.

Isto é mais grave que URL inventada, e por um motivo estrutural: URL falsa é detectável por
código, ausência falsa não deixa rastro nenhum. Pior, o desenho atual **premiava** o erro —
três motores concordando entrava como consenso, o grau mais alto de confiança do relatório.
A validação cruzada confirma o que os motores encontram; ela não diz nada sobre o que todos
deixaram de encontrar, e três buscas que falham pelo mesmo motivo parecem três confirmações.

Duas mudanças no `SKILL.md`.

Regra dura nova, a de número 8: nunca escrever "não existe" com base em concordância, e sim
"os motores não localizaram", dizendo onde se procurou. Quando a resposta negativa importa
para a decisão — e importa quase sempre, porque "não há impedimento" costuma virar
autorização — abrir a fonte primária.

Passo 5b, obrigatório para tema normativo e sempre que uma conclusão se apoiar em ausência:
abrir o texto oficial, não a matéria que o comenta nem o site que o compila. Motor de busca
alcança bem o que foi comentado e mal o que só existe no original. Não custa API, custa
minutos de leitura, e separa relatório utilizável de relatório que parece pronto.

### PENDÊNCIA DA NOTA JÁ RESOLVIDA ANTES

`tokens_input_busca` do Grok já estava em 450 mil, corrigido em 04/08 na análise da segunda
pesquisa, com as mesmas medições que a nota cita.

### LIÇÃO

Duas listas descrevendo a mesma coisa divergem, e a divergência aparece no pior momento — no
meio de uma pesquisa, com o usuário esperando. `agentes` e `motores_disponiveis` nasceram em
dias diferentes para propósitos parecidos, e a distância entre "está no cardápio" e "pode ser
chamado" foi o que obrigou a edição manual.

E a lição maior: um método de validação tem um domínio, fora do qual ele não só deixa de
ajudar como engana. Confirmação cruzada mede convergência entre buscas, não existência no
mundo. Vale perguntar de todo mecanismo de verificação qual pergunta ele responde de fato, e
qual ele apenas parece responder.

---

## [2026-08-05 10:20] — Índice de qualidade por motor e o que a literatura já mediu

### PERGUNTA DO DANILO

Desconfiança com o Gemini, que estaria inventando demais, e a dúvida se o problema é o uso
via API ou se sempre foi assim e ele não percebia na plataforma. Pediu um índice de qualidade
por motor e uma busca sobre trabalho anterior nesse tema.

### A DESCONFIANÇA ESTÁ CERTA E MEDIDA

Precisão de fonte nas duas pesquisas reais, calculada sobre as URLs que passaram na
verificação:

| Motor | URLs citadas | Reprovadas | Precisão |
|---|---|---|---|
| Grok 4.20 multi-agent | 52 | 5 | 90% |
| GPT-5.6 Terra | 120 | 12 | 90% |
| Perplexity Deep Research | 74 | 10 | 86% |
| Gemini 3.1 Pro | 57 | 13 | **77%** |

O Gemini é o pior dos quatro, com folga.

### E A LITERATURA JÁ SABIA

O DeepResearch Bench avalia agentes de pesquisa com dois frameworks, RACE para a qualidade do
relatório e FACT para abundância factual e confiabilidade de citação. Nele, o Gemini Deep
Research lidera em citações efetivas, com 111,21 em média, e fica atrás do Perplexity em
Citation Accuracy, onde a Perplexity marca 90,24%.

O padrão é geral e tem nome: quem cita mais, cita pior. Medições recentes mostram modelos da
OpenAI com o maior volume de atribuições e acerto factual entre 39% e 59%; Anthropic com menos
volume e acerto de 69% a 77%; Google no meio, entre 45% e 49%. Especificamente, o Gemini Deep
Research troca precisão por cobertura — 0,145 contra 0,269 de precisão, com 32,42 referências
por relatório contra 4,27.

A explicação proposta é diluição de atenção na síntese: agregar informação de muitas passagens
aumenta a chance de atribuir o fato à fonte errada.

Isso responde a dúvida do Danilo sobre API contra plataforma. O comportamento não é efeito do
acesso por API; é característica documentada do modelo, e ele já consumia isso antes sem ter
como perceber, porque não havia verificação de fonte.

### ÍNDICE IMPLEMENTADO

Três dimensões, com os nomes alinhados aos da literatura, calculadas sobre o que o sistema já
media:

- **Precisão de fonte**, equivalente ao Citation Accuracy: URLs aprovadas sobre URLs citadas
- **Taxa de confirmação**: afirmações que outro motor sustentou, sobre as que o motor trouxe
- **Confiabilidade operacional**: execuções sem falha nem truncamento

O índice combina as três com pesos 3, 2 e 1, de 0 a 100. Volume de fontes ficou de fora da
nota de propósito: premiar quantidade é premiar exatamente o comportamento que a literatura
associa a menor precisão. Volume continua visível como contexto, em coluna própria.

### SOBRE TRABALHO ANTERIOR

Orquestração multimodelo existe e é ativa: MARCH, debate adversarial com votação, frameworks
de papéis especializados em que um agente gera, outro verifica fatos e um terceiro confere
citações. Ganhos relatados de 67% a 85% de redução de alucinação.

Duas ressalvas úteis. Há trabalho mostrando cascata de alucinação, em que cadeias longas de
agentes reduzem a alucinação e também a acurácia factual — suprimir demais custa informação
verdadeira, o mesmo trade-off que apareceu aqui na regra de descartar afirmação com fonte
reprovada. E quase tudo é orquestração dentro de um provedor, com subagentes do mesmo modelo.
Orquestrar provedores diferentes, com índices de busca independentes, continua sendo raro.

---

## [2026-08-05 10:50] — A avaliação dos motores sai dos dados, não do texto

### O QUE O DANILO APONTOU

Concordou com a leitura sobre o Gemini, mas não com a forma. Hoje o modelo está ruim; amanhã
pode melhorar e outro piorar. Nada sobre desempenho pode estar escrito no código — fixo devem
ser apenas os limiares contra os quais o desempenho medido é comparado.

Ele tinha razão sobre algo que eu mesmo havia feito: o `config.json` trazia frases como
"Atenção: 7 de 23 URLs inventadas em 04/08" e "Zero URLs reprovadas" dentro do campo
`quando_usar`. Julgamento de desempenho congelado em arquivo de configuração, que vira mentira
na semana seguinte e ninguém lembra de corrigir.

### O QUE MUDOU

Todo julgamento saiu do `config.json`. O campo `quando_usar` voltou a descrever só
característica estável: qual índice o motor usa, como cobra, que parâmetro exige.

Entrou `limiares_qualidade`, que é a régua e nada além dela: precisão de fonte confiável a
partir de 90% e em atenção a partir de 80%; índice geral confiável a partir de 80 e em atenção
a partir de 65; mínimo de 20 URLs e 2 pesquisas para classificar qualquer motor. Mexer nesses
números muda a régua, nunca o resultado de um motor específico.

### NOVO — scripts/qualidade.py

Varre todas as pesquisas feitas e calcula, por motor:

- **precisão de fonte** — URLs aprovadas sobre citadas, equivalente ao Citation Accuracy
- **taxa de confirmação** — afirmações que outro motor sustentou, sobre as que ele trouxe
- **confiabilidade** — execuções sem incidente, com falha total pesando 1 e truncamento 0,5

O índice combina as três com os pesos do config e a faixa sai da comparação com os limiares.
Daí deriva o **papel** do motor na próxima pesquisa: confirmação, confirmação com ressalva,
descoberta ou em avaliação. Nenhum desses rótulos é escrito à mão em lugar nenhum.

Grava `qualidade-motores.json` com a foto atual e o histórico, uma linha por motor por
pesquisa. O motor é identificado pelo modelo, não pelo id nem pela letra, para que a série
sobreviva a renomeações e trocas de slot.

Primeira medição, com três pesquisas:

| Motor | Pesq. | URLs | Precisão | Confirm. | Confiab. | Índice | Faixa |
|---|---|---|---|---|---|---|---|
| Grok 4.20 multi-agent | 2 | 52 | 90% | 73% | 100% | 86,2 | confiável |
| GPT-5.6 Terra | 3 | 120 | 90% | 48% | 92% | 76,1 | atenção |
| Perplexity Deep Research | 2 | 74 | 86% | 67% | 40% | 72,1 | atenção |
| Gemini 3.1 Pro | 3 | 57 | 77% | 56% | 80% | 70,4 | atenção |

Correção feita durante o teste: falha total e truncamento pesavam igual, e isso zerava a
confiabilidade do Perplexity, que tinha falhado uma vez e truncado outra. Perder tudo e perder
o fim não são a mesma coisa.

### CICLO FECHADO

Passo 3b novo no `SKILL.md`: antes de analisar, consultar o papel de cada motor. Passo 7
passa a rodar o `qualidade.py` junto com o painel, de modo que cada pesquisa concluída
realimente a régua e a seguinte já use a nota atualizada.

O uso da skill virou o benchmark. Não há avaliação separada a manter.

### VIÉS DE DOMÍNIO — verificação para o próximo teste

O Danilo vai usar a skill em tema de estilo pessoal e vestuário. Varredura nos arquivos de
instrução encontrou uma única menção de domínio, e como exemplo de regra geral.

Um caso descoberto na verificação: o passo 5b pressupõe fonte primária, que não existe em tema
de gosto ou comportamento. O risco muda de lugar — em vez de norma inventada, preferência
apresentada como regra e convenção de nicho apresentada como consenso. Instrução acrescentada:
separar fato verificável de recomendação, recomendação leva o nome de quem recomenda, e três
motores concordando sobre o que "se deve fazer" costuma indicar que leram o mesmo tipo de
conteúdo, não consenso no mundo.

### LIÇÃO

Dado sobre desempenho envelhece; régua não. Escrever "este modelo é ruim" num arquivo de
configuração parece documentar, mas é congelar uma medição de um dia e transformá-la em regra
permanente que ninguém revisa. A separação certa é a que o Danilo apontou: o sistema guarda o
critério, os dados guardam o veredito.

---

## [2026-08-05 11:05] — Nota com data, log de erros e o que a pesquisa de hoje revelou

### CONFERÊNCIA PEDIDA PELO DANILO

Três exigências: a nota de qualidade tem de ficar gravada, com data, e o log de erros tem de
ser acompanhado. A conferência achou as três incompletas.

A nota tinha data só no cabeçalho do arquivo, e a foto era sobrescrita a cada execução: não
havia como saber se um motor melhorou ou piorou. O histórico registrava a contagem de
incidentes, não quais foram. E não havia registro do motivo de cada URL reprovada.

### CORRIGIDO

`serie_notas`: uma medição por motor por dia, nunca sobrescrita. Rodar duas vezes no mesmo dia
atualiza a linha em vez de duplicar. É o que permite acompanhar evolução, e o script passa a
mostrar a variação do índice desde a última data medida.

`erros` por linha do histórico, com rodada, tipo e detalhe: falha, truncado, sem fontes,
reprovadas sem rastro. E `reprovadas_por_motivo`, com a contagem por estado — inventada,
fora do tema, inexistente, suspeita, inconclusiva.

O quadro por motivo, na primeira medição:

| Motor | Motivos das reprovações |
|---|---|
| GPT-5.6 Terra | fora do tema 4 · inconclusiva 3 · inexistente 5 |
| Gemini 3.1 Pro | fora do tema 1 · inconclusiva 5 · **inventada 7** |
| Grok 4.20 | fora do tema 2 · inconclusiva 1 · suspeita 2 |
| Perplexity | fora do tema 2 · inconclusiva 3 · inexistente 4 · suspeita 1 |

O Gemini é o único com URLs classificadas como inventadas — sem registro no arquivo da
internet, ou seja, provavelmente nunca existiram. Nos outros, o que aparece é página que saiu
do ar ou fonte fora do assunto.

Bug corrigido no teste: ordenação dos erros comparava dicionários quando data e motor
empatavam.

### O QUE A PESQUISA DE HOJE MOSTROU

Três verificações sobre correções recentes, na pesquisa de minigeração acima de 75 kW.

**Log em arquivo: funcionou.** `r1.log` e `r2.log` gravados na pasta, com comando e etapas.

**Migração para ids: sobreviveu a acontecer no meio.** A rodada 1, das 09:13, rodou com os
slots antigos A, B, C e D; a rodada 2, das 09:33, já rodou com `gpt`, `grok` e `perplexity`. A
refatoração entrou entre as duas e nada quebrou.

**Correção do prompt inline: não chegou.** O `prompt_mestre.md` daquela pesquisa não tem a
exigência de citar a URL junto da afirmação, e o resultado apareceu no dado: `sem_rastro` em
três dos quatro motores na rodada 1 e em dois dos três na rodada 2. A revalidação continuou
sem alcançar quase nada.

Causa: a correção foi gravada em 04/08 às 18:50, e a sessão que conduziu a pesquisa já estava
aberta com a versão anterior dos arquivos em contexto. Edição em arquivo de skill não alcança
sessão em andamento.

### LIÇÃO OPERACIONAL

Correção de skill vale a partir da próxima sessão, não da próxima pesquisa. Sessão longa
carrega a versão do momento em que abriu e segue com ela até fechar. Quando uma correção
importa para o resultado — e a de citação inline importava —, vale abrir sessão nova em vez de
continuar na que está.

---

## [2026-08-05 11:45] — Dado de uso não é parte do produto

### PERGUNTA DO DANILO

Quem clona o repositório e instala a skill herda as notas de qualidade dos motores, ou começa
do zero? A pergunta expôs um erro de classificação que eu tinha cometido sem perceber.

### O ERRO

`skill/qualidade-motores.json` estava versionado, porque mora dentro de `skill/`. Dois
problemas distintos.

O primeiro é de privacidade: o campo `historico` lista o nome da pasta de cada pesquisa, e o
nome da pasta é o tema. As três pesquisas feitas apareciam identificadas no repositório
público. Não é conteúdo nem cliente nomeado, mas revela no que o usuário trabalha, e ninguém
autorizou isso.

O segundo é de projeto, e é o que a pergunta do Danilo apontou: nota de motor calculada sobre
as pesquisas de outra pessoa não diz nada sobre o uso de quem instala. Pior, contamina a série
dele desde o primeiro dia com uma linha de base que não é sua.

A raiz do erro foi de classificação. `outputs/` sempre esteve no `.gitignore` por ser dado de
uso. O arquivo de qualidade é exatamente a mesma categoria — dado derivado do uso — mas como
ficava dentro da pasta do código, entrou junto sem ninguém questionar.

### CORRIGIDO

`skill/qualidade-motores.json` foi para o `.gitignore`. Instalação nova começa a própria série
do zero, e o script passa a explicar isso em vez de imprimir uma seção vazia: até acumular o
mínimo de pesquisas e URLs, todos os motores são tratados como confirmação com ressalva.

`catalogo-motores.json` continua versionado. É o catálogo público do OpenRouter classificado,
sem nenhum dado de uso, e poupa a primeira consulta de quem instala.

O conhecimento agregado foi para o README, sem identificar pesquisa: a faixa de precisão
observada entre motores, a observação de que o pior foi também o único a produzir URLs sem
registro no arquivo da internet, e o vínculo com a literatura sobre o trade-off entre volume e
precisão de citação. Ordem de grandeza para quem for calibrar os limiares, declarada como
experiência de um usuário e não como benchmark.

### LIMPEZA DO HISTÓRICO

O arquivo já estava público em commits anteriores. Repositório apagado e recriado, como da
outra vez.

Armadilha encontrada no caminho: recriar a partir do repositório local traria o arquivo de
volta, porque ele continuava em doze commits do histórico local. Foi preciso reescrever o
histórico com `git filter-branch --index-filter` antes de recriar, e depois apagar as refs de
backup que o próprio filter-branch cria em `refs/original/` — sem isso, o arquivo continua
alcançável e a verificação acusa. Os doze commits foram preservados; só o arquivo saiu deles.

Verificação final: busca por cada um dos três temas no repositório remoto devolve zero
ocorrências, e o arquivo responde 404.

### LIÇÃO

A pergunta certa sobre qualquer arquivo novo não é onde ele mora, é de onde ele vem. Um
arquivo gerado pelo uso é dado do usuário, mesmo quando fica na pasta do código, e ir para o
repositório por proximidade de diretório é acidente de organização, não decisão.

Vale como regra geral para este projeto: antes de versionar arquivo que algum script escreve,
perguntar se ele existiria numa instalação que nunca rodou nada. Se não existiria, é dado de
uso e não entra.

---

## [2026-08-12 16:35] — Auditoria do BACKLOG: a cascata que invalida motor bom

### OBJETIVO

Avaliar os sete itens do `BACKLOG.md`, aberto às 16:17 a partir das duas pesquisas de Medellín,
antes de consertar qualquer coisa. O pedido foi documentar a avaliação primeiro, porque quem
retomar isto daqui a meses precisa saber o que já foi medido, o que caiu e por quê — sem repetir
a investigação.

Nada de código foi alterado nesta entrada. O plano de correção está no fim, ainda por aplicar.

### MÉTODO

Cada item foi conferido contra o código em `skill/scripts/` e contra os sete `r1.json` e `r2.json`
do histórico (03/08 a 12/08), e não apenas contra as duas pesquisas que originaram o backlog. As
quatro URLs acusadas de "fora do tema" foram baixadas manualmente com `curl` para medir tipo de
conteúdo, tamanho do texto legível e posição dos termos dentro da página.

### O QUE SE CONFIRMA

O mapeamento posicional das citações do Perplexity é real. Os sete pares da tabela do backlog
foram testados na pesquisa de primeira pesquisa de 12/08: sete de sete. E a razão é estrutural, o
que torna a correção segura: o corpo do relatório do Perplexity não contém URL nenhuma, todas vêm
das `annotations` da API em `buscar.py:176-181`, na ordem de citação, e a seção "URLs capturadas"
é escrita pelo próprio script. O marcador `[N]` casa com a N-ésima annotation por construção.

Risco de implementação que o backlog não previu: `extrair_urls` deduplica. Se o motor citar a
mesma página em duas annotations, todos os índices seguintes deslocam, e a salvaguarda proposta
(maior `N` menor ou igual ao número de URLs) não pega esse caso. O conserto correto guarda a
lista de annotations com o índice original, separada da lista deduplicada.

### O QUE MUDA NO DIAGNÓSTICO

**A ordem da cascata está invertida no backlog.** O ALERTA GRAVE em `buscar.py:691` dispara
quando todas as fontes reprovadas ficam sem trecho associado. Sem reprovação nenhuma, não há
alerta. Quem reprovou as fontes do Perplexity nas duas pesquisas foi a conferência de tema, que é
o item 2. A cadeia real: o item 2 reprova página boa, o item 1 impede o resgate do trecho, o item
6 invalida o motor inteiro. Consertar o item 2 desarma os três casos observados; consertar o item
1 sozinho deixa o gatilho de pé.

**O item 2 tem três causas, com conserto diferente para cada uma.** Medido URL a URL:

| URL reprovada | Tipo devolvido | Texto legível | Causa real |
|---|---|---|---|
| `domesdaybook.net/.../mills` | text/html | 16.950 chars, com "mill" no começo | termo passado foi `watermill`/`milling`, nunca a raiz `mill` |
| `hdr.undp.org/content/energising-human-development` | text/html | 8.467 chars | os termos aparecem depois dos 4.000 chars lidos |
| `elibrary.imf.org/.../article-A005-en.xml` | text/html | 28.502 chars | mesma causa, agravada por 622 KB de HTML bruto |
| `econstor.eu/.../1694107760.pdf` | text/html, 4.732 bytes | 1.655 chars | parede de cookie no lugar do PDF |

O casamento em `buscar.py:529` já é por prefixo, então `mill` pegaria "mills" e "milling" — a raiz
é que nunca foi passada. Metade desse item se resolve na instrução de uso do `--termos`, sem tocar
em código. E o estado "inconclusiva" para página vazia já existe em `buscar.py:525`, com limiar de
250 caracteres; o intersticial do econstor tem 1.655 e passa por página real.

**O item 4 cai.** O custo do Grok é 89% entrada. Na pesquisa de energia: 402.914 tokens de entrada
a US$ 0,50 contra 25.512 de saída a US$ 0,064. `reasoning_effort` atua sobre a saída, economizaria
cerca de cinco centavos e arriscaria qualidade. O único estouro real da série foi 05/08, com
563.513 tokens de entrada contra a faixa de 420 a 490 mil declarada no config, ou seja, variação
de material lido. O item 4 é absorvido pelo item 5, que já aponta a alavanca certa.

### O QUE FALTAVA NO BACKLOG

**Item 8 — estado inconclusivo conta como reprovação em dois lugares onde não devia.** Em 05/08,
na pesquisa de regulação de 05/08, um motor foi invalidado por ALERTA GRAVE tendo como únicas reprovações duas
URLs inconclusivas, que são falha de SSL e timeout do próprio verificador. E `qualidade.py:75`
soma `len(urls_problematicas)` inteiro no contador de reprovadas, sem separar estado.

**Item 9 — a régua de qualidade está viciada, e ela sustentou decisão tomada hoje.** Das 145
reprovações do histórico, 71 são "fora do tema" (49%) e 17 são "inconclusiva" (12%): 61% do total
vem de estados que não indicam invenção.

| Motor | URLs | Reprovadas | Precisão registrada | Só falhas duras |
|---|---|---|---|---|
| Grok 4.20 Multi-Agent | 479 | 40 | 0,916 | 0,975 |
| GPT-5.6 Terra | 343 | 39 | 0,886 | 0,959 |
| Perplexity Deep Research | 114 | 19 | 0,833 | 0,947 |
| Gemini 3.1 Pro | 110 | 47 | 0,573 | 0,773 |

A decisão de 12/08 de tirar o Gemini do padrão continua de pé: ele segue o pior em qualquer régua
e é o único com URL inventada (7, contra zero dos outros dois motores padrão). O número que a
justificou é que está errado. Quem merece reexame é o Grok, que tem a melhor precisão da série e
saiu do padrão por custo.

**Item 10 — o ALERTA GRAVE disparou em seis das sete pesquisas**, e alcança qualquer motor. Pegou
dois motores em 05/08 e pegou o Grok na pesquisa de pesquisa de infraestrutura de hoje, a mesma que
fundamentou a decisão sobre OpenRouter. O prejuízo é maior que os US$ 1,72 contabilizados no
backlog para o Perplexity.

### DADOS DE APOIO

Custo e falha por motor, série completa, extraídos dos `r*.json`:

| Pesquisa | Motor | Entrada | Saída | US$ | Estados de reprovação |
|---|---|---|---|---|---|
| 05/08 regulação (profunda) | A | 563.513 | 27.062 | 0,6014 | fora do tema 1 · sem rastro |
| 05/08 regulação | C | 2.267 | 6.224 | 0,1352 | inconclusiva 2 · sem rastro |
| 05/08 regulação | D | 2.448 | 15.931 | 0,8731 | truncado (length) · sem rastro |
| 12/08 infraestrutura | grok | 278.643 | 20.047 | 0,4849 | fora do tema 4 · sem rastro |
| 12/08 primeira | perplexity | 1.465 | 8.938 | 0,7609 | truncado · sem rastro |
| 12/08 segunda | perplexity | 1.614 | 9.894 | 0,9590 | fora do tema 5 · truncado · sem rastro |

Sobre o truncamento do item 3: o corte acontece sempre entre 75% e 80% do teto declarado, nos dois
modos (15.931 de 20.000 em profunda; 8.938 e 9.894 de 12.000 em normal). O padrão é compatível com
tokens de raciocínio contando contra o limite sem aparecer em `completion_tokens`. O script já pede
`usage: {include: true}` em `buscar.py:560` e lê apenas `completion_tokens` em `buscar.py:647`:
salvar o `usage` bruto responde a pergunta sem gastar pesquisa nova.

### PLANO DE CORREÇÃO — ordem e razão

1. Item 2, a conferência de tema, que é o gatilho de toda a cascata. Três consertos localizados em
   `verificar_tema` e `_texto_do_html`: casar por raiz curta, ler todo o texto legível em vez dos
   primeiros 4.000 caracteres, e reconhecer intersticial como inconclusiva. Mais uma linha no
   `SKILL.md` sobre passar raiz em `--termos`.
2. Item 8, excluindo "inconclusiva" do gatilho do alerta e do contador de qualidade. Duas linhas.
3. Itens 1 e 6 juntos, que são o mesmo conserto: resolver `[N]` pelo índice de annotation e graduar
   a quarentena para alcançar as afirmações afetadas em vez do motor inteiro.
4. Recalcular `qualidade-motores.json` com a régua corrigida, antes de qualquer decisão nova sobre
   composição de motores.
5. Item 3, salvando o `usage` bruto para confirmar a hipótese do raciocínio.
6. Item 5, estimativa do Grok por faixa de entrada observada. O item 4 morre aqui.
7. Item 7, aviso de perda de árbitro em tempo de execução.

### LIÇÕES

Verificação que reprova fonte boa custa mais caro que verificação ausente. Quando a régua erra, o
motor perde a contribuição inteira, a nota dele cai e a decisão seguinte sobre qual motor usar sai
enviesada — o erro se propaga para fora do arquivo onde nasceu.

Antes de acusar o motor, olhar a régua. O sinal está no dado: quando o mesmo domínio é reprovado
para dois motores diferentes na mesma pesquisa, a hipótese de falha de verificação é mais provável
que a de coincidência de alucinação. O `hdr.undp.org` reprovado para GPT e Perplexity na pesquisa
de energia é o caso exemplar.

Backlog escrito no calor da pesquisa acerta os sintomas e erra a causa. Os sete itens estavam bem
observados, com dois deles apontando causa trocada, porque foram escritos a partir do que apareceu
no log e não do código nem da série histórica. Vale como método: antes de consertar item de
backlog, reconferir contra o código e contra todas as execuções, não só a que doeu.

Separar estado de verificação por gravidade é decisão de projeto, não detalhe. Existir, tratar do
tema e não ter dado para concluir são três coisas distintas, e hoje as três caem no mesmo balde de
`urls_problematicas`. Todo consumidor desse balde (alerta, revalidação, índice de qualidade) herda
a confusão.

---

## [2026-08-12 19:05] — Conserto da cascata: gravidade de estado, citação numerada e teto por motor

### OBJETIVO

Aplicar as correções apuradas na auditoria das 16:35 e na revalidação das 18:30, que incluiu
as duas rodadas 2 inexistentes na primeira apuração. Sete itens do backlog tocados, com teste
para cada um antes de seguir ao próximo. Nenhuma chamada de API foi gasta: tudo verificado
contra páginas reais e contra as respostas já salvas em `outputs/`.

### O QUE MUDOU

**1. Gravidade de estado, em `buscar.py`.** `FALHAS_DURAS` (inexistente, inventada, suspeita,
removida) e `SINAIS_FRACOS` (fora do tema, inconclusiva) passam a ser explícitos, com a função
`duras()` para filtrar. Os três consumidores que liam o mesmo balde — quarentena, alerta e
índice de qualidade — passam a ler o que lhes cabe.

**2. Alerta deixa de ser binário.** `reprovadas_sem_rastro` agora se calcula só sobre falha
dura e significa que uma afirmação específica ficou sem rastro, não que o agente inteiro está
descartado. Campos novos no JSON: `falhas_duras`, `falhas_duras_sem_rastro`, `urls_fora_do_tema`.
O markdown por agente separa "ALERTA DE FONTE" de "SINAL FRACO", com texto dizendo o que cada
um autoriza concluir.

**3. Citação numerada resolvida no parser.** `urls_das_citacoes()` guarda as annotations na
ordem original, com repetições, e `contexto_da_url()` ganhou `_contexto_por_marcador()`, que
resolve `[N]` para a N-ésima citação. Duas travas: a numeração só vale se o maior marcador do
texto couber na lista, e só se resolve marcador que exista no corpo. A lista com repetições é
o ponto delicado — a lista deduplicada de `extrair_urls` deslocaria todos os índices seguintes
a uma página citada duas vezes, trocando a fonte de cada afirmação em silêncio.

**4. Conferência de tema, três consertos.** `_raizes()` deriva raiz por sufixo e quebra termo
composto, então `milling` alcança "mill" e "mills". `_texto_do_html()` deixou de cortar o corpo
em 4.000 caracteres, e `BYTES_POR_PAGINA` subiu de 120 KB para 1,5 MB. `_muro_ou_casca()`
reconhece muro de acesso, desafio de robô e casca de JavaScript, e devolve `inconclusiva` em
vez de `fora do tema`. Documento sem HTML continua não gerando registro nenhum, porque PDF em
fonte acadêmica é o esperado.

**5. Teto de saída por motor.** `teto_de_saida()` lê `max_tokens` do config por rodada, com o
teto do modo como padrão. O Perplexity declara 20.000 na rodada 1 e 12.000 na rodada 2.

**6. Estimativa por faixa.** `tokens_input_busca` aceita `{tipico, max}`, e o Grok passa a ser
estimado entre 420 e 730 mil tokens de entrada, medidos.

**7. Composição efetiva ao fim da rodada.** O script recontava os motores só na largada. Agora
avisa quando o número de motores elegíveis cai durante a execução, e repete o aviso de falta de
árbitro com o número que sobrou.

**8. Índice de qualidade, em `qualidade.py`.** `reprovadas` conta só falha dura, `sinais_fracos`
conta o resto, e `QUEBRA_DE_SERIE` marca 12/08/2026 para que a mudança de régua não apareça no
painel como se os motores tivessem melhorado sozinhos.

**9. Config.** Grok volta a `padrao: true`, com a razão registrada no próprio arquivo.

### RESULTADOS

Teste 1, raízes. `watermill,windmill,moinho,molino,engenho,sailing,steam,milling` passa a gerar
também `mill` e `sail`.

Teste 2, as quatro URLs que eram falso positivo, conferidas contra as páginas reais:

| URL | Antes | Agora |
|---|---|---|
| `domesdaybook.net/.../mills` | fora do tema | passa |
| `hdr.undp.org/content/energising-human-development` | fora do tema | passa |
| `elibrary.imf.org/.../article-A005-en.xml` | fora do tema | passa |
| `econstor.eu/.../1694107760.pdf` | fora do tema | inconclusiva, com o motivo certo (Anubis) |

O caso do FMI só passou depois de subir o limite de bytes: o artigo tem 622 KB de HTML e a
primeira ocorrência de "consumption" está no caractere 14.956 do texto limpo, fora do alcance
antigo. A palavra "electricity" não aparece uma vez sequer nele, e "energy" aparece 76 — daí a
instrução nova no SKILL.md de passar o termo genérico do domínio junto dos específicos.

Teste 3, recuperação de trecho, reprocessando as respostas salvas das três pesquisas de 12/08:

| Pesquisa | Rodada | Motor | Trecho antes | Trecho agora |
|---|---|---|---|---|
| primeira pesquisa de 12/08 | 1 | perplexity | 0 de 4 | 2 |
| primeira pesquisa de 12/08 | 2 | perplexity | 0 de 2 | 2 |
| segunda pesquisa de 12/08 | 1 | perplexity | 0 de 5 | 5 |
| segunda pesquisa de 12/08 | 2 | perplexity | 0 de 7 | 3 |

Nenhum outro motor mudou de comportamento, o que é o esperado: os que escrevem a URL ao lado da
afirmação já eram lidos pela busca literal.

Notas recalculadas, sete pesquisas e 22 medições:

| Motor | URLs | Falha dura | Sinal fraco | Precisão | Índice | Papel |
|---|---|---|---|---|---|---|
| Grok 4.20 Multi-Agent | 501 | 12 | 31 | 0,976 | 89,3 | confirmação |
| GPT-5.6 Terra | 360 | 14 | 29 | 0,961 | 80,4 | confirmação |
| Perplexity Deep Research | 151 | 7 | 21 | 0,954 | 77,3 | confirmação com ressalva |
| Gemini 3.1 Pro | 110 | 25 | 22 | 0,773 | 72,5 | confirmação com ressalva |

O Perplexity fica em "atenção" pela confiabilidade de 44%, que é o truncamento das quatro
chamadas, e não pela citação. É o número que o teto próprio de saída deve mover na próxima
pesquisa, e é o teste que decide se ele continua no padrão.

O Gemini sai de crítico e continua o pior, com as 7 URLs inventadas de toda a série. A decisão
de deixá-lo fora do padrão se mantém, agora apoiada na invenção e não na nota.

### O QUE NÃO FOI FEITO

A verificação de que a fonte sustenta a afirmação continua pendente, e é o buraco de fundo: a
skill confere endereço, não confere conteúdo. Todos os dez itens do backlog são manifestações
disso.

### LIÇÕES

Régua de verificação é código de produção e merece o mesmo cuidado que o resto. Ela decide o
que entra no relatório, quanto vale cada motor e o que se compra na próxima pesquisa. Errada,
ela não avisa: produz descarte silencioso com aparência de rigor.

Estado de verificação precisa carregar gravidade desde o desenho. Existir, tratar do tema e não
ter dado para concluir são três coisas distintas, e um balde único faz cada consumidor herdar a
confusão dos outros.

Correção de régua quebra série histórica, e a quebra precisa ser declarada dentro da ferramenta.
Sem a marca, o painel mostraria quatro motores melhorando no mesmo dia, o que é leitura errada
de um conserto nosso.

Teste retroativo em resposta já salva vale mais que teste sintético e não custa nada. As quatro
recuperações de trecho e as quatro URLs conferidas usaram material que já estava em disco: o
conserto foi medido contra o caso real que o originou, sem gastar um centavo de API.

---

## [2026-08-13 14:15] — Auditoria adversarial derruba parte do conserto, e o conserto do conserto

### OBJETIVO

O Danilo pediu que um agente independente auditasse o trabalho da véspera, com instrução
explícita de derrubá-lo: "a minha impressão é que nós mesmos estamos criando problemas por nós
mesmos". A auditoria rodou sem acesso ao raciocínio de quem escreveu o código, com proibição de
editar arquivo e de gastar chamada paga.

Valeu a pena. Ela achou uma regressão grave, uma perda de segurança e um consumidor esquecido.

### O QUE A AUDITORIA PEGOU

**1. A conferência de tema virou peneira aberta. Regressão introduzida no conserto anterior.**
O casamento por prefixo com raiz curta fazia `mill` casar "million", "millennium" e
"milliondollar". A página da Wikipédia sobre o Instagram passava numa pesquisa sobre moinhos
medievais, e o mesmo valia para Bitcoin e insulina. Das 84 reprovações históricas por tema,
o veredito novo aprovava a maioria — a camada que existe para pegar "acertou o domínio e
inventou o caminho" tinha deixado de pegar qualquer coisa.

**2. URL fabricada que responde 200 saiu da revalidação.** Ao excluir `inconclusiva` de
`afirmacoes_a_revalidar`, as três URLs inventadas pelo Gemini na pesquisa de contingência
(`youtube.com/watch?v=vibecoding-tutorial-2026` e irmãs, todas HTTP 200 com página curta)
deixariam de ir para a rodada 2. É o modo de falha que a regra dura 2 do SKILL.md chama de
mais perigoso do produto, reintroduzido por descuido meu.

**3. Havia um quarto consumidor da régua.** `dashboard.py` calcula precisão e índice próprios e
ficou na régua velha. O painel gerado às 19:05 publicava 43 URLs reprovadas do Grok e precisão
de 91% enquanto o `qualidade.py`, no mesmo minuto, publicava 12 e 98%. O painel é o artefato que
se abre com duplo clique.

**4. O resolvedor de marcador lia uma fração do texto.** Copiei do `_contexto_literal` o corte
por cabeçalho de fontes, e "referências", "sources" e "fontes:" são palavras comuns no meio da
análise. Em uma das respostas o corte reduziu o corpo a 4,8% do relatório, no meio de uma frase
sobre engenhos de açúcar.

**5. Sinal fraco rebaixava falha dura.** `verificar_tema` sobrescrevia `suspeita` com
`fora do tema` sem guarda, e com a régua nova isso lavava a acusação: `scorasacademy.com.br`,
marcada por ser domínio raiz, deixou de pesar contra o motor.

Mais quatro erros de número e de documentação: a faixa de entrada do Grok gravada no config
(mínimo real 179.296 e não 278.643, fator 4,0 e não 2,6), a atribuição dos 44% de confiabilidade
do Perplexity só às quatro chamadas de 12/08 quando são nove execuções com oito truncamentos e
uma falha, a linha "três pesquisas feitas" que sobrou no ESTADO.md, e o README público
descrevendo uma composição padrão que não existe mais.

### O QUE MUDOU AGORA

`SUFIXOS_ACEITOS` fecha o casamento em fronteira de palavra, aceitando só flexão: `mill` alcança
"mills", "milling" e "milled", e não alcança "million". O sufixo agentivo `-er` ficou de fora
numa segunda passagem, porque `mill` mais `er` casa o sobrenome Miller, que aparece em qualquer
bibliografia. E `TEXTO_LONGO` resolve o caso residual: menção única num documento acima de 30 mil
caracteres não sustenta que a página trate do assunto — a página sobre insulina traz "Mills GB"
numa referência e passaria.

`afirmacoes_a_revalidar` volta a incluir todo estado com trecho, inclusive `inconclusiva`.
`verificar_tema` só marca `fora do tema` quando o estado ainda é `ok`. `_contexto_por_marcador`
lê o corpo inteiro e descarta marcador que esteja em linha de lista de fontes, identificada por
conter URL. `dashboard.py` importa a régua de `buscar.py`, como o `qualidade.py`.

### RESULTADOS

Peneira, com os termos reais da pesquisa de história:

| Página | Antes do conserto de ontem | Depois de ontem | Agora |
|---|---|---|---|
| Wikipédia, Instagram | fora do tema | passava | fora do tema |
| Wikipédia, Bitcoin | fora do tema | passava | fora do tema |
| Wikipédia, insulina | fora do tema | passava | fora do tema |

As quatro URLs que motivaram tudo continuam corretas: domesdaybook, PNUD e FMI passam, e o
econstor fica inconclusiva pelo desafio anti-robô.

Recuperação de trecho por marcador, com o corte consertado:

| Pesquisa | Rodada | Motor | Ontem | Agora |
|---|---|---|---|---|
| primeira pesquisa de 12/08 | 1 | perplexity | 2 | 4 de 4 |
| primeira pesquisa de 12/08 | 2 | perplexity | 2 | 2 de 2 |
| segunda pesquisa de 12/08 | 1 | perplexity | 5 | 5 de 5 |
| segunda pesquisa de 12/08 | 2 | perplexity | 3 | 6 de 7 |
| pesquisa de infraestrutura | 1 | grok | 0 | 2 de 4 |

As três URLs fabricadas do Gemini voltam para a rodada 2, com trecho.

Efeito líquido sobre o histórico: das 46 URLs marcadas `fora do tema` em pesquisas cujos termos
estão registrados no log, 24 passam, 16 viram inconclusiva e 6 continuam fora do tema. As seis
são páginas de varejo, um post do Instagram e uma resolução do BIPM, em pesquisas onde não
tinham o que fazer.

Painel e medidor voltam a concordar: 12 reprovadas e 98% para o Grok nos dois.

### O QUE FICA COMO LIMITAÇÃO CONHECIDA

Página de comércio renderizada por JavaScript com muito texto de navegação continua caindo em
`fora do tema` em vez de `inconclusiva`: `cea.com.br/jeans/masculino/bermudas` é reprovada numa
pesquisa que tinha "bermuda" entre os termos. O detector de casca só alcança página curta.

`kuprienko.info`, com o texto de Luis Capoche sobre Potosí, continua reprovada numa pesquisa
sobre Potosí, e a causa é vocabulário: a fonte é em espanhol e usa "ingenios", enquanto os termos
foram passados em inglês e português. É o caso que a instrução nova do SKILL.md cobre.

E a armadilha de deduplicação que o código trata continua sem exercício real: nenhuma resposta
salva do Perplexity repete URL entre citações, então a trava foi verificada só em teste
sintético.

### LIÇÕES

Auditor adversarial paga por si. Foram cinco defeitos reais em código que eu tinha declarado
testado, sendo dois deles piores que o problema original: a peneira aberta e a URL inventada
saindo da revalidação. Testar o caso que motivou o conserto não é testar o conserto.

Todo aperto de régua precisa de um caso negativo no teste. Meu teste da véspera só perguntava
"a página boa passa?". Faltava a outra metade, "a página ruim continua sendo pega?", e é onde a
regressão morava.

Quando se muda uma definição compartilhada, o passo obrigatório é procurar todos os leitores dela
antes de declarar pronto. Eu contei três consumidores porque foram os três que lembrei, e o
quarto era justamente o que o Danilo abre com duplo clique.

Conserto sob pressão reintroduz o erro que o produto já tinha aprendido a evitar. A exclusão de
`inconclusiva` da revalidação desfez, sem querer, a regra dura que estava escrita no SKILL.md
desde 04/08. Regra dura merece teste que a defenda, e não só um parágrafo em documento.

---

## [2026-08-13 14:47] — Segunda auditoria adversarial: nove correções, e um achado do auditor que não procede

### OBJETIVO

Segunda rodada do ciclo pedido pelo Danilo. Um agente independente atacou especificamente as
correções da véspera, com as mesmas proibições: não editar arquivo, não gastar chamada paga,
reproduzir cada afirmação antes de aceitá-la.

Veredito dele: não se sustenta. Estava certo em quase tudo.

### O QUE ELE PEGOU, E O QUE FOI FEITO

**1. O corte cego sobrevivia no caminho principal.** Consertei `_contexto_por_marcador` e deixei
`_contexto_literal` intacto, que é justamente por onde passam GPT, Grok e Gemini, os três motores
que escrevem a URL ao lado da afirmação. Agora nenhum dos dois corta por cabeçalho: a ocorrência
em item de lista se reconhece pela linha, via `_e_linha_de_lista`, que olha marcador de lista e
proporção de texto fora da URL.

**2. Cabeçalho `Range` provocando HTTP 416.** Servidor cujo arquivo é menor que o fim da faixa
recusa o pedido. Um PDF do MPRA responde 416 para `bytes=0-1500000` e 200 sem o cabeçalho.
Removido: lê-se N bytes do fluxo, o que tem o mesmo efeito e não depende do servidor.

**3. Painel e medidor discordavam em tudo menos nas duas colunas que eu conferi.** `dashboard.py`
agrupava por slot, então uma pesquisa em que a rodada 1 usou letra e a rodada 2 usou id contava
pesquisa e execução em dobro; truncamento era interruptor em vez de contagem, e o incidente
pesava 1,0 onde o `qualidade.py` pesa 0,5. O índice do Perplexity saía 70 no painel e 77,3 no
script. Agora os dois batem: 89, 80, 77 e 72 contra 89,3, 80,4, 77,3 e 72,5.

**4. "O Gemini é o único com URL inventada" é falso.** São oito na série, sete dele e uma do
Perplexity (`core.ac.uk/download/213902926.pdf`, HTTP 404, na rodada 2 da história). A frase
estava no README público, no ESTADO.md e no CHANGELOG. Corrigida nos três para "concentra as
URLs inventadas, sete das oito".

**5. A densidade dependia da digitação do termo.** `_raizes` emite a forma e a raiz, e ambas
casavam a mesma ocorrência, dobrando a contagem: a mesma página passava com `--termos mills` e
reprovava com `--termos mill`. Agora conta-se posição única no texto, e não ocorrência por raiz.

**6. O motivo gravado mentia.** Quando o corte era por densidade, a mensagem dizia que a página
não menciona nenhum termo, e ela menciona uma vez. Texto próprio agora, porque esse motivo viaja
para o relatório e para o prompt da rodada 2.

**7. Falha de rede virava item de revalidação.** Com `inconclusiva` de volta na lista, um 403 de
editora acadêmica entraria na rodada 2 como se fosse fonte duvidosa: 157 itens contra 13 reais
nas cinco pesquisas com termos registrados. Agora o registro carrega `origem: rede` e fica fora
da revalidação, sem deixar de aparecer no relatório. O verificador de tema também ganhou o motivo
com código HTTP, que antes era só o nome da exceção.

**8. Muro de acesso em português não era reconhecido.** A comparação era acentuada e a lista não
tinha os avisos do portal do governo. A FAQ da ANEEL sobre minigeração distribuída, que responde
"Conteúdo Restrito" com 3.206 caracteres, era acusada de não tratar do tema numa pesquisa sobre
minigeração distribuída. Agora a comparação é sem acento, o limiar subiu para 3.500 e a lista
inclui os avisos em português.

**9. Trecho recuperado por marcador vinha de citação em lote.** Em 22 de 24 resoluções a primeira
ocorrência estava num lote como `[1][2][4][8][9][10]`, e a janela fixa de 700 caracteres num
parágrafo de uma linha só produzia a mesma frase deslocada de um caractere. Agora se prefere o
marcador isolado, o recorte é por frase, e quando só existe lote o trecho vai marcado:
`[atenção: citação em lote de 12 fontes neste trecho]`.

Mais dois menores: termo com menos de quatro letras era descartado em silêncio e agora é logado,
e a docstring de `_faixa_entrada` mantinha os números falsificados de 278 mil e fator 2,6.

### O ACHADO QUE NÃO PROCEDE

O auditor afirma que o corte por cabeçalho deixava sem trecho 26 URLs escritas no corpo, e cita
como caso as sete URLs inventadas do slot C em `uma pesquisa de regulação`, "19 caracteres depois do
corte". Fui conferir uma a uma: as sete estão em linhas que contêm apenas o endereço, dentro da
lista de fontes. Sem o corte elas continuam sem trecho, e devem continuar — nunca foram usadas ao
lado de afirmação nenhuma. O conserto do corte está certo pelos outros motivos; o ganho alegado
para esse caso não existe. Depois do conserto, o número de falhas duras com trecho localizado
segue idêntico nessas linhas.

### O NÚMERO 46 CONTRA 84

Os dois estão certos e medem coisas diferentes. São 84 ocorrências de `fora do tema` no histórico
e 79 URLs distintas. Meu recorte de 46 era o subconjunto cujas pesquisas têm `--termos` gravado em
`r1.log`, que são três pastas — sem os termos originais não dá para reprocessar honestamente. O
auditor recuperou termos de outras pastas por outro caminho e chegou a 80. A frase da entrada
anterior está correta no que declara, e agora fica registrado o universo completo.

### RESULTADOS

| Caso | Antes | Agora |
|---|---|---|
| Wikipédia Instagram, Bitcoin e insulina, termos de moinho | passavam | fora do tema |
| PNUD, FMI e Domesday | passam | passam |
| econstor com desafio Anubis | fora do tema | inconclusiva |
| FAQ da ANEEL com Conteúdo Restrito | fora do tema | inconclusiva |
| PDF do MPRA | HTTP 416 | 200, 558 KB lidos |
| Painel contra medidor, índice do Perplexity | 70 contra 77,3 | 77 contra 77,3 |

### LIÇÕES

Consertar a cópia e esquecer o original é o erro que mais se repete aqui. Foi assim com o corte
por cabeçalho, que arrumei no caminho novo e deixei no antigo, e tinha sido assim na véspera com
o quarto consumidor da régua. A pergunta que faltava nas duas vezes é a mesma: quem mais faz isto?

Auditor adversarial também erra, e o jeito de saber é conferir o caso concreto que ele cita. As
sete URLs do regulação de 04/08 estavam onde ele disse e não eram o que ele disse. Aceitar o relatório
inteiro por vir bem argumentado teria produzido uma correção sem efeito e uma lição falsa no
changelog.

Número que sustenta decisão precisa vir com o recorte declarado. "46 URLs" e "84 URLs" descrevem
o mesmo acervo com critérios diferentes, e sem o critério ao lado o número vira munição para
qualquer lado.

---

## [2026-08-13 15:15] — Terceira auditoria: o gate de lista era regressão líquida

### OBJETIVO

Terceira rodada do ciclo adversarial. O auditor atacou as nove correções das 14:47 e deu veredito
negativo: segundo ele, o conserto reintroduziu por outra porta a mesma regressão que a auditoria
anterior tinha derrubado. Estava certo no essencial.

### O QUE ELE PEGOU

**1. `_e_linha_de_lista` derrubava trecho legítimo.** Duas causas. A regra do marcador de lista
tratava qualquer bullet abaixo de 400 caracteres como item de índice, e bullet com 290 caracteres
de análise é afirmação — uma das três URLs fabricadas do Gemini que a entrada anterior comemorou
ter recuperado voltou a ficar sem trecho. E o padrão `URL: <endereço>` na linha seguinte ao
veredito, comum na rodada 2, tinha a linha descartada sem que ninguém olhasse a prosa logo acima.

Medido sobre as 161 URLs problemáticas dos sete JSONs: o corte antigo dava 78 trechos e 40 das 58
falhas duras; o gate novo tinha caído para 64 e 32.

**2. As duas instruções de `--termos` no SKILL.md se anulavam.** Uma manda evitar palavra
genérica, a outra, acrescentada por mim na véspera, manda incluir o termo genérico do domínio.
Com `water` e `power` na lista, a Wikipédia do Instagram, do Bitcoin e da insulina voltam a passar
numa pesquisa sobre moinhos. A peneira reabria pela instrução de operação, e não pelo código.

**3. A densidade ainda dependia da digitação.** Contar posição inicial não bastava: `water mill`
gera as raízes `water`, `mill` e `water mill`, que casam a mesma passagem em posições diferentes,
então uma menção única virava duas.

**4. `origem: rede` alcançava falha dura.** A marca era gravada sem guarda de estado, então uma
URL já `suspeita` que tomasse 403 na conferência de tema saía da revalidação. É o caso que mais
precisa da rodada 2, porque ninguém conseguiu ler a página.

**5. Falso positivo de muro em página real.** `quantica.scorasacademy.com.br` lista "Cloudflare"
entre competências de nuvem, tem 2.399 caracteres e virava inconclusiva. Palavra de tela de
bloqueio é também vocabulário de página de tecnologia.

**6. O conserto da janela deslizante só mudou de ponta.** Consertei o início pelo recorte de
frase e deixei `fim = pos + 300`, então três trechos saíram byte a byte idênticos.

Mais: o piso de custo no ESTADO.md era US$ 1,59 e o real é US$ 1,52; o SKILL.md ainda descrevia
casamento "por prefixo", que deixou de existir; a marca de citação em lote entrava colada no
trecho que vai para o motor na rodada 2; a lista de citações não passava pelo mapa de resolução
de redirecionamento, o que matava o caminho por marcador justamente no Gemini; e o painel usava
o rótulo "Fontes" para dois números diferentes na mesma página.

### O QUE FOI FEITO

`_e_linha_de_lista` passou a decidir só por quanto texto sobra fora da URL, sem olhar marcador de
lista. `_prosa_acima` recupera a afirmação escrita antes de uma linha que só exibe endereço, e
para de subir quando encontra cabeçalho de lista de fontes — é o que mantém as sete URLs
inventadas do slot C de 04/08 sem trecho, como devem ficar.

A densidade conta intervalos mesclados, então sobreposição de raízes vale uma passagem. A marca
de origem só entra em registro ainda `ok`. Os sinais de muro foram separados em inequívocos, que
concluem sozinhos, e ambíguos como "cloudflare" e "consent", que precisam de dois. O fim do
trecho passou a ser o fim da frase, com teto de 400 caracteres, e a janela do caminho por
marcador caiu para 350.

A contagem de citações em lote virou campo próprio, `citacoes_no_trecho`, e o aviso aparece no
markdown ao lado do item, fora do texto que o motor recebe como afirmação a verificar. As
citações passam pelo mapa de `resolver_redirects`. Documento sem HTML não é mais baixado para ser
descartado: o tipo é lido no cabeçalho antes do corpo. E o SKILL.md ganhou a regra que faltava
sobre `--termos`, agora com o critério explícito — o termo que a fonte esperada usaria e que uma
página de outro assunto não usaria, com `energy` servindo e `power` e `water` não.

### RESULTADOS

| Medida | Corte antigo | Gate de 14:47 | Agora |
|---|---|---|---|
| URLs problemáticas com trecho | 78 | 64 | 105 |
| Falhas duras com trecho (de 58) | 40 | 32 | 45 |
| Sete URLs inventadas do slot C | sem trecho | sem trecho | sem trecho |

Peneira e URLs boas seguem corretas nos seis casos de teste. A FAQ da ANEEL continua reconhecida
como muro; a página da Scoras, com "Cloudflare" no texto, deixou de ser. O PDF do MPRA responde
200. Painel e medidor continuam batendo.

### LIÇÕES

Gate novo precisa ser medido contra o que ele substitui, e não contra zero. O corte por cabeçalho
era ruim e eu troquei por algo pior sem comparar: bastava rodar os dois sobre o mesmo corpus, que
é o que o auditor fez em cinco minutos.

Instrução de operação é parte do sistema. A peneira reabriu porque o SKILL.md mandava incluir
termo genérico, e nenhum teste de código pegaria isso — o teste teria que usar os termos que a
instrução manda usar.

Aviso em português dentro de campo de dado vira entrada de modelo. A marca de lote colada no
trecho ia junto para a rodada 2, onde o motor a leria como parte da afirmação a verificar.

---

## [2026-08-13 15:36] — Quarta auditoria: o número que publiquei estava inflado pelo meu próprio teste

### CORREÇÃO DA ENTRADA ANTERIOR

A tabela da entrada das 15:15 diz que a recuperação de trecho passou de 78 para 105, e as falhas
duras com trecho de 40 para 45. **Os dois números estão errados**, e o erro é de método, não de
código.

Meu script de medição lia `r.get("citacoes") or r.get("urls")`. O campo `citacoes` só passou a
ser gravado ontem, então nenhuma das sete pesquisas do acervo tem esse campo, e toda a medição
caiu no segundo termo — que é a lista deduplicada de `extrair_urls`, exatamente a que a docstring
de `urls_das_citacoes` descreve como imprestável para resolver marcador, porque a repetição
removida desloca todos os índices seguintes. Os 22 trechos que faziam 83 virar 105 vinham todos
daí.

Números honestos, medidos com o que os arquivos de fato contêm:

| Medida | Corte antigo (antes de tudo) | Hoje |
|---|---|---|
| URLs problemáticas com trecho | 78 | 77 |
| Falhas duras com trecho (de 58) | 40 | 35 |
| Trechos vindos de casamento por prefixo de URL | 12 | 0 |

A comparação direta não vale, e é por isso que a terceira coluna existe. O método antigo achava
a URL com `texto.find`, que casa por prefixo: `https://loja.exemplo/` encontrava a ocorrência de
`https://loja.exemplo/categoria/subcategoria` e herdava o trecho dela. Doze casos no
acervo, seis deles com atribuição francamente errada — a home citada como se fosse fonte ficava
coberta pela prova da página específica, e a rodada 2 recebia uma afirmação que outra URL já
sustentava. O número menor de hoje é o número sem essas doze heranças.

O ganho real do fallback novo, isolado: a busca literal sozinha recupera 58 trechos e 27 falhas
duras; com `_prosa_acima`, 77 e 35.

### O QUE MAIS A AUDITORIA PEGOU

**A janela deslizante não tinha sido consertada.** O recorte de frase procurava `". "`, e no
estilo acadêmico o marcador cola no ponto — `...second century CE.[1][2][4]` não tem espaço
depois do ponto, então o recuo ia para a frase anterior. Seis URLs distintas recebiam o mesmo
parágrafo de resumo, três delas byte a byte idênticas. Agora existe `FIM_DE_FRASE`, que reconhece
pontuação seguida de espaço ou de colchete, e os trechos do mesmo caso caíram de 1.232 para 160 e
304 caracteres, com dois textos distintos em vez de fatias deslizantes do mesmo.

**`_e_linha_de_lista` testava o comprimento antes de remover a URL**, então endereço nu de 477
caracteres — os da ANEEL e os links de redirecionamento do Gemini — passava por afirmação.
Invertida a ordem.

**A guarda de cabeçalho de `_prosa_acima` dependia de literais estreitos.** Com "## Fontes" ou
"Bibliografia" no lugar de "FONTES CONSULTADAS", as sete URLs inventadas do slot C ganhariam um
parágrafo sobre condomínios em São Paulo. A lista de cabeçalhos foi ampliada.

**`qualidade.py` imprimia `? fonte(s) com falha dura sem trecho`** em nove dos 22 erros, porque o
campo não existe nos JSONs anteriores a ontem. Agora diz que o número não foi registrado.

### O QUE FICA COMO LIMITAÇÃO ESTRUTURAL

O detector de muro só olha página abaixo de 3.500 caracteres. Quando o corpo era cortado em 4.000,
isso cobria quase tudo que se lia; hoje se lê até 1,5 MB, e tela de bloqueio acima de 3.500
caracteres passa direto para a conferência de termos. O auditor não achou contraexemplo vivo, e o
argumento é estrutural — fica registrado como risco conhecido, sem conserto especulativo.

E o mapeamento `[N] → N-ésima citação` continua sem exercício com dado real, agora com a razão
escrita: as respostas antigas não guardam `annotations`. A primeira pesquisa nova é que vai dizer
se ele funciona.

### LIÇÕES

O fallback silencioso no script de medição foi o erro mais caro do dia. `campo_novo or
campo_antigo` parece defensivo e é o contrário: mede o antigo e reporta como se fosse o novo, sem
nada no resultado denunciando a troca. Em código de medição, campo ausente deve interromper, não
substituir.

Publiquei número de melhoria que não existia, e o publiquei no mesmo documento em que critico
número sem recorte declarado. A regra que fica: benchmark de conserto se roda contra o dado que
existe, e quando o dado não existe, o resultado é "não medido" — nunca um número obtido por
aproximação conveniente.

Correção que reduz o número pode ser a correção certa. Sair de 78 para 77, e de 40 para 35, é
melhora: doze atribuições herdadas saíram, e nenhuma delas dizia a verdade sobre o que a fonte
sustentava.

---

## [2026-08-13 17:31] — v2: três skills, verificação separada da coleta, e o que a coleta não media

### OBJETIVO

Executar o `DESENHO_v2.md`, aprovado depois da conversa que redefiniu o produto. A frase que
organiza tudo: coletar é commodity, e o valor está em dizer se o que veio presta. O sistema
verificava procedência e não verificava verdade.

### CAMADA ESTRUTURAL — três partes com fronteira em disco

`buscar.py` deixou de verificar. Ele coleta, grava e sai. `verificacao.py` recebeu as 680 linhas
de régua que viviam dentro dele, e `verificar.py` é o comando que roda sobre uma pasta já
coletada — sem custo, quantas vezes se quiser, inclusive em pesquisa antiga.

Esse é o ponto da separação e não é estético. Nos dois dias anteriores, cada ajuste de régua
exigia scripts avulsos para medir efeito sobre o acervo, porque a única forma de rodar a
verificação era comprando uma pesquisa nova.

Três skills, com os scripts num lugar só: `/pesquisa` (clarificação, coleta, rodada 2, redação),
`/verificar` (o miolo) e `/qualidade` (medição, fora do fluxo). Symlinks em `~/.claude/skills/`.

Compatibilidade: `problemas_gravados()` lê o veredito do arquivo separado quando ele existe e do
campo embutido quando não existe. As sete pesquisas do acervo continuam medindo igual — conferido,
os quatro índices não mudaram um dígito.

### CAPACIDADES NOVAS

**Coerência interna.** `divergencias_numericas()` extrai medidas com unidade de cada resposta,
ancora cada uma no vocabulário raro ao redor e compara entre motores. Detectou, no acervo: 35%
contra 8,8% sobre o mesmo efeito, e 46% contra 100% de tonelagem a vapor. É o sinal de erro que
não exige ser especialista, e é o que teria pego os três números derrubados em 12/08.
`unidades_trocadas()` cobre o caso irmão, percentual contra valor absoluto.

Dois filtros que nasceram do próprio teste: âncora precisa ser rara no conjunto, senão "pessoa" e
"probabilidade" casam medidas sem relação; e série histórica com anos diferentes não é
divergência. Com eles, uma pesquisa de regulação saiu de 43 pares para 8.

**Independência por origem.** `origens()` conta domínios distintos, compartilhados e exclusivos
por motor. Consenso deixa de ser quantos motores disseram e passa a ser quantas origens
sustentam. Medido no acervo: sobreposição entre 0,11 e 0,27, ou seja, a maior parte do material
vem de origens que só um motor alcançou.

**Cinco gatilhos de decisão.** Afirmação negativa, consenso de origem única, incoerência,
divergência de escola e fonte atrás de muro. Saem em `r1_decisoes.md`, no máximo dez itens, cada
um com uma pergunta fechada.

**Criticidade como eixo separado de profundidade.** Correção do Danilo: os modos nasceram por
custo, não por confiabilidade. Agora são duas perguntas na clarificação. Profundidade governa
custo; criticidade governa quantas origens o consenso exige, se os gatilhos param o fluxo e se a
fonte primária é obrigatória. Corroborar um dado é rápido e crítico; levantar exemplos é profundo
e pouco crítico.

**Parecer independente.** `references/prompt-parecer.md`, para subagente com contexto isolado que
lê o material bruto sem ver a análise de quem coletou. Roda sempre, nas duas rodadas, salvo
pedido de pular. É a formalização do que quatro auditorias adversariais provaram em dois dias.

**Memória de afirmações.** `memoria.py`, JSONL de uma linha por fato, consultado por busca antes
de disparar pesquisa nova, nunca lido inteiro — o erro do arquivo de conexões do brain v2, que
chegou a duas mil linhas e consumia o contexto numa consulta. Porta estreita: só entra o que teve
duas origens independentes ou validação humana. Campos de validade: `vale_ate` e `invalida_se`.

Primeiro registro gravado: o art. 23, § 6º da REN ANEEL 1.000/2021, que custou uma pesquisa
inteira em 04/08 e não custará outra.

**Régua por tema.** `qualidade.py` registra a área de cada pesquisa e reporta por tema a partir de
três pesquisas naquele tema. Antes disso, seria trocar uma régua imprecisa por várias.

### O QUE NÃO ENTROU

Agente chefe de equipe, agente redator separado e agente pesquisador em Claude. O ganho de dividir
em agentes é isolar contexto para quebrar viés, e isso se resolve com um papel novo — o
verificador independente. Os outros acrescentariam passo sem acrescentar independência.

### LIÇÕES

A fronteira certa entre partes de um sistema é o artefato em disco, não a etapa mental. Enquanto
coleta e verificação compartilhavam execução, melhorar a régua custava dinheiro; agora custa um
comando.

Capacidade que mede verdade é diferente de capacidade que mede procedência, e a segunda estava
madura enquanto a primeira não existia. Um relatório com 100% das URLs válidas pode estar errado
do começo ao fim, e nada no sistema anterior notaria.

Filtro de ruído se calibra contra o acervo, não contra a intuição. Os dois cortes que salvaram a
detecção de coerência — âncora rara e ano incompatível — só apareceram rodando sobre as sete
pesquisas reais.

---

## [TEMPLATE PARA PRÓXIMAS ENTRADAS]

## [YYYY-MM-DD] — Título da Sessão

### OBJETIVO
O que estava sendo construído.

### PROBLEMA
Descrição do erro. Sintomas, quando acontece, mensagem de erro.

### ANÁLISE / ROOT CAUSE
Como foi investigado. O que causou.

### SOLUÇÃO
Arquivos modificados, código alterado, comandos executados.

### RESULTADOS
Evidências de que funcionou. Testes executados.

### LIÇÕES APRENDIDAS
O que funcionou bem, o que evitar, descobertas úteis.
