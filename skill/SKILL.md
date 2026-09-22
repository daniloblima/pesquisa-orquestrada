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

   **A quinta camada pergunta se a fonte sustenta o número, e não só se ela existe.** As quatro primeiras respondem "esta página existe e fala do assunto?". Desde 21/08/2026, quando a afirmação colada numa fonte traz número que discrimina — com casa decimal, ou de três dígitos para cima — a conferência procura esse número na página. Nenhum encontrado, o estado é `número não localizado`, que é **sinal fraco**: manda revalidar, nunca desqualifica.

   **O caso de estreia dessa camada era um falso positivo, e a correção ensina o que ela mede.** Em 21/08/2026 ela acusou o `noxhash.com` de sustentar oito números da espinha de depreciação — 92,5%, 86,7%, 87,5%, 96,3% e outros — que não estão escritos na página, e isso ficou registrado aqui, no `ESTADO.md` e no `BACKLOG.md` como prova de que a camada funcionava. Em 22/09/2026 a página foi aberta e lida. Ela traz uma tabela com os valores em dólar por terahash, por geração — S19 de ~US$ 80 para ~US$ 10 e depois US$ 3–6 —, e os seis percentuais fecham na aritmética sobre essa tabela, até a casa decimal. O texto do motor abre com "Convertendo esses exemplos em perdas aproximadas", ou seja, ele declarou a conta. A fonte sustentava a afirmação, por derivação anunciada.

   Desde então, afirmação que anuncia a própria conta não é cobrada da fonte: o `conferir_numeros` marca o item como `derivado` e o sinal não dispara. A frase sobre faixas arredondadas existe na página — "Flagships lose 50–70% of their value in the first 18 months" — e fala de outra coisa, a perda nos primeiros 18 meses, não a série por geração.

   **O que essa camada não faz.** Confere número, não sentido: afirmação sem número não é avaliável, e na pesquisa de estreia só 16 das 47 URLs com contexto tinham número conferível. Quem julga sentido é a sexta camada, descrita abaixo. Fonte de conteúdo volátil — canal de Telegram, cotação ao vivo, listagem que muda por hora — dá falso positivo por natureza, e um canal do Telegram foi o segundo sinal da estreia. Número em imagem ou tabela montada por JavaScript não é lido. Por tudo isso é sinal fraco, e o veredito é seu.

   **Número escrito dentro de uma URL nunca foi afirmado por ninguém.** A URL colada ao lado da afirmação sai do texto antes da extração desde 22/09/2026. Sem isso, `migalhas.com.br/depeso/427640/` cobrava da página o número 427640, `legisweb.com.br/noticia/?id=34071` cobrava 34071, e `idArquivoBinario=53213` fazia a Lei 9.074/1995 no Planalto responder por um número que era identificador de anexo de outro site. Cinco dos sete falsos positivos conferidos naquele dia tinham essa única causa.

   **Número que veio do seu próprio pedido não se cobra da fonte.** "Para um lote de 4.200 unidades" é premissa da pergunta, e cobrá-la das fontes acusou cinco delas antes do desconto entrar.

   **Os estados têm gravidades diferentes, e essa diferença manda.** Falha dura é `inventada` (não existe e nunca esteve no arquivo da internet), `removida` (existiu e saiu do ar, então a informação pode ser real), `inexistente` (404) e `suspeita` (o texto ao lado do link admite que ele foi construído, ou o domínio é encurtador ou hospedagem). Sinal fraco é `fora do tema` (a conferência de assunto não achou os termos), `inconclusiva` (não deu para ler a página, por muro de acesso, documento sem HTML ou falha de rede) `citação imprecisa` (a URL é domínio raiz, sem página específica), `número não localizado` (a página não traz o número que a afirmação atribui a ela), e os dois da sexta camada: `fonte não sustenta` (a página foi lida e não diz o que se atribuiu a ela) e `fonte contradiz` (a página diz o oposto).

2b. **A sexta camada pergunta se a página diz o que disseram que ela diz.** As cinco anteriores medem forma — endereço que existe, domínio plausível, vocabulário presente, número escrito. Nenhuma lê sentido, e por isso a afirmação sem número passava sem julgamento nenhum: na pesquisa de estreia, 31 das 47 URLs com contexto estavam nesse caso.

   Quem julga é o Jev, da TypeSafe, chamado pelo `sustentacao.py`. Ele lê o recorte da página que ancora a afirmação e devolve um de quatro vereditos — sustenta, sustenta em parte, contradiz, não trata — com uma confiança. Acima de 0,80 o veredito vale; abaixo disso entra como aviso de leitura e você decide. Custa cerca de US$ 0,012 numa pesquisa de 109 URLs, contra os US$ 2,38 de média que a pesquisa inteira custa.

   **Ela também substitui a conferência de tema quando está ligada.** A régua de vocabulário conta raiz de palavra e reprova fonte legítima escrita em outro idioma: dos 8 casos marcados como `fora do tema` no histórico, todos os que foram abertos na página eram falso positivo, entre eles a página da FranklinCovey em inglês que traz exatamente a frase que a afirmação traduz, e o texto de Capoche sobre Potosí, em espanhol, que está no `BACKLOG` desde 13/08 pela mesma causa. Quando o julgamento tem convicção, ele manda; quando concorda com a heurística, o sinal fica.

   **Afirmação de ausência não recebe veredito dela.** Em 3 de 7 negações plantadas o modelo respondeu "sustenta", e indireção com dupla negação é limitação publicada do `jev-1.13`. Como a regra dura 8 já manda conferir ausência em fonte primária, "não existe dispositivo", "não há precedente" e "nenhuma norma prevê" saem daqui marcadas para o passo 5b, sem julgamento. Um "sustenta" com confiança 0,99 sobre uma negação viraria autorização, que é o pior erro que este produto pode cometer.

   **Duas rotas para o mesmo modelo, e a segunda não pede nada de novo.** A preferida é a API da TypeSafe, pela `TYPESAFE_API_KEY` em `~/.claude/.env`. Não havendo essa chave, a camada usa o Jev pelo OpenRouter, com a `OPENROUTER_API_KEY` que você já precisa ter para a pesquisa rodar. Mesmo preço nas duas, US$ 0,042 por milhão de tokens de entrada, sem intermediação.

   Uma armadilha ao procurar: o Jev **não aparece em `/api/v1/models` do OpenRouter**, porque devolve decisão e não texto e por isso não cabe no contrato de chat. Ele é servido em `POST /api/alpha/decisions`, e o identificador é `jev-latest` sem prefixo — `typesafe/jev-latest` devolve HTTP 400. Procurar no catálogo de modelos dá zero e não significa ausência.

   **Sem nenhuma das duas chaves, a skill roda igual.** A camada desliga em silêncio e a régua de vocabulário volta a ser a única — nenhuma outra parte muda.

   **Domínio raiz é sinal fraco desde 21/08/2026, e antes era falha dura.** A heurística julga forma, e forma não prova invenção: numa pesquisa sobre valor residual de ASIC, as duas únicas falhas duras da rodada 1 eram `asicminervalue.com` e `hashrateindex.com`, as duas referências centrais do tema, ambas no ar. Quando a fonte é uma plataforma cujo produto é o próprio índice, citar a raiz é a citação correta. Continua indo para a revalidação, que é o tratamento que a imprecisão merece, e deixou de pesar contra o motor.

   Só falha dura pesa contra o motor. Sinal fraco entra no relatório como aviso de leitura e nunca desqualifica agente nem afirmação sozinho: em 12/08/2026, 103 das 161 reprovações acumuladas eram sinal fraco, com falso positivo comprovado em quatro páginas que estavam exatamente no tema.

   **Descartar em silêncio é proibido.** A afirmação pode ser verdadeira com a citação errada, e apagá-la tira do relatório informação boa sem deixar rastro — o leitor nunca fica sabendo que faltou. O script devolve `afirmacoes_a_revalidar`, com o trecho exato que cada fonte reprovada sustentava, e todas entram obrigatoriamente na rodada 2. Só depois se decide: confirmada por fonte que existe, entra normalmente; não confirmada, vai para limitações, nomeada, dizendo o que se tentou verificar e não se conseguiu.

   **Quando o trecho não se localiza, a quarentena é da afirmação e não do agente.** O campo `reprovadas_sem_rastro` diz que alguma fonte com falha dura não pôde ser ligada a nenhum trecho, nem por URL escrita no corpo nem por marcador numerado. Isso põe em dúvida o que se apoiava naquela fonte, e nada além disso. A regra antiga invalidava a contribuição inteira do motor e, em 12/08/2026, jogou fora seis respostas boas do Perplexity, que cita em estilo acadêmico — inclusive vereditos corretos sobre Potosí, Barbegal e a série de tonelagem a vapor, que estavam escritos no sumário.

   Este é o modo de falha mais perigoso do produto. Zero URL é visível. URL presente que aponta para uma página inventada parece verificada e ninguém confere. Já aconteceu: um motor construiu link plausível para um estudo que os outros dois depois declararam inexistente.
3. **Nenhuma URL verificada é descartada.** Toda URL que passou entra nas referências, mesmo sustentando informação fraca. As reprovadas não entram como referência: vão para a seção de limitações, nomeadas, com o motivo.
4. **Fonte única é sempre marcada.** Nunca apresente como fato o que só um motor trouxe. O marcador é literal: `(fonte única — verificar)`.
5. **Nunca inventar confirmação.** Se você não achou a mesma informação em dois agentes, ela não é consenso. Na dúvida, trate como fonte única.
6. **Confirmar o escopo e o custo antes de gastar, nessa ordem.** Nunca dispare a rodada 1 sem que o Danilo tenha aberto o `prompt_mestre.md` e sem mostrar a estimativa depois disso. A estimativa vem como faixa, não como número: o motor de busca profunda cobra por consulta interna e varia com o tema.

   **O prompt se lê no arquivo, nunca no chat.** Ele lê o prompt e não lê os resultados, e é ali que ele confere se todos os ângulos combinados estão cobertos, se entrou algum que ele não quer e se falta alguma coisa. Resumo na tela não serve, porque quem resume pode omitir — foi o que aconteceu em 24/08/2026, quando dois ângulos entraram entre o escopo aprovado e o prompt disparado e a pesquisa inteira pendeu para regulação sem ele saber. O passo 2 abre o arquivo e espera.

   Esta é a única janela em que o escopo ainda pode ser corrigido. Nenhuma das seis camadas de verificação conserta uma pesquisa que perguntou a coisa errada.
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

**A última aba é sempre a escolha dos motores, e ela se monta a partir deste comando:**

```bash
python3 ~/.claude/skills/pesquisa/scripts/qualidade.py --escolha
```

Ele devolve uma linha por motor com id, rótulo, índice de busca, custo típico por rodada, a nota da série inteira, a nota recente, quantas rodadas o motor truncou e o papel medido. **Copie a tabela para a aba, uma opção por linha, e nada além dela.**

Três coisas não se negociam nessa aba, e as três já foram violadas na prática:

- **`multiSelect: true`, com um item por motor.** Nunca combinações prontas em escolha única. Quem decide a composição é o Danilo, e oferecer pacotes fechados tira dele a decisão que a aba existe para fazer.
- **Custo à vista.** Já vem no comando. Em 21/08/2026 ele pediu "ChatGPT e outro motor baratinho" e escolheu o Perplexity, que custa catorze vezes mais que o GPT — a informação existia no `config.json` e não chegou à tela.
- **Nota à vista, junto do custo.** A régua de qualidade é o diferencial do projeto e rodava tarde demais: o `--resumo` é chamado no passo 3b, depois da rodada 1, quando o dinheiro já foi gasto. Mostrar só custo empurraria a escolha para o barato, o que é tão ruim quanto o contrário.

Os marcados com `*` são sugestão de partida, não recomendação sua. Se quiser recomendar, escreva a recomendação **no texto da pergunta**, com a razão, em vez de reduzir as opções.

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

**Pare aqui e abra o arquivo na tela dele. Nada é disparado antes de ele ter lido.**

```bash
open -a "Visual Studio Code" <pasta>/prompt_mestre.md
```

Diga em uma linha o que ele vai encontrar: a lista de ângulos com a marca de origem, sendo
que `[acrescentado por mim]` é o que você deduziu e ele nunca aprovou. Peça que edite no
arquivo — cortar ângulo, acrescentar, mudar recorte, escrever observação — e avise quando
terminar. **Não ofereça revisar no chat.** O fluxo dele é editar no arquivo, e o
`buscar.py` lê o arquivo na hora de disparar, então o que ele deixar escrito é literalmente
o que vai aos motores.

Este passo existe porque em 24/08/2026 o prompt foi montado, gravado e disparado sem que ele
visse o texto final. Dois ângulos entraram entre o escopo que ele aprovou e o que foi
enviado, ambos puxando para regulação, e o `gov.br` respondeu por 64 menções na rodada. Ele
leu isso na verificação e concluiu que a pesquisa tinha saído do alvo, sem nunca ter visto o
que foi perguntado. Ele lê o prompt e não lê os resultados, então esta é a única janela em
que o escopo ainda pode ser corrigido — depois dela, nenhuma das seis camadas de verificação
conserta uma pesquisa que perguntou a coisa errada.

Quando ele terminar, releia o arquivo do disco antes de seguir, porque o que vale é a versão
dele. Tire as marcas `[combinado]` e `[acrescentado por mim]` que tiverem sobrado: elas são
para a leitura dele e não para o motor.

Só então mostre a estimativa. A ordem importa — editar muda o tamanho do prompt, e estimar
antes daria um número sobre um texto que deixou de existir.

Mostre a estimativa antes de gastar:

```bash
python3 ~/.claude/skills/pesquisa/scripts/buscar.py \
  --prompt-file <pasta>/prompt_mestre.md --estimar --modo normal --rodada 1
```

Apresente o valor ao Danilo e espere o aval. Se o modo for `profunda`, avise que o agente A pode levar de 3 a 10 minutos.

O comando devolve quatro números, e os quatro vão para a tela: a faixa desta rodada, a
projeção da pesquisa inteira, o saldo do OpenRouter e o que sobra depois. **O que precisa
caber no saldo é a pesquisa inteira, nunca a rodada que está sendo disparada** — pesquisa
que para entre as duas rodadas por falta de crédito perde o dinheiro da primeira, porque a
validação cruzada só existe depois da segunda.

Quando `cobertura.cobre_pesquisa_inteira` vier `false`, diga isso antes de qualquer outra
coisa e não dispare sem ele decidir. A recarga é em https://openrouter.ai/settings/credits.
O aviso é conservador de propósito: a conta usa o teto, e o gasto real tem ficado perto de
85% dele.

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

Depois dela, a aferição de custo:

```bash
python3 ~/.claude/skills/pesquisa/scripts/qualidade.py --custos
```

Confronta o previsto com o gasto em todas as rodadas já feitas e fecha com o saldo atual.
Não gasta crédito: o endpoint de créditos é leitura. É o que mantém a estimativa honesta,
porque ela é o número em cima do qual o aval de gastar é dado, e o que dispensa manter uma
janela do painel aberta para saber se dá para a próxima.

Feche informando ao Danilo: caminho do relatório, custo real somado de todas as rodadas (campo `custo_real_usd` em cada JSON), **quanto sobrou de saldo e para quantas pesquisas dá**, quantas afirmações ficaram como fonte única e o que permaneceu sem resolução.

## Comandos do script

| Objetivo | Comando |
|---|---|
| Estimar sem gastar, com saldo e projeção das duas rodadas | `--prompt-file X.md --estimar` |
| Rodada 1 | `--prompt-file X.md --saida r1.json --rodada 1` |
| Rodada 2 | `--prompts-file P.json --saida r2.json --rodada 2` |
| Escolher motores | `--motores grok,gpt` |
| Modo | `--modo rapida\|normal\|profunda` |

Aferição de custo e saldo, no `qualidade.py`, sem gastar crédito:

| Objetivo | Comando |
|---|---|
| Previsto contra gasto, rodada a rodada, e saldo atual | `qualidade.py --custos` |

Configuração dos modelos, preços e modos: `config.json`. Trocar de motor é trocar a string `modelo`.

Chave: lida de `OPENROUTER_API_KEY` no ambiente, ou de `~/.claude/.env`. Nunca imprima a chave, nunca a copie para dentro de um projeto.

## Quando algo dá errado

**Agente com zero URL.** Não é bug do script, é o modelo respondendo de memória. Ele não conta como fonte. Se for recorrente no mesmo slot, verifique se `engine_busca` está declarado no `config.json` — sem `engine` explícito, os modelos Google ignoram o plugin de busca em silêncio.

**Resposta truncada (`finish=length`).** Suba o modo, ou o `max_tokens_r1` do modo em uso.

**Texto curto e caro.** O modelo gastou o orçamento em raciocínio interno. Confirme que `reasoning_effort` está como `low` para aquele agente.

**Um agente falhou na rodada 1.** Continue com os dois restantes e registre a falha na seção de limitações. Com um só, pare.

**Modelo não existe mais.** O catálogo do OpenRouter muda rápido. Consulte `https://openrouter.ai/models` e atualize `config.json`, incluindo o bloco `precos_por_milhao_usd`.

## Defeito da skill vai para o BACKLOG

Os contornos acima existem para tocar o trabalho. Quando o problema é da própria skill — o script
erra, uma regra produz falso positivo, uma etapa custa caro sem entregar —, isso se anota e não se
conserta agora.

Onde: `~/Experimentos/pesquisa-orquestrada/BACKLOG.md`

**Nunca editar a skill durante uma sessão de uso.** Conserto feito no meio de uma entrega não é
testado, e o trabalho é o que tem prazo. A sessão de manutenção é outra, e é ela que decide o que
entra.

O formato e os três estados — `observado`, `diagnosticado`, `confirmado` — estão no cabeçalho do
próprio BACKLOG. O que você concluiu sobre a causa entra como `diagnosticado`, nunca como
`confirmado`, a menos que você tenha aberto o código ou o arquivo e conferido ali.
