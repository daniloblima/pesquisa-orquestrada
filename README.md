# Pesquisa orquestrada

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

Clone o repositório e ligue a skill ao Claude Code:

```bash
git clone https://github.com/<usuario>/pesquisa-orquestrada.git
ln -s "$(pwd)/pesquisa-orquestrada/skill" ~/.claude/skills/pesquisa
```

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

A skill conduz a clarificação, mostra a faixa de custo estimada, espera seu aval e roda as duas rodadas. O relatório sai em `outputs/AAAA-MM-DD_tema/relatorio.md`, junto com o material bruto de cada motor.

O painel fica em `outputs/dashboard.html` e abre com duplo clique. Mostra custo acumulado, desempenho por motor, fontes exclusivas e as fontes mais recorrentes.

## Motores

Configuração em [skill/config.json](skill/config.json). Trocar de motor é trocar uma string.

| Slot | Padrão | Índice |
|---|---|---|
| A | `perplexity/sonar-deep-research` | Perplexity |
| B | `openai/gpt-5.6-terra` | OpenAI |
| C | `google/gemini-3.1-pro-preview` | Google |

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

Hoje cada URL passa por quatro camadas: se existe, se a forma é de fonte real, se o modelo confessou tê-la construído no texto ao redor e se a página trata do tema. Quando não resolve, o arquivo da internet separa página removida de URL que nunca existiu — só a segunda indica invenção. Nenhuma camada custa API, e falha de checagem nunca vira acusação: o estado fica inconclusivo.

**Estimativa de custo com parâmetro único.** Motores cobram de formas incompatíveis: um recebe os resultados de busca no prompt e chega a 80 mil tokens de entrada, outro pesquisa do lado do provedor e cobra por consulta. Nenhuma média serve para os dois, e a estimativa errava por fator de 2 a 3 nas duas direções.

## Limitações

Roda dentro do Claude Code, não é aplicação independente.

A qualidade depende de os motores serem mesmo independentes. Se dois deles usarem o mesmo índice de busca, a concordância entre eles vira artefato do método.

Confirmação por dois motores reduz o risco de erro, não o elimina. Modelos compartilham dados de treino e vieses, então erros não são inteiramente independentes e não se cancelam como amostras aleatórias.

## Licença

MIT.
