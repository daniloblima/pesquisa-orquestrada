---
name: pesquisa
description: Pesquisa profunda com validação cruzada entre motores de busca independentes via OpenRouter. Conduz a clarificação, dispara os motores, chama a skill verificar antes de usar o material, resolve divergências numa segunda rodada e entrega relatório com todas as referências e o grau de confirmação de cada afirmação. Usar quando o pedido for de pesquisa que precisa ser confiável, com fontes, sobre tema factual ou de mercado. Triggers "pesquisa", "/pesquisa", "pesquisa profunda", "pesquisa orquestrada", "levanta as fontes sobre".
---

# /pesquisa — pesquisa com validação cruzada

Três motores de busca com índices diferentes pesquisam o mesmo tema em paralelo. O que dois ou mais confirmam entra no relatório como fato. O que só um trouxe volta para os outros validarem numa segunda rodada. O que sobra sem confirmação entra marcado.

Você é o orquestrador. O script `scripts/buscar.py` é o único ponto que gasta crédito do OpenRouter, e serve só para chamar os motores. Clarificação, análise, decisão do que validar e redação final são seu trabalho, aqui dentro.

## Regras duras

Estas não se negociam. Violar qualquer uma invalida o relatório.

1. **Agente sem URL não confirma nada.** Se o script marcar `sem_fontes: true`, aquele agente respondeu de memória. Não conta como fonte, não sustenta consenso, não vira "confirmado por dois". Registre a falha na seção de limitações do relatório.
2. **Fonte reprovada manda a afirmação para revalidação, nunca para o lixo.** O script confere cada URL em quatro camadas — se existe, se a forma é de fonte real, se o modelo confessou tê-la construído e se a página ao menos trata do tema.

   **Os estados têm gravidades diferentes, e essa diferença manda.** Falha dura é `inventada` (não existe e nunca esteve no arquivo da internet), `removida` (existiu e saiu do ar, então a informação pode ser real), `inexistente` (404) e `suspeita` (o texto ao lado do link admite que ele foi construído, ou o domínio é encurtador ou hospedagem). Sinal fraco é `fora do tema` (a conferência de assunto não achou os termos), `inconclusiva` (não deu para ler a página, por muro de acesso, documento sem HTML ou falha de rede) e `citação imprecisa` (a URL é domínio raiz, sem página específica).

   **Domínio raiz é sinal fraco desde 21/08/2026, e antes era falha dura.** A heurística julga forma, e forma não prova invenção: numa pesquisa sobre valor residual de ASIC, as duas únicas falhas duras da rodada 1 eram `asicminervalue.com` e `hashrateindex.com`, as duas referências centrais do tema, ambas no ar. Quando a fonte é uma plataforma cujo produto é o próprio índice, citar a raiz é a citação correta. Continua indo para a revalidação, que é o tratamento que a imprecisão merece, e deixou de pesar contra o motor.

   Só falha dura pesa contra o motor. Sinal fraco entra no relatório como aviso de leitura e nunca desqualifica agente nem afirmação sozinho: em 12/08/2026, 103 das 161 reprovações acumuladas eram sinal fraco, com falso positivo comprovado em quatro páginas que estavam exatamente no tema.

   **Descartar em silêncio é proibido.** A afirmação pode ser verdadeira com a citação errada, e apagá-la tira do relatório informação boa sem deixar rastro — o leitor nunca fica sabendo que faltou. O script devolve `afirmacoes_a_revalidar`, com o trecho exato que cada fonte reprovada sustentava, e todas entram obrigatoriamente na rodada 2. Só depois se decide: confirmada por fonte que existe, entra normalmente; não confirmada, vai para limitações, nomeada, dizendo o que se tentou verificar e não se conseguiu.

   **Quando o trecho não se localiza, a quarentena é da afirmação e não do agente.** O campo `reprovadas_sem_rastro` diz que alguma fonte com falha dura não pôde ser ligada a nenhum trecho, nem por URL escrita no corpo nem por marcador numerado. Isso põe em dúvida o que se apoiava naquela fonte, e nada além disso. A regra antiga invalidava a contribuição inteira do motor e, em 12/08/2026, jogou fora seis respostas boas do Perplexity, que cita em estilo acadêmico — inclusive vereditos corretos sobre Potosí, Barbegal e a série de tonelagem a vapor, que estavam escritos no sumário.

   Este é o modo de falha mais perigoso do produto. Zero URL é visível. URL presente que aponta para uma página inventada parece verificada e ninguém confere. Já aconteceu: um motor construiu link plausível para um estudo que os outros dois depois declararam inexistente.
3. **Nenhuma URL verificada é descartada.** Toda URL que passou entra nas referências, mesmo sustentando informação fraca. As reprovadas não entram como referência: vão para a seção de limitações, nomeadas, com o motivo.
4. **Fonte única é sempre marcada.** Nunca apresente como fato o que só um motor trouxe. O marcador é literal: `(fonte única — verificar)`.
5. **Nunca inventar confirmação.** Se você não achou a mesma informação em dois agentes, ela não é consenso. Na dúvida, trate como fonte única.
6. **Confirmar o custo antes de gastar.** Nunca dispare a rodada 1 sem mostrar a estimativa e receber o aval do Danilo. A estimativa vem como faixa, não como número: o motor de busca profunda cobra por consulta interna e varia com o tema.
7. **Não pesquise você mesmo.** Seu WebSearch não substitui os motores — usá-lo destruiria a lógica de validação cruzada, porque não é um índice independente auditável. Você lê, compara e escreve.
8. **Consenso sobre ausência não é prova de ausência.** A validação cruzada confirma o que os motores encontram; ela não diz nada sobre o que todos deixaram de encontrar. Se os três concordam que uma norma, um precedente ou um estudo não existe, isso não é um fato confirmado por três fontes — é uma busca que falhou três vezes, possivelmente pelo mesmo motivo.

   Nunca escreva "não existe" com base em concordância. Escreva que os motores não localizaram, e diga onde se procurou. Quando a resposta negativa importa para a decisão do Danilo — e ela quase sempre importa, porque "não há impedimento" costuma virar autorização —, abra a fonte primária e confira você mesmo.

   Aconteceu em 04/08/2026: os três afirmaram que nenhum dispositivo impunha teto de 75 kW à potência de geração. O art. 23, § 6º, da REN ANEEL 1.000/2021 diz exatamente isso, e nenhum dos três o localizou. Só apareceu na conferência manual do texto oficial.

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

**Dois eixos, e são independentes.** Pergunte os dois, em abas separadas.

*Profundidade* — `rapida`, `normal` ou `profunda`, padrão `normal`. Governa custo: quantos
motores, teto de tokens, resultados por busca.

*Criticidade* — `baixa`, `media` ou `alta`, padrão `media`. Governa rigor: quantas origens
independentes o consenso exige, se os gatilhos param o fluxo e se a conferência em fonte primária
é obrigatória.

Os dois se combinam livremente, e confundi-los estraga a pesquisa nas duas pontas. Corroborar um
dado específico é rápido com criticidade alta. Levantar exemplos de marketing B2B em empresas
centenárias é profundo com criticidade baixa.

**Antes de qualquer coisa, consulte a memória.** O que já foi estabelecido não se compra de novo:

```bash
python3 ~/.claude/skills/pesquisa/scripts/memoria.py buscar <termos do tema>
```

Se houver afirmação registrada sobre o tema, mostre ao Danilo antes de montar o prompt — com a
data e o aviso de vencimento, quando houver. Pesquisa que redescobre o que já se sabia é dinheiro
gasto duas vezes, e pior, pode contradizer o próprio acervo sem ninguém notar.

**A última aba é sempre a escolha dos motores.** Monte-a a partir da lista `motores` do `config.json`, com `multiSelect: true`, mostrando rótulo, índice e custo típico. Os marcados com `padrao: true` são a sugestão.

Não há teto nem mínimo. O número de motores é consequência da escolha, e a lista é aberta: motor novo é item novo no `config.json`, sem mexer em código. Nunca edite o `config.json` no meio de uma pesquisa para acomodar uma escolha — passe os ids em `--motores`. Só se acrescenta motor ao config quando ele passa a ser opção permanente, e aí com `padrao: false` até provar que vale.

As regras de composição continuam valendo e o script as repete no log, calculadas sobre o número escolhido:

- **Um índice por família.** Dois motores da mesma família leem as mesmas páginas, e a concordância entre eles não valida nada.
- **Dois motores não têm árbitro.** A rodada 2 perde a função de arbitrar contradição.
- **Acima de três a análise fica mais rasa**, porque cresce o material a comparar sem ganho proporcional de independência.

Diga qual dessas se aplica à escolha dele antes de rodar, mas a decisão é dele — os avisos informam, não bloqueiam.

Quando a lista passar de cinco ou seis, pare de oferecer um a um: monte a aba com combinações por perfil — econômica, equilibrada, profunda — mais uma opção de escolher manualmente.

Depois da escolha, use `--motores <ids>` nas duas rodadas e registre os ids no `meta.json`.

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
  --motores grok,gpt,perplexity
```

`--motores` recebe os ids escolhidos na clarificação. Omitir roda os marcados como padrão no `config.json`, nunca os demais — é o que impede um motor caro de entrar por esquecimento.

O `buscar.py` só coleta. A conferência das fontes acontece no passo seguinte, pela `/verificar`, e é ali que se escolhem os termos do tema.

Escolha de cinco a oito substantivos centrais do tema, com quatro letras ou mais. Nomes próprios, termos técnicos e siglas por extenso funcionam bem. Evite palavras genéricas como "análise" ou "mercado", que aparecem em qualquer página e não separam nada. Acentuação não importa.

**Passe a raiz curta, nunca a forma derivada.** O casamento aceita a raiz mais flexão (`s`, `es`, `ing`, `ings`, `ed`) e termina em fronteira de palavra, então `mill` alcança "mill", "mills", "milling" e "milled", e não alcança "million". O caminho inverso não existe: `milling` não alcança "mill". Em 12/08/2026 uma página do Domesday Book sobre moinhos foi reprovada numa pesquisa sobre moinhos no Domesday Book, por causa disso.

**Forma composta se passa separada.** `watermill` não alcança "water mill", que é como a maior parte das páginas históricas escreve, e o contrário também vale. Quando as duas grafias importam, passe as duas: `watermill,water mill`.

**Cubra o vocabulário da fonte, sem cair na palavra que serve para tudo.** O artigo do FMI sobre 167 anos de dados de energia usa "energy" 76 vezes e "electricity" nenhuma: numa pesquisa de eletrificação rural, `energy` precisa estar na lista. Mas termo largo demais abre a peneira — com `water` e `power` na lista, a página da Wikipédia sobre o Instagram passa numa pesquisa sobre moinhos medievais, medido em 13/08/2026. O critério é o termo que a fonte esperada usaria e que uma página de outro assunto não usaria: `energy` numa pesquisa de energia serve; `power` e `water` não.

O script grava `r1.json` e um markdown por motor, nomeado pelo id: `r1_grok.md`, `r1_gpt.md`, `r1_gemini.md`. **Leia os três markdown, um por vez** — não carregue o JSON inteiro, que é grande e repete o conteúdo.

Confira no log quais agentes falharam e quais vieram sem fontes. Se dois ou mais falharem, pare e relate: não há validação cruzada possível com um motor só.

### Passo 3a — Verificação, obrigatória antes de qualquer leitura de conteúdo

Invoque a skill `/verificar` sobre a pasta. Ela roda a conferência mecânica e o parecer
independente, e devolve `r1_verificacao.json` e `r1_decisoes.md`.

```bash
python3 ~/.claude/skills/pesquisa/scripts/verificar.py <pasta> \
  --rodada 1 --termos "termo1,termo2,termo3" --criticidade <criticidade>
```

**Leia `r1_decisoes.md` antes de ler qualquer resposta de motor.** Se houver itens ali, leve-os
ao Danilo agora, no formato em que estão: no máximo dez, cada um com uma pergunta fechada. Em
criticidade alta, nada segue sem as respostas.

O parecer independente vem de subagente com contexto isolado, seguindo
`references/prompt-parecer.md`. Ele lê o material bruto sem ver a sua análise. Onde a leitura
dele divergir da sua, a divergência vira item de decisão — não resolva sozinho.

### Passo 3b — Como tratar cada motor nesta pesquisa

```bash
python3 ~/.claude/skills/pesquisa/scripts/qualidade.py --resumo
```

Devolve o papel de cada motor, calculado a partir das pesquisas já feitas: **confirmação**, **confirmação com ressalva**, **descoberta** ou **em avaliação**.

Isso não é opinião escrita em lugar nenhum. A nota sai de três medidas — precisão de fonte, taxa de confirmação e confiabilidade — comparadas com os limiares do `config.json`. Motor que melhora sobe de faixa sozinho; motor que piora desce. Nunca escreva no `config.json`, no `SKILL.md` ou no relatório que um modelo específico é bom ou ruim: isso vira mentira na semana seguinte, e a régua existe justamente para dispensar esse julgamento.

Use o papel no passo 4:

- **confirmação** — vale como uma das duas fontes de um consenso, sem ressalva.
- **confirmação com ressalva** — vale como confirmação, mas quando uma afirmação depende só dele e do mínimo, confira a fonte antes de aceitar.
- **descoberta** — não sustenta consenso sozinho. O que vier só dele vai para a rodada 2 mesmo que pareça sólido, e o que sobreviver entra marcado.
- **em avaliação** — amostra pequena; trate como confirmação com ressalva.

Se um motor está em "descoberta", diga isso ao Danilo no resumo do passo 4, com o número medido, não com adjetivo.

### Passo 4 — Consenso e divergência

Com os três textos lidos, produza um levantamento explícito. Trabalhe por afirmação, não por parágrafo.

Para cada afirmação relevante, classifique:

- **Consenso** — dois ou mais agentes com fonte afirmam o mesmo. Vai direto ao relatório.
- **Fonte única** — um só agente trouxe. Vira alvo de validação na rodada 2.
- **Contradição** — agentes discordam sobre o mesmo ponto, tipicamente número, data ou atribuição. O terceiro agente arbitra na rodada 2.
- **Fonte reprovada** — vem pronto em `afirmacoes_a_revalidar` no JSON de cada agente, com o trecho e o motivo da reprovação. Entra na rodada 2 com prioridade máxima, sem exceção.

Uma afirmação com fonte reprovada não vira consenso mesmo que outro agente diga algo parecido. Enquanto a fonte não se sustenta, a afirmação está em quarentena.

Cuidado com falso consenso: dois agentes citando a mesma matéria não são duas fontes, são uma. Compare as URLs antes de chamar de confirmado.

**A `/verificar` mede isso desde 21/08/2026, e o item se chama `eixo compartilhado`.** Ela conta quantas vezes cada domínio é invocado como prova — endereço escrito ao lado da afirmação ou marcador numerado — e acusa o domínio que passa de 20% das provas de algum motor e é citado por mais de um. Leia a seção "De quem a pesquisa depende" no fim do `r_decisoes.md` mesmo quando nenhum item disparar.

**Contar motores não é contar fontes, e a sobreposição agregada não protege.** Na pesquisa de valor residual de ASIC, a sobreposição era 0,176 e até tranquilizava, enquanto a espinha numérica inteira da depreciação vinha de um domínio só, `noxhash.com`, citado pelos dois motores. Ele passou nas quatro camadas de verificação — existe, tem forma de fonte, não foi confessado como construído e trata do tema. O que ele é: uma plataforma que aluga máquina ASIC por assinatura, ou seja, quem ganha ao mostrar que comprar hardware deprecia rápido.

**Cada eixo vem com a linha "Como o site se apresenta", que é o título e a descrição da própria home.** Ali o `noxhash.com` se anuncia como "Cloud Mining Platform | Rent Mining Machines... Start from $20/mo", e a pergunta sobre interesse se responde sozinha. A linha **mostra e não julga**, de propósito: classificar interesse comercial por palavra-chave foi testado em 21/08/2026 e reprovado, porque `aneel.gov.br` casa "assinatura" e "preço" e seria acusada de parte interessada. Fonte primária levando carimbo de vendedor seria o erro do domínio raiz outra vez, na pior fonte possível para errar.

**A ausência da linha não diz nada.** Domínio que recusa leitura automatizada não devolve cartão, e `sec.gov` é um deles. Sem cartão, a pergunta continua de pé e quem responde é você.

Mostre ao Danilo um resumo curto do que foi consenso e do que vai para validação. Não peça aprovação, só informe e siga.

### Passo 5 — Rodada 2 cirúrgica

Monte um prompt por agente, contendo **apenas o que ele precisa validar**. Nunca mande o resultado completo dos outros — isso contamina e encarece.

Cada prompt deve dizer o que verificar, pedir confirmação ou refutação com fonte e exigir a seção de URLs. Se um agente não tem nada a validar, o valor dele é `null`.

**Quem citou não valida a própria citação.** Uma afirmação com fonte reprovada vai para os outros motores, nunca para quem a produziu — o modelo que construiu o link tende a defendê-lo, e o teste deixa de ser teste. Se só um outro motor está disponível, vale assim mesmo; se nenhum, a afirmação vai direto para limitações.

Ao montar o item, dê o trecho e o que se procura, **sem dizer que a fonte era falsa**. O agente precisa procurar a informação do zero, não avaliar um veredito pronto. Escreva no formato de "verifique se isto procede e traga a fonte", nunca "confirme que isto é falso".

Grave `<pasta>/prompts_r2.json`:

```json
{ "grok": "texto do prompt...", "gpt": null, "gemini": "texto do prompt..." }
```

```bash
python3 ~/.claude/skills/pesquisa/scripts/buscar.py \
  --prompts-file <pasta>/prompts_r2.json \
  --saida <pasta>/r2.json --rodada 2 --modo <modo> \
  --motores grok,gpt,gemini
```

Leia os markdown da rodada 2 do mesmo jeito.

### Passo 5a — Verificar a rodada 2

Mesmo comando do passo 3a, com `--rodada 2`. A rodada 2 é onde entram as fontes que vão
sustentar o que sobrou em dúvida: verificá-la importa mais, não menos.

### Passo 5b — Conferência em fonte primária

Obrigatório quando a pesquisa é sobre norma, regulamento, lei ou contrato, e sempre que uma conclusão se apoiar em ausência — não existe vedação, não há precedente, nada impede.

Abra o texto oficial e leia o dispositivo. Não a matéria que comenta o dispositivo, não o site que compila a norma: o PDF da agência, o portal do Planalto, o diário oficial. Motor de busca alcança bem o que foi comentado e mal o que só existe no texto original.

Registre no relatório qual dispositivo foi conferido e onde. Se não deu para abrir a fonte primária, isso vai para limitações — a conclusão passa a ser "os motores não localizaram", nunca "não existe".

Este passo não custa API. Custa alguns minutos de leitura e é o que separa um relatório utilizável de um que parece pronto.

**Quando não existe fonte primária.** Em tema de gosto, estética, comportamento ou recomendação prática, não há texto oficial contra o que conferir, e o passo acima não se aplica. O risco muda de lugar: em vez de norma inventada, o perigo é preferência apresentada como regra, e convenção de um nicho apresentada como consenso.

O que fazer nesses casos, no lugar da conferência: separe no relatório o que é fato verificável — o que uma marca declara, o que um estudo mediu, o que uma norma de etiqueta escrita diz — do que é recomendação de alguém. Recomendação leva o nome de quem recomenda, sempre. Três motores concordando que "deve-se fazer assim" costuma significar que os três leram o mesmo tipo de conteúdo, não que exista consenso no mundo — e aí vale dizer de onde vem a convergência.

### Passo 6 — Relatório final

Escreva seguindo `references/formato-relatorio.md`. Salve em:

```
~/Experimentos/pesquisa-orquestrada/outputs/AAAA-MM-DD_slug-do-tema/relatorio.md
```

### Passo 6b — O que fica na memória

Depois do relatório aprovado, grave as afirmações que valem além desta pesquisa:

```bash
python3 ~/.claude/skills/pesquisa/scripts/memoria.py inserir \
  --fato "..." --valor "..." --tema "energia/regulação" \
  --fonte <URL da fonte primária> --pesquisa <pasta> --origens 2 \
  --vale-ate AAAA-MM-DD --invalida-se "o que precisa mudar no mundo"
```

A porta é estreita de propósito: só entra o que teve duas origens independentes ou o que o Danilo
validou (`--validado`). Uma pesquisa boa rende de cinco a quinze linhas. O resto continua no
relatório, que não se apaga.

Nada vai para o brain-v3 automaticamente. Se um fato sustentar decisão de projeto, ele entra lá
pelo `/salve`, com a curadoria do Danilo.

### Passo 7 — Metadados e painel

Grave `meta.json` na mesma pasta. É o que alimenta o painel e a régua por tema.

O campo `area` é o que permite medir motor por domínio de conhecimento — um motor pode ser bom em
regulação brasileira e ruim em literatura acadêmica. Use rótulo curto e reutilizável, para que
pesquisas do mesmo domínio caiam no mesmo balde: `energia/regulação`, `varejo`, `infraestrutura`,
`história econômica`, `macroeconomia`. Sem ele, a régua por tema nunca liga.

```json
{
  "data": "AAAA-MM-DD",
  "tema": "título curto da pesquisa",
  "area": "energia/regulação",
  "objetivo": "uma linha, saída da clarificação",
  "hipotese": "a hipótese testada",
  "modo": "normal",
  "criticidade": "media",
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

Regenere o painel e a medição de qualidade:

```bash
python3 ~/.claude/skills/pesquisa/scripts/dashboard.py
python3 ~/.claude/skills/pesquisa/scripts/qualidade.py
```

A segunda linha é o que fecha o ciclo: cada pesquisa concluída realimenta a nota dos motores, então a próxima já é conduzida com a régua atualizada. Sem esse passo, o passo 3b da pesquisa seguinte trabalha com dados velhos.

Feche informando ao Danilo: caminho do relatório, custo real somado de todas as rodadas (campo `custo_real_usd` em cada JSON), quantas afirmações ficaram como fonte única e o que permaneceu sem resolução.

## Comandos do script

| Objetivo | Comando |
|---|---|
| Estimar sem gastar | `--prompt-file X.md --estimar` |
| Rodada 1 | `--prompt-file X.md --saida r1.json --rodada 1` |
| Rodada 2 | `--prompts-file P.json --saida r2.json --rodada 2` |
| Escolher motores | `--motores grok,gpt` |
| Modo | `--modo rapida\|normal\|profunda` |

Configuração dos modelos, preços e modos: `config.json`. Trocar de motor é trocar a string `modelo`.

Chave: lida de `OPENROUTER_API_KEY` no ambiente, ou de `~/.claude/.env`. Nunca imprima a chave, nunca a copie para dentro de um projeto.

## Quando algo dá errado

**Agente com zero URL.** Não é bug do script, é o modelo respondendo de memória. Ele não conta como fonte. Se for recorrente no mesmo slot, verifique se `engine_busca` está declarado no `config.json` — sem `engine` explícito, os modelos Google ignoram o plugin de busca em silêncio.

**Resposta truncada (`finish=length`).** Suba o modo, ou o `max_tokens_r1` do modo em uso.

**Texto curto e caro.** O modelo gastou o orçamento em raciocínio interno. Confirme que `reasoning_effort` está como `low` para aquele agente.

**Um agente falhou na rodada 1.** Continue com os dois restantes e registre a falha na seção de limitações. Com um só, pare.

**Modelo não existe mais.** O catálogo do OpenRouter muda rápido. Consulte `https://openrouter.ai/models` e atualize `config.json`, incluindo o bloco `precos_por_milhao_usd`.
