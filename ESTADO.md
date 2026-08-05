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

| Script | O que faz | Gasta crédito |
|---|---|---|
| `buscar.py` | Chama os motores, verifica as URLs, extrai afirmações a revalidar | **sim, é o único** |
| `qualidade.py` | Mede precisão, confirmação e confiabilidade por motor; deriva o papel de cada um | não |
| `dashboard.py` | Gera o painel HTML de todas as pesquisas | não |
| `motores.py` | Catálogo do OpenRouter, classifica só o diferencial a cada consulta | não |

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

Três pesquisas feitas. Custo por pesquisa entre US$ 1,59 e US$ 3,48, conforme o número de motores.

Notas medidas em 05/08/2026, calculadas pelos limiares do `config.json`:

| Motor | Pesq. | URLs | Precisão | Índice | Papel |
|---|---|---|---|---|---|
| Grok 4.20 multi-agent | 2 | 52 | 90% | 86,2 | confirmação |
| GPT-5.6 Terra | 3 | 120 | 90% | 76,1 | confirmação com ressalva |
| Perplexity Deep Research | 2 | 74 | 86% | 72,1 | confirmação com ressalva |
| Gemini 3.1 Pro | 3 | 57 | 77% | 70,4 | confirmação com ressalva |

O Gemini é o único com URLs classificadas como inventadas, sete até agora. Isso bate com a literatura: o DeepResearch Bench mede que ele lidera em citações efetivas e fica atrás em citation accuracy. O padrão é geral — quem cita mais, cita pior, por diluição de atenção na síntese.

**Não decida sobre motor a partir desta tabela.** Rode `python3 skill/scripts/qualidade.py` e use o número do dia.

O `qualidade-motores.json` não vai para o repositório: é dado de uso, e o histórico dele cita os temas das pesquisas feitas. Quem instala a skill começa a própria série do zero. O README publica só a ordem de grandeza, sem identificar pesquisa.

## Pendências reais

- **Verificar se a exigência de citação inline funciona.** A correção foi gravada em 04/08 e ainda não foi exercitada: a pesquisa de 05/08 rodou em sessão aberta antes da mudança e não a recebeu. É a hipótese mais importante em aberto.
- **Teste em domínio sem fonte primária.** A skill só viu temas com resposta certa e fonte oficial, de regulação e mercado. Em tema de gosto ou comportamento o risco muda: preferência apresentada como regra, convenção de nicho apresentada como consenso. Há instrução no passo 5b, ainda não exercitada.
- **Verificação de que a fonte sustenta a afirmação**, e não apenas que existe e trata do tema. Desenhada, não implementada, esperando um caso concreto.
- **Nenhum caso com resposta conhecida.** Se um relatório sair inteiro errado, nada acusa.
- **Substituir os indicadores de fontes coletadas e tempo total no painel**, que perderam utilidade, por taxa de confirmação e taxa de URL reprovada.
- **Modo `profunda` nunca exercitado.**

## Como retomar

1. Ler este arquivo.
2. `python3 skill/scripts/qualidade.py` — estado atual dos motores, variação desde a última medição e erros recentes.
3. Abrir `outputs/dashboard.html` se quiser o quadro visual.
4. `git log --oneline` para o que mudou por último.
5. CHANGELOG só quando precisar do porquê de uma decisão específica. Está em ordem cronológica, do mais antigo ao mais recente.

**Uma advertência que custou uma pesquisa:** edição em arquivo de skill não alcança sessão já aberta. Correção vale a partir da próxima sessão, não da próxima pesquisa.
