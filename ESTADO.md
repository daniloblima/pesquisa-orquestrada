# ESTADO — leia isto primeiro

Atualizado: 2026-08-05 11:26

Documento de retomada. O `CHANGELOG.md` tem 1.100 linhas e guarda o detalhe de cada problema; este arquivo dá o mapa e diz onde procurar. Leia inteiro antes de mexer em qualquer coisa, e só abra o CHANGELOG quando precisar do porquê de uma decisão específica.

## O que é

Skill do Claude Code que faz pesquisa com validação cruzada entre motores de busca independentes, via OpenRouter. Acionada por `/pesquisa <tema>`.

Nasceu como app de terminal em Python (PRD de março/2026, nunca implementado) e virou skill em 03/08/2026. O Claude Code orquestra: clarificação, análise de consenso, decisão do que revalidar e redação final. O OpenRouter paga apenas as chamadas de busca.

Repositório público: github.com/daniloblima/pesquisa-orquestrada

## Onde as coisas vivem

```
~/Experimentos/pesquisa-orquestrada/
├── ESTADO.md                     este arquivo
├── CHANGELOG.md                  todos os problemas, com causa e correção
├── README.md                     vitrine pública
├── PRD.md, tasks.md, rules.md    planejamento interno, fora do repositório
├── outputs/                      pesquisas feitas, fora do repositório
│   ├── dashboard.html            painel, abre com duplo clique
│   └── AAAA-MM-DD_tema/          r1.json, r1.log, r1_<id>.md, r2.*, meta.json, relatorio.md
└── skill/                        ← a skill inteira
    ├── SKILL.md                  fluxo e regras duras
    ├── config.json               motores, modos, preços, limiares
    ├── catalogo-motores.json     catálogo do OpenRouter classificado
    ├── qualidade-motores.json    notas medidas, série por data, log de erros — LOCAL, fora do repositório
    ├── references/               prompt-mestre.md, formato-relatorio.md
    └── scripts/                  buscar.py, dashboard.py, motores.py, qualidade.py
```

`~/.claude/skills/pesquisa` é symlink para `skill/`. Uma fonte de verdade só, versionada.

Chave do OpenRouter em `~/.claude/.env`, permissão 600, fora de qualquer repositório. Nunca dentro do projeto.

## Os quatro scripts

> Reorganizado em 13/08/2026: são três skills, e os scripts moram todos em `skill/scripts/`.
> `/pesquisa` coleta e redige, `/verificar` confere o material coletado e `/qualidade` mede os
> motores. Ver `DESENHO_v2.md` e a entrada de 13/08 17:31 no CHANGELOG.

| Script | O que faz | Gasta crédito |
|---|---|---|
| `buscar.py` | Chama os motores e grava a resposta. Só isso | **sim, é o único** |
| `verificar.py` | Confere fontes, coerência e independência sobre uma pasta já coletada | não |
| `verificacao.py` | A régua em si, importada por quem precisa dela | não |
| `memoria.py` | Afirmações já estabelecidas, uma linha por fato | não |
| `qualidade.py` | Mede precisão, confirmação e confiabilidade por motor; deriva o papel de cada um | não |
| `dashboard.py` | Gera o painel HTML de todas as pesquisas | não |
| `motores.py` | Catálogo do OpenRouter, classifica só o diferencial a cada consulta | não |
| `regressao.py` | Roda a régua atual e a de um commit sobre as pesquisas já feitas, e mostra só as diferenças | não |

> Desde 21/08/2026 a verificação grava `r{N}_observacao.json` ao lado do veredito: o que a
> web respondeu sobre cada URL, na data em que foi perguntado. É o que permite recalcular a
> régua depois sem voltar à rede. Ver "Quando a régua muda" abaixo.

Só biblioteca padrão do Python. Nada a instalar.

## Decisões que não se re-litigam

**O Claude Code orquestra, o OpenRouter só busca.** A alternativa era um orquestrador via API, como no PRD original. A clarificação vira conversa de verdade, a consolidação roda em modelo melhor e a lógica fica em markdown editável.

**Um índice de busca por família, e `engine` sempre explícito.** Se dois motores usam o mesmo mecanismo de busca, leem as mesmas páginas e a concordância entre eles não valida nada. O plugin sem `engine` declarado é ignorado em silêncio pelos modelos Google.

**Motores identificados por id, em lista aberta, sem teto.** Acrescentar motor é acrescentar item em `motores` no `config.json`. Só entra quem tem `padrao: true` quando `--motores` é omitido — é o que impede motor caro de rodar por esquecimento.

**Nenhum julgamento de modelo escrito em arquivo.** O `config.json` guarda limiares; a nota sai dos dados, em `qualidade.py`. Motor que melhora sobe de faixa sozinho. Escrever "este modelo é ruim" em configuração congela uma medição de um dia como regra permanente.

**Fonte reprovada manda a afirmação para revalidação, nunca para o lixo.** Descarte silencioso perde informação verdadeira citada com fonte errada.

**Quem citou não valida a própria citação**, e o motor nunca é avisado de que a fonte caiu — senão concorda com a reprovação em vez de pesquisar.

## Modos de falha já descobertos — não reinvestigar

Detalhe completo no CHANGELOG, com data e teste.

1. **Busca que falha em silêncio.** Plugin sem `engine` explícito: modelos Google respondem de memória, HTTP 200, sem aviso. Sinal de que buscou: volume de tokens de entrada e presença de URLs.
2. **URL que existe na forma e não no mundo.** É o modo grave, porque parece verificado. Quatro camadas hoje: existe, forma de fonte, confissão do modelo no texto, e se a página trata do tema. O arquivo da internet separa página removida de URL inventada.
3. **Consenso sobre ausência não é prova de ausência.** Três motores afirmaram que não havia dispositivo impondo teto de 75 kW; o art. 23, § 6º da REN ANEEL 1.000/2021 diz exatamente isso. Nenhum achou. Regra dura 8 e passo 5b existem por causa disso.
4. **Estimativa com parâmetro único.** Motores cobram de formas incompatíveis: um recebe a busca no prompt e chega a 80 mil tokens de entrada; outro busca do lado do provedor e cobra por consulta. `tokens_input_busca` é por modelo, medido.
5. **Truncamento.** Relatório cortado perde a seção de fontes, que fica no fim. Tetos de tokens já subidos duas vezes.
6. **Falha entrando como sucesso.** `finish_reason=error` com `erro` nulo. Hoje marca o agente como falho.
7. **Citação só no rodapé.** Motor que lista URLs apenas na seção final impede recuperar a afirmação que cada fonte sustentava, e a revalidação não alcança nada. O prompt mestre exige URL no próprio parágrafo; `reprovadas_sem_rastro` marca quando falha assim mesmo.

## Números atuais

Sete pesquisas feitas até 12/08/2026, contando as duas rodadas de cada uma. Custo por pesquisa
entre US$ 1,52 e US$ 3,48 até 05/08; as três de 12/08 custaram entre US$ 1,86 e US$ 3,08.

Atenção ao custo da composição padrão, que mudou duas vezes em 12/08. Saiu o Gemini, entrou o
Perplexity, e o Grok ficou: o típico por rodada foi de US$ 0,86 para US$ 1,80, ou seja, perto de
US$ 3,60 por pesquisa de duas rodadas. Confirme a estimativa antes de disparar, sempre.

Notas medidas em 05/08/2026, calculadas pelos limiares do `config.json`:

| Motor | Pesq. | URLs | Precisão | Índice | Papel |
|---|---|---|---|---|---|
| Grok 4.20 multi-agent | 2 | 52 | 90% | 86,2 | confirmação |
| GPT-5.6 Terra | 3 | 120 | 90% | 76,1 | confirmação com ressalva |
| Perplexity Deep Research | 2 | 74 | 86% | 72,1 | confirmação com ressalva |
| Gemini 3.1 Pro | 3 | 57 | 77% | 70,4 | confirmação com ressalva |

O Gemini concentra as URLs classificadas como inventadas, sete das oito da série — a oitava é do Perplexity. Isso bate com a literatura: o DeepResearch Bench mede que ele lidera em citações efetivas e fica atrás em citation accuracy. O padrão é geral — quem cita mais, cita pior, por diluição de atenção na síntese.

**Não decida sobre motor a partir desta tabela.** Rode `python3 skill/scripts/qualidade.py` e use o número do dia.

> **A tabela acima está superada.** Ela foi medida com a régua antiga, que somava falso positivo
> de tema e falha de rede do verificador na conta de erro de citação. Régua corrigida em
> 12/08/2026 às 19:05, e a série anterior a essa data não se compara com a posterior. Números
> atuais, sete pesquisas e 22 medições:
>
> | Motor | URLs | Falha dura | Sinal fraco | Precisão | Índice | Papel |
> |---|---|---|---|---|---|---|
> | Grok 4.20 Multi-Agent | 501 | 12 | 31 | 98% | 89,3 | confirmação |
> | GPT-5.6 Terra | 360 | 14 | 29 | 96% | 80,4 | confirmação |
> | Perplexity Deep Research | 151 | 7 | 21 | 95% | 77,3 | confirmação com ressalva |
> | Gemini 3.1 Pro | 110 | 25 | 22 | 77% | 72,5 | confirmação com ressalva |
>
> O Perplexity fica em atenção pela confiabilidade de 44%, que é truncamento e não citação. O
> Gemini continua o pior e concentra a invenção de URL, sete das oito da série, e por isso segue
> fora do padrão. O Grok voltou ao padrão em 12/08. Ver `CHANGELOG.md`, entrada de 19:05.

O `qualidade-motores.json` não vai para o repositório: é dado de uso, e o histórico dele cita os temas das pesquisas feitas. Quem instala a skill começa a própria série do zero. O README publica só a ordem de grandeza, sem identificar pesquisa.

## Pendências reais

- **`BACKLOG.md` é o documento operacional dos problemas conhecidos**, aberto em 12/08/2026 e
  revisado no mesmo dia às 16:35 contra o código e as sete pesquisas. Dez itens com evidência,
  ordem de correção sugerida e o veredito de cada um. Ler antes de mexer no código de verificação.
  A apuração completa está no `CHANGELOG.md`, entrada de 12/08 16:35.
- **Verificar se a exigência de citação inline funciona.** A correção foi gravada em 04/08 e ainda não foi exercitada: a pesquisa de 05/08 rodou em sessão aberta antes da mudança e não a recebeu. É a hipótese mais importante em aberto.
- **Teste em domínio sem fonte primária.** A skill só viu temas com resposta certa e fonte oficial, de regulação e mercado. Em tema de gosto ou comportamento o risco muda: preferência apresentada como regra, convenção de nicho apresentada como consenso. Há instrução no passo 5b, ainda não exercitada.
- **Verificação de que a fonte sustenta a afirmação**, e não apenas que existe e trata do tema. Desenhada, não implementada, esperando um caso concreto.
- **Nenhum caso com resposta conhecida.** Se um relatório sair inteiro errado, nada acusa.
- **Substituir os indicadores de fontes coletadas e tempo total no painel**, que perderam utilidade, por taxa de confirmação e taxa de URL reprovada.
- **Modo `profunda` nunca exercitado.**

## Como retomar

1. Ler `HANDOFF_2026-08-13.md` primeiro, que conta os dois dias em que a skill foi
   reorganizada em três, depois este arquivo, e o `BACKLOG.md` se o trabalho for de correção.
2. `python3 skill/scripts/qualidade.py` — estado atual dos motores, variação desde a última medição e erros recentes.
3. Abrir `outputs/dashboard.html` se quiser o quadro visual.
4. `git log --oneline` para o que mudou por último.
5. CHANGELOG só quando precisar do porquê de uma decisão específica. Está em ordem cronológica, do mais antigo ao mais recente.

**Uma advertência que custou uma pesquisa:** edição em arquivo de skill não alcança sessão já aberta. Correção vale a partir da próxima sessão, não da próxima pesquisa.

## Duas notas por motor, e a divergência entre elas é o sinal

`ÍNDICE` é a série inteira, cada medição valendo o mesmo. `RECENTE` é a mesma série com as
medições antigas pesando menos — metade a cada `meia_vida_dias` do `config.json`, hoje 30.

Nenhuma das duas manda sozinha, e é esse o ponto. Só a última rodada é volátil demais para
decidir composição de motores. O acumulado puro é o oposto: carrega defeito de passado
longínquo como se fosse de agora e penaliza o motor que melhorou. O decaimento dá inércia
sem congelar, e por ser contínuo não tem o degrau de uma janela fixa, onde a medição de
ontem vale tudo e a de anteontem vale zero.

**Onde as duas divergem é onde o motor mudou.** Verificado em 21/08/2026 com série
sintética: dois motores com índice acumulado quase idêntico, 84,6 e 85,6, um melhorando e o
outro piorando ao longo de quatro meses. A nota recente os separa em 93,4 e 74,5. A média
longa sozinha os trataria como equivalentes.

A massa mínima usa a contagem **bruta** de URLs, não a ponderada. Com decaimento, um motor
de série longa cairia abaixo do mínimo só por o tempo ter passado, e perderia a
classificação sem ter feito nada.

Na série atual a diferença entre as duas é de 0,1 a 0,4 ponto, porque ela tem 18 dias. O
mecanismo é para quando houver massa.

## A nota viaja, o histórico fica

Dois arquivos, e a diferença entre eles é o que pode ser visto por terceiros.

| Arquivo | Contém | Vai ao repositório? |
|---|---|---|
| `skill/notas-motores.json` | Agregado por motor: precisão, confirmação, confiabilidade, índice, papel, custo médio por rodada | **Sim.** Sem tema, sem URL, sem nome de pesquisa |
| `skill/qualidade-motores.json` | O mesmo mais `serie_notas` e `historico`, com uma linha por pesquisa | Não. O histórico cita o tema de cada pesquisa |

A nota publicada é **semente, não verdade**. Quem instala parte dela e, assim que a série
local tiver massa para um motor, passa a medir o próprio — os usos são outros, e o que cada
um pesa é outro. As duas divergem de propósito, e o resumo marca `[nota herdada]` no que
ainda não foi medido localmente.

**A publicação nunca apaga o que não pode substituir.** Só motor com amostra suficiente
local sobrescreve a nota herdada; o resto é preservado. Sem essa guarda, a primeira execução
do `qualidade.py` numa instalação nova publicava nota vazia por cima da semente e apagava a
curadoria antes de ela ser lida — bug encontrado e corrigido em 21/08/2026.

## Quando a régua muda, a série precisa ser recalculada

```bash
python3 skill/scripts/verificar.py <pasta> --todas --recalcular
```

Aplica a régua de hoje sobre a observação já colhida, **sem tocar a rede**. Na pesquisa de
ASIC: 51 segundos com rede contra 0,097 segundo no recálculo, com veredito idêntico.

Isso existe porque a nota dos motores é recalculada do zero a cada execução do
`qualidade.py`, lendo os arquivos de verificação em disco. Quando a régua muda e a série
não é recalculada, a nota passa a somar medições feitas com critérios diferentes — foi o
que aconteceu em 12/08 e sustentou uma decisão de composição de motores com número errado.

**E por que não simplesmente rodar a verificação de novo?** Porque ela iria à rede, e a rede
de hoje não é a de agosto. Uma página que estava no ar na data da pesquisa e saiu do ar
depois viraria erro de citação de um motor que não errou nada. O recálculo julga a
observação daquele dia.

O que separa os dois: o que é derivável do bruto é **recomputado** a cada recálculo — a
forma da URL, a confissão do modelo no texto ao lado, a régua de tema. O que veio da web é
**lido** da observação. Só uma coisa continua exigindo rede, e está escrita no arquivo:
mudar a **lista de termos** do tema, porque `termos_achados` só se relê contra os termos que
foram perguntados.

**Vale a partir de 21/08/2026.** As oito pesquisas anteriores não têm observação gravada, e
`--recalcular` avisa e não faz nada nelas. Decidido assim de propósito: colher observação
retroativa hoje produziria dado de hoje carimbado com data de agosto.

## Antes de commitar mudança na régua

```bash
python3 skill/scripts/regressao.py --detalhe
```

Roda a verificação sobre uma cópia de cada pesquisa do histórico, com o código de trabalho
e com o do último commit, e mostra só o que mudou. Meio segundo, sem crédito, sem tocar o
material original.

**Saída idêntica não é o objetivo.** Quem mexe na régua quer que ela mude. O que a rede
pega é a mudança que você não pretendia: em 21/08/2026, rebaixar "domínio raiz" mexeu em 21
URLs de sete pesquisas, e as 21 tinham o mesmo motivo. Se uma tivesse outro, era regressão.

Isso existe porque a régua não tem teste, e a evidência dela é histórica — o material de
prova é caro, já foi comprado e está em `outputs/`.
