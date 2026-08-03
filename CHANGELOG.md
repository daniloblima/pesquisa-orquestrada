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
