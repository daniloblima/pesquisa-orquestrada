# Pesquisa orquestrada

Versão 2.4.0, de 23/09/2026. O histórico de versões está no fim deste arquivo e o detalhe de cada mudança no [CHANGELOG.md](CHANGELOG.md).

Skill do Claude Code que faz pesquisa com validação cruzada entre três motores de busca independentes, via OpenRouter.

Três modelos de famílias diferentes pesquisam o mesmo tema em paralelo, cada um com seu próprio índice. O que dois ou mais confirmam entra no relatório como fato. O que só um trouxe volta para os outros validarem numa segunda rodada. O que sobra sem confirmação entra marcado.

O problema que resolve: rodar o mesmo prompt no Perplexity, no ChatGPT e no Gemini, copiar os três resultados e sintetizar à mão. Isso não tem lógica de validação, perde fontes pelo caminho e depende de julgamento manual para saber no que confiar.

## Como funciona

```
/pesquisa <tema>
  │
  ├─ Claude Code: entrevista de clarificação
  ├─ Claude Code: monta o prompt mestre
  ├─ scripts/buscar.py ──> OpenRouter, 3 motores em paralelo      [gasta crédito]
  ├─ Claude Code: separa consenso de divergência
  ├─ scripts/buscar.py ──> rodada 2, prompt cirúrgico por motor   [gasta crédito]
  ├─ Claude Code: consolida o relatório
  └─ scripts/dashboard.py: atualiza o painel
```

A orquestração inteira roda no Claude Code. O OpenRouter paga apenas as chamadas de pesquisa, que é o que o Claude Code não consegue fazer sozinho: acessar motores heterogêneos com índices independentes.

## Instalação

Requisitos: Claude Code, Python 3.9 ou superior e uma conta no OpenRouter com crédito. O script não usa biblioteca externa, só a padrão do Python.

O repositório tem três skills que trabalham juntas, e as três precisam ser ligadas ao Claude Code:

| Skill | Pasta | Para que serve |
|---|---|---|
| `/pesquisa` | `skill/` | conduz a pesquisa inteira e guarda todos os scripts |
| `/verificar` | `skill-verificar/` | confere se as fontes prestam antes de virarem relatório; a `/pesquisa` a chama sozinha |
| `/qualidade` | `skill-qualidade/` | mede o desempenho dos motores ao longo das pesquisas |

Clone o repositório e crie os três atalhos. Os nomes dos atalhos importam, porque as skills se chamam por eles:

```bash
git clone https://github.com/daniloblima/pesquisa-orquestrada.git
cd pesquisa-orquestrada
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skill" ~/.claude/skills/pesquisa
ln -s "$(pwd)/skill-verificar" ~/.claude/skills/verificar
ln -s "$(pwd)/skill-qualidade" ~/.claude/skills/qualidade
```

Abra uma sessão nova do Claude Code depois de criar os atalhos: sessão já aberta não enxerga skill nova.

Grave a chave fora do repositório, com permissão restrita:

```bash
mkdir -p ~/.claude && touch ~/.claude/.env && chmod 600 ~/.claude/.env
echo 'OPENROUTER_API_KEY=sua_chave_aqui' >> ~/.claude/.env
```

A chave nunca mora junto do código. O script procura primeiro na variável de ambiente `OPENROUTER_API_KEY`, depois em `~/.claude/.env` e em `~/.config/openrouter/.env`.

## Uso

No Claude Code, em qualquer pasta:

```
/pesquisa regulação de armazenamento de energia no Brasil
```

A skill conduz a clarificação, mostra a faixa de custo estimada, espera seu aval e roda as duas rodadas. O relatório sai em `<pasta das pesquisas>/AAAA-MM-DD_tema/relatorio.md`, junto com o material bruto de cada motor.

**Onde as pesquisas ficam.** Na primeira pesquisa, a skill pergunta onde você quer guardá-las e grava a resposta como `PESQUISA_SAIDA` em `~/.claude/.env`, o mesmo arquivo da chave. O padrão sugerido é a pasta `outputs/` dentro do repositório, que o git ignora. Os relatórios podem conter material confidencial, então escolher uma pasta sincronizada com a nuvem é decisão sua. Para ver ou trocar a pasta depois:

```bash
python3 skill/scripts/pasta.py                      # mostra a pasta atual
python3 skill/scripts/pasta.py --definir ~/Pesquisas  # troca
```

O painel fica em `<pasta das pesquisas>/dashboard.html` e abre com duplo clique. Mostra custo acumulado, desempenho por motor, fontes exclusivas e as fontes mais recorrentes.

## Motores

Configuração em [skill/config.json](skill/config.json). Trocar de motor é trocar uma string.

Composição padrão desde 12/08/2026:

| Motor | Índice | Padrão | Custo típico |
|---|---|---|---|
| `x-ai/grok-4.20-multi-agent` | xAI | sim | US$ 0,35 a 0,68, conforme o material que ele decide ler |
| `openai/gpt-5.6-terra` | OpenAI | sim | US$ 0,18 |
| `perplexity/sonar-deep-research` | Perplexity | sim | US$ 1,12 |
| `google/gemini-3.1-pro-preview` | Google | não | US$ 0,12 |

O Gemini saiu do padrão por concentrar as URLs inventadas da série, sete das oito, e continua disponível por escolha explícita. O Perplexity entrou por ser índice independente dos outros dois. A escolha dos motores é oferecida a cada pesquisa, e a composição padrão é o que roda quando `--motores` é omitido.

Para ver o que existe hoje no OpenRouter e conferir se o que está configurado ainda vale:

```bash
python3 skill/scripts/motores.py
```

O critério de escolha é independência antes de preço. Três motores de famílias diferentes valem mais que cinco da mesma: o que dá validação é ler páginas diferentes, não gerar mais texto sobre as mesmas.

## Custo

Entre US$ 1 e 2,50 por pesquisa completa em modo normal, dependendo dos motores. A estimativa aparece como faixa antes de qualquer gasto, e o custo real fica registrado no painel.

Cuidado com modelos de busca profunda: eles cobram por consulta interna, não só por token. O `sonar-deep-research` custou US$ 1,12 numa chamada cujos tokens valiam US$ 0,05.

Para estimar sem gastar nada:

```bash
python3 skill/scripts/buscar.py --prompt-file prompt.md --estimar
```

## O que este projeto aprendeu apanhando

Estão todos documentados em [CHANGELOG.md](CHANGELOG.md), com sintoma, causa e correção. Os três que mais importam para quem for construir algo parecido:

**Busca web que falha em silêncio.** O plugin de busca do OpenRouter sem `engine` explícito é ignorado pelos modelos Google. Sem erro, sem aviso: o modelo responde de memória e o resultado parece normal. Só a inspeção da contagem de tokens de entrada revelou. Toda integração com busca precisa de um sinal verificável de que a busca aconteceu.

**URL que existe na forma e não no mundo.** A primeira trava protegia contra o motor que volta sem nenhuma fonte, que é o caso visível. O caso grave é o oposto: link plausível, bem formado, apontando para uma página inventada, que entra nas referências parecendo verificado.

A literatura mede esse fenômeno: de 3% a 13% das URLs citadas por agentes de pesquisa nunca existiram, e agentes de busca profunda alucinam a taxas maiores que modelos com busca simples ([arXiv 2604.03173](https://arxiv.org/abs/2604.03173), [arXiv 2605.06635](https://arxiv.org/html/2605.06635v1)). Não é acidente de um modelo ruim, é taxa base.

Hoje cada URL passa por seis camadas: se existe, se a forma é de fonte real, se o modelo confessou tê-la construído no texto ao redor, se a página trata do tema, se ela traz o número que a afirmação atribui a ela, e se sustenta o que disseram que ela sustenta. Quando não resolve, o arquivo da internet separa página removida de URL que nunca existiu — só a segunda indica invenção. Falha de checagem nunca vira acusação: o estado fica inconclusivo.

As cinco primeiras medem forma e não custam API. A sexta lê sentido, e é a única que consulta um modelo: o Jev, da TypeSafe, que responde pergunta tipada e devolve um veredito com probabilidade em vez de texto. Ela é opcional — sem chave configurada a skill roda igual, com a conferência de tema por vocabulário no lugar dela. Com chave, custa cerca de US$ 0,012 numa pesquisa de 109 URLs, contra os US$ 2,38 de média que a pesquisa inteira custa.

**Por que uma camada de sentido faz diferença.** As cinco primeiras respondem "esta página existe e fala do assunto?". Nenhuma responde "o que está escrito ali sustenta o que disseram?". A diferença aparece em dois lugares. Fonte legítima escrita em outro idioma era reprovada por vocabulário, porque a conferência casa raiz de palavra: uma página em inglês que traz exatamente a frase traduzida na afirmação era marcada como fora do tema. E afirmação sem número não era avaliável de forma alguma — numa pesquisa medida, 31 das 47 URLs com contexto passavam sem nenhum julgamento de conteúdo.

**O que ela não faz.** Não julga afirmação de ausência — "não existe dispositivo", "não há precedente" —, porque modelos erram em dupla negação e um veredito de "sustenta" sobre uma negação viraria autorização. Essas vão para conferência em fonte primária, que é o que a regra de ausência sempre mandou fazer.

**Estimativa de custo com parâmetro único.** Motores cobram de formas incompatíveis: um recebe os resultados de busca no prompt e chega a 80 mil tokens de entrada, outro pesquisa do lado do provedor e cobra por consulta. Nenhuma média serve para os dois, e a estimativa errava por fator de 2 a 3 nas duas direções.

## Qualidade dos motores

A skill mede sozinha o desempenho de cada motor a partir das pesquisas que você fizer, e usa isso para decidir o peso de cada um na análise:

```bash
python3 skill/scripts/qualidade.py
```

Três medidas por motor — precisão de fonte (URLs que passaram na verificação, equivalente ao Citation Accuracy da literatura), taxa de confirmação e confiabilidade operacional — comparadas com os limiares do `config.json`. Daí sai o papel do motor: confirmação, confirmação com ressalva ou descoberta.

**A série começa vazia e é sua.** As medições ficam em `skill/qualidade-motores.json`, fora do repositório: nota de motor calculada sobre as pesquisas de outra pessoa não diz nada sobre o seu uso, e o histórico carregaria os temas que essa pessoa pesquisou. Até acumular duas pesquisas e vinte URLs por motor, todos são tratados como confirmação com ressalva.

Nenhum julgamento sobre modelo específico está escrito no código ou na configuração. O que é fixo são os limiares; a nota sai dos dados e muda sozinha quando o modelo muda.

### O que a experiência de um usuário sugeriu

Três pesquisas, agosto de 2026, sem valor estatístico — serve para dar ordem de grandeza a quem for calibrar os limiares:

| Precisão de fonte | Observado |
|---|---|
| Melhor motor | cerca de 90% |
| Pior motor | cerca de 77% |

O motor com a pior precisão foi também o que mais produziu URLs sem qualquer registro no arquivo da internet, isto é, que provavelmente nunca existiram. Nos demais, as reprovações foram sobretudo páginas fora do ar ou fora do assunto, que são falhas de outra natureza.

Isso é coerente com a literatura de avaliação de agentes de pesquisa, que mede um trade-off consistente: **quem cita mais tende a citar pior**, atribuído a diluição de atenção durante a síntese ([DeepResearch Bench](https://arxiv.org/pdf/2506.11763), [Cited but Not Verified](https://arxiv.org/html/2605.06635v1)). Por isso o índice desta skill não premia volume de fontes — premiar quantidade seria premiar o comportamento associado a menor precisão.

## Limitações

Roda dentro do Claude Code, não é aplicação independente.

A qualidade depende de os motores serem mesmo independentes. Se dois deles usarem o mesmo índice de busca, a concordância entre eles vira artefato do método.

Confirmação por dois motores reduz o risco de erro, não o elimina. Modelos compartilham dados de treino e vieses, então erros não são inteiramente independentes e não se cancelam como amostras aleatórias.

## Versões

O projeto segue versionamento semântico. O número do meio sobe a cada funcionalidade nova, o último a cada correção, e o primeiro quando muda a estrutura da skill. Cada versão tem uma marca de release no GitHub.

| Versão | Data | O que entregou | Commit |
|---|---|---|---|
| 1.0.0 | 05/08/2026 | Skill em produção: três motores via OpenRouter, rodada de revalidação, verificação de fontes pelo arquivo da internet e índice de qualidade por motor | `e40ea7b` |
| 2.0.0 | 13/08/2026 | A verificação vira skill separada da coleta (`/verificar`), com falha dura separada de sinal fraco. Mudança de estrutura, por isso versão maior | `d8a6709` |
| 2.1.0 | 21/08/2026 | Quinta camada (a fonte traz o número atribuído a ela), régua de regressão contra as pesquisas já feitas e nota dos motores publicada com a skill | `205b18d` |
| 2.2.0 | 31/08/2026 | Saldo do OpenRouter na estimativa e aferição do custo previsto contra o gasto | `34775d7` |
| 2.3.0 | 23/09/2026 | Sexta camada (a fonte sustenta a afirmação, via Jev), correções de URL suja, coerência numérica e truncamento, prompt legível antes de pagar. Arquivo LICENSE e versionamento | tag `v2.3.0` |
| 2.4.0 | 23/09/2026 | Instalação autônoma: o README liga as três skills, a pasta das pesquisas é perguntada na primeira pesquisa e gravada em `~/.claude/.env` (`pasta.py`), caminhos da máquina do autor e o nome dele saem das instruções | tag `v2.4.0` |

## Licença

MIT. O texto completo está em [LICENSE](LICENSE).
