---
name: pesquisa
description: Pesquisa profunda com validação cruzada entre três motores de busca independentes (xAI, OpenAI, Google, com Perplexity opcional) via OpenRouter. O Claude Code orquestra, extrai o que foi confirmado por mais de uma fonte, dispara uma segunda rodada para resolver divergências e entrega relatório em markdown com todas as referências. Usar quando o pedido for de pesquisa que precisa ser confiável, com fontes, sobre tema factual ou de mercado. Triggers "pesquisa", "/pesquisa", "pesquisa profunda", "pesquisa orquestrada", "levanta as fontes sobre".
---

# /pesquisa — pesquisa com validação cruzada

Três motores de busca com índices diferentes pesquisam o mesmo tema em paralelo. O que dois ou mais confirmam entra no relatório como fato. O que só um trouxe volta para os outros validarem numa segunda rodada. O que sobra sem confirmação entra marcado.

Você é o orquestrador. O script `scripts/buscar.py` é o único ponto que gasta crédito do OpenRouter, e serve só para chamar os motores. Clarificação, análise, decisão do que validar e redação final são seu trabalho, aqui dentro.

## Regras duras

Estas não se negociam. Violar qualquer uma invalida o relatório.

1. **Agente sem URL não confirma nada.** Se o script marcar `sem_fontes: true`, aquele agente respondeu de memória. Não conta como fonte, não sustenta consenso, não vira "confirmado por dois". Registre a falha na seção de limitações do relatório.
2. **Fonte reprovada manda a afirmação para revalidação, nunca para o lixo.** O script confere cada URL em quatro camadas — se existe, se a forma é de fonte real, se o modelo confessou tê-la construído e se a página ao menos trata do tema. Os estados são `inventada` (não existe e nunca esteve no arquivo da internet), `removida` (existiu e saiu do ar, então a informação pode ser real), `fora do tema` (existe mas fala de outra coisa) e `suspeita` (forma ou contexto ruins).

   **Descartar em silêncio é proibido.** A afirmação pode ser verdadeira com a citação errada, e apagá-la tira do relatório informação boa sem deixar rastro — o leitor nunca fica sabendo que faltou. O script devolve `afirmacoes_a_revalidar`, com o trecho exato que cada fonte reprovada sustentava, e todas entram obrigatoriamente na rodada 2. Só depois se decide: confirmada por fonte que existe, entra normalmente; não confirmada, vai para limitações, nomeada, dizendo o que se tentou verificar e não se conseguiu.

   Este é o modo de falha mais perigoso do produto. Zero URL é visível. URL presente que aponta para uma página inventada parece verificada e ninguém confere. Já aconteceu: um motor construiu link plausível para um estudo que os outros dois depois declararam inexistente.
3. **Nenhuma URL verificada é descartada.** Toda URL que passou entra nas referências, mesmo sustentando informação fraca. As reprovadas não entram como referência: vão para a seção de limitações, nomeadas, com o motivo.
4. **Fonte única é sempre marcada.** Nunca apresente como fato o que só um motor trouxe. O marcador é literal: `(fonte única — verificar)`.
5. **Nunca inventar confirmação.** Se você não achou a mesma informação em dois agentes, ela não é consenso. Na dúvida, trate como fonte única.
6. **Confirmar o custo antes de gastar.** Nunca dispare a rodada 1 sem mostrar a estimativa e receber o aval do Danilo. A estimativa vem como faixa, não como número: o motor de busca profunda cobra por consulta interna e varia com o tema.
7. **Não pesquise você mesmo.** Seu WebSearch não substitui os motores — usá-lo destruiria a lógica de validação cruzada, porque não é um índice independente auditável. Você lê, compara e escreve.

## Fluxo

### Passo 0 — Data real

```bash
date "+%Y-%m-%d %H:%M"
```

Vale para o cabeçalho do relatório e o nome da pasta. Não estime a hora.

### Passo 1 — Clarificação

Use `AskUserQuestion` para conduzir, com opções concretas em vez de perguntas abertas sempre que der. Cobrir obrigatoriamente:

- Objetivo e uso da pesquisa, ou seja, para que serve o resultado
- O que ele já sabe sobre o tema, para não gastar rodada com o óbvio
- Hipótese a confirmar ou refutar
- Ângulos que precisam obrigatoriamente ser cobertos
- Perspectiva contrária que ele queira entender mesmo se enfraquecer a hipótese
- Recorte temporal e geográfico, quando fizer diferença

Pergunte também o modo, se ele não disse: `rapida`, `normal` ou `profunda`. O padrão é `normal`.

**A última aba é sempre a escolha dos motores.** Monte-a a partir de `motores_disponiveis` no `config.json`, com `multiSelect: true`, mostrando rótulo, índice e custo típico de cada um. Os marcados com `padrao: true` são a sugestão.

Regra ao montar o cardápio: um índice por família. Dois motores da mesma família leem as mesmas páginas, e aí a concordância entre eles não valida nada — só encarece. Se o Danilo escolher dois da mesma família, diga isso e confirme antes de seguir.

Três é o número de trabalho. Com dois não há como arbitrar contradição, e cada motor além de três é mais material para comparar sem ganho proporcional de independência. Se ele escolher dois, avise que a rodada 2 perde o árbitro; se escolher quatro ou mais, avise que a análise fica mais rasa.

Quando a lista de `motores_disponiveis` passar de quatro, pare de oferecer um a um: monte a aba com combinações prontas por perfil — econômica, equilibrada, profunda — mais uma opção de escolher manualmente.

Depois da escolha, grave os slots escolhidos e use `--agentes` nas duas rodadas. Se ele escolher um conjunto diferente do configurado, não edite o `config.json`: passe a seleção na linha de comando e registre no `meta.json`.

Não avance sem objetivo e hipótese. O resto pode ficar em aberto.

### Passo 2 — Prompt mestre e estimativa

Monte o prompt mestre seguindo `references/prompt-mestre.md`. É o mesmo texto para os três agentes.

Crie a pasta de trabalho e grave o prompt:

```bash
mkdir -p ~/Experimentos/pesquisa-orquestrada/outputs/AAAA-MM-DD_slug-do-tema
```

Mostre a estimativa antes de gastar:

```bash
python3 ~/.claude/skills/pesquisa/scripts/buscar.py \
  --prompt-file <pasta>/prompt_mestre.md --estimar --modo normal --rodada 1
```

Apresente o valor ao Danilo e espere o aval. Se o modo for `profunda`, avise que o agente A pode levar de 3 a 10 minutos.

### Passo 3 — Rodada 1

```bash
python3 ~/.claude/skills/pesquisa/scripts/buscar.py \
  --prompt-file <pasta>/prompt_mestre.md \
  --saida <pasta>/r1.json --rodada 1 --modo <modo> \
  --termos "termo1,termo2,termo3,termo4,termo5"
```

`--termos` liga a conferência de assunto: o script baixa o início de cada página e verifica se ela ao menos fala do tema. Página que existe e responde, mas não menciona nenhum termo, é marcada como fora do tema — é o que acontece quando o modelo acerta o domínio e inventa o caminho, ou cita a home de um site em vez do artigo. Não custa API e leva segundos.

Escolha de cinco a oito substantivos centrais do tema, com quatro letras ou mais. Nomes próprios, termos técnicos e siglas por extenso funcionam bem. Evite palavras genéricas como "análise" ou "mercado", que aparecem em qualquer página e não separam nada. Acentuação não importa.

O script grava `r1.json` e um `r1_A.md`, `r1_B.md`, `r1_C.md` por agente. **Leia os três markdown, um por vez** — não carregue o JSON inteiro, que é grande e repete o conteúdo.

Confira no log quais agentes falharam e quais vieram sem fontes. Se dois ou mais falharem, pare e relate: não há validação cruzada possível com um motor só.

### Passo 4 — Consenso e divergência

Com os três textos lidos, produza um levantamento explícito. Trabalhe por afirmação, não por parágrafo.

Para cada afirmação relevante, classifique:

- **Consenso** — dois ou mais agentes com fonte afirmam o mesmo. Vai direto ao relatório.
- **Fonte única** — um só agente trouxe. Vira alvo de validação na rodada 2.
- **Contradição** — agentes discordam sobre o mesmo ponto, tipicamente número, data ou atribuição. O terceiro agente arbitra na rodada 2.
- **Fonte reprovada** — vem pronto em `afirmacoes_a_revalidar` no JSON de cada agente, com o trecho e o motivo da reprovação. Entra na rodada 2 com prioridade máxima, sem exceção.

Uma afirmação com fonte reprovada não vira consenso mesmo que outro agente diga algo parecido. Enquanto a fonte não se sustenta, a afirmação está em quarentena.

Cuidado com falso consenso: dois agentes citando a mesma matéria não são duas fontes, são uma. Compare as URLs antes de chamar de confirmado.

Mostre ao Danilo um resumo curto do que foi consenso e do que vai para validação. Não peça aprovação, só informe e siga.

### Passo 5 — Rodada 2 cirúrgica

Monte um prompt por agente, contendo **apenas o que ele precisa validar**. Nunca mande o resultado completo dos outros — isso contamina e encarece.

Cada prompt deve dizer o que verificar, pedir confirmação ou refutação com fonte e exigir a seção de URLs. Se um agente não tem nada a validar, o valor dele é `null`.

**Quem citou não valida a própria citação.** Uma afirmação com fonte reprovada vai para os outros motores, nunca para quem a produziu — o modelo que construiu o link tende a defendê-lo, e o teste deixa de ser teste. Se só um outro motor está disponível, vale assim mesmo; se nenhum, a afirmação vai direto para limitações.

Ao montar o item, dê o trecho e o que se procura, **sem dizer que a fonte era falsa**. O agente precisa procurar a informação do zero, não avaliar um veredito pronto. Escreva no formato de "verifique se isto procede e traga a fonte", nunca "confirme que isto é falso".

Grave `<pasta>/prompts_r2.json`:

```json
{ "A": "texto do prompt...", "B": null, "C": "texto do prompt..." }
```

```bash
python3 ~/.claude/skills/pesquisa/scripts/buscar.py \
  --prompts-file <pasta>/prompts_r2.json \
  --saida <pasta>/r2.json --rodada 2 --modo <modo> \
  --termos "os mesmos termos da rodada 1"
```

Leia os markdown da rodada 2 do mesmo jeito.

### Passo 6 — Relatório final

Escreva seguindo `references/formato-relatorio.md`. Salve em:

```
~/Experimentos/pesquisa-orquestrada/outputs/AAAA-MM-DD_slug-do-tema/relatorio.md
```

### Passo 7 — Metadados e painel

Grave `meta.json` na mesma pasta. É o que alimenta o painel:

```json
{
  "data": "AAAA-MM-DD",
  "tema": "título curto da pesquisa",
  "objetivo": "uma linha, saída da clarificação",
  "hipotese": "a hipótese testada",
  "modo": "normal",
  "afirmacoes_fonte_unica": 0,
  "divergencias_nao_resolvidas": 0,
  "contribuicao_por_motor": {
    "A": { "afirmacoes": 0, "confirmadas": 0, "exclusivas_no_relatorio": 0, "descartadas": 0 },
    "B": { "afirmacoes": 0, "confirmadas": 0, "exclusivas_no_relatorio": 0, "descartadas": 0 },
    "C": { "afirmacoes": 0, "confirmadas": 0, "exclusivas_no_relatorio": 0, "descartadas": 0 }
  },
  "nota_manual": { "A": null, "B": null, "C": null }
}
```

O bloco `contribuicao_por_motor` é o que mede qual motor vale o que custa. Você já faz essa contagem no passo 4, ela só não estava sendo gravada. Para cada motor:

- `afirmacoes` — quantas afirmações dele entraram no relatório final
- `confirmadas` — quantas dessas outro motor também sustentou
- `exclusivas_no_relatorio` — quantas entraram apoiadas só nele
- `descartadas` — quantas você deixou de fora por fonte reprovada, contradição perdida ou irrelevância

Conte por afirmação, não por parágrafo. Se não der para separar com honestidade, grave `null` em vez de chutar: número inventado aqui contamina a série inteira e é pior que campo vazio.

`nota_manual` é opcional, de 1 a 5, só quando o Danilo quiser dar. Não pergunte a cada pesquisa.

Regenere o painel:

```bash
python3 ~/.claude/skills/pesquisa/scripts/dashboard.py
```

Feche informando ao Danilo: caminho do relatório, custo real somado de todas as rodadas (campo `custo_real_usd` em cada JSON), quantas afirmações ficaram como fonte única e o que permaneceu sem resolução.

## Comandos do script

| Objetivo | Comando |
|---|---|
| Estimar sem gastar | `--prompt-file X.md --estimar` |
| Rodada 1 | `--prompt-file X.md --saida r1.json --rodada 1` |
| Rodada 2 | `--prompts-file P.json --saida r2.json --rodada 2` |
| Subconjunto de agentes | `--agentes A,C` |
| Modo | `--modo rapida\|normal\|profunda` |

Configuração dos modelos, preços e modos: `config.json`. Trocar de motor é trocar a string `modelo`.

Chave: lida de `OPENROUTER_API_KEY` no ambiente, ou de `~/.claude/.env`. Nunca imprima a chave, nunca a copie para dentro de um projeto.

## Quando algo dá errado

**Agente com zero URL.** Não é bug do script, é o modelo respondendo de memória. Ele não conta como fonte. Se for recorrente no mesmo slot, verifique se `engine_busca` está declarado no `config.json` — sem `engine` explícito, os modelos Google ignoram o plugin de busca em silêncio.

**Resposta truncada (`finish=length`).** Suba o modo, ou o `max_tokens_r1` do modo em uso.

**Texto curto e caro.** O modelo gastou o orçamento em raciocínio interno. Confirme que `reasoning_effort` está como `low` para aquele agente.

**Um agente falhou na rodada 1.** Continue com os dois restantes e registre a falha na seção de limitações. Com um só, pare.

**Modelo não existe mais.** O catálogo do OpenRouter muda rápido. Consulte `https://openrouter.ai/models` e atualize `config.json`, incluindo o bloco `precos_por_milhao_usd`.
