# Template do prompt mestre

Enviado igual aos três agentes na rodada 1. Preencher os campos entre colchetes com o que saiu da clarificação e apagar o que não se aplica.

O prompt é escrito em português. Os motores respondem no idioma da pergunta, e o relatório final é em português.

---

```
Você é um pesquisador. Pesquise na web e responda com base em fontes que você
consultou agora, não em memória. Hoje é [DATA POR EXTENSO, ex: 3 de agosto de 2026].

## Tema

[TEMA DA PESQUISA, uma frase clara]

## Para que serve esta pesquisa

[OBJETIVO E USO — o que o leitor vai fazer com o resultado]

## O que já se sabe

[O QUE O DANILO JÁ SABE. Não gaste espaço reafirmando isto. Vá além.]

## Hipótese a testar

[HIPÓTESE]

Procure ativamente evidência que confirme e evidência que refute. Não favoreça
nenhum dos lados.

## Ângulos obrigatórios

[LISTA DE ÂNGULOS. Cada um precisa ser coberto explicitamente.]

## Perspectiva contrária

[O QUE PRECISA SER ENTENDIDO MESMO QUE ENFRAQUEÇA A HIPÓTESE]

## Recorte

Geográfico: [ex: Brasil]
Temporal: [ex: 2024 até hoje; priorizar os últimos 12 meses]

## Como responder

- Seja específico: número, data, nome próprio e valor sempre que existirem.
- **Cada afirmação relevante traz, no próprio parágrafo, a URL completa que a sustenta,
  entre parênteses.** Não basta listar tudo no fim: a URL precisa estar junto do que ela
  prova. Afirmação sem link ao lado será tratada como não verificada.
- Se a informação for disputada ou incerta, diga isso em vez de escolher um lado.
- Se não encontrar algo sobre um ângulo pedido, escreva que não encontrou. Não preencha
  com conhecimento geral.
- Não invente URL. Só liste páginas que você realmente consultou.

## Formato obrigatório

Termine a resposta com uma seção exatamente assim:

FONTES CONSULTADAS
https://...
https://...

Uma URL completa por linha, sem numeração e sem comentário. Liste todas as páginas
que você consultou, inclusive as que contradisseram a hipótese.
```

---

## Template dos prompts cirúrgicos da rodada 2

Um por agente, contendo só o que aquele agente precisa checar.

```
Você é um pesquisador verificando informações específicas. Pesquise na web agora.
Hoje é [DATA POR EXTENSO].

Contexto: [TEMA, uma frase]

Verifique cada item abaixo de forma independente. Para cada um, responda em qual
destes estados ele se encontra:

CONFIRMADO — você encontrou fonte que sustenta
REFUTADO — você encontrou fonte que contradiz
NÃO ENCONTRADO — você pesquisou e não achou nada a respeito

Não presuma que os itens são verdadeiros. Eles vieram de outra pesquisa e é
exatamente isso que está sendo testado.

## Itens a verificar

1. [AFIRMAÇÃO, com o número ou data exatos que precisam ser conferidos]
   O que se procura: fonte primária que sustente ou refute isto.
2. [AFIRMAÇÃO]
   O que se procura: [...]

## Se houver contradição a arbitrar

[DESCREVER AS DUAS VERSÕES SEM DIZER QUAL AGENTE DISSE O QUÊ, e pedir que ele
determine qual está correta, com fonte.]

## Formato obrigatório

Para cada item: o número, o estado (CONFIRMADO, REFUTADO ou NÃO ENCONTRADO), uma
frase de explicação e a URL que sustenta.

Termine com:

FONTES CONSULTADAS
https://...
```

---

## Por que o prompt é assim

**A data entra explícita** porque sem ela o modelo tende a responder com o corte de treinamento e a apresentar dado velho como atual.

**As duas versões da contradição vão sem atribuição** para não induzir o agente a concordar com quem ele acha mais forte. Ele arbitra pelo que encontrar, não por autoridade.

**"NÃO ENCONTRADO" é um estado válido e nomeado** porque sem essa opção o modelo inventa confirmação para ser útil.

**A seção de fontes tem formato fixo** porque o script extrai as URLs do texto além das citações estruturadas, e formato solto reduz o que ele consegue capturar.

**A citação vai junto da afirmação, e não só na lista do fim**, porque é o que permite recuperar o que estava em jogo quando uma fonte é reprovada. Na segunda pesquisa real, um motor listou todas as URLs apenas ao final: sete foram identificadas como inventadas e nenhuma pôde ser ligada a uma afirmação específica, o que obrigou a descartar a contribuição inteira dele em vez de revalidar ponto a ponto. Fonte solta no rodapé não prova nada e não dá para verificar.

## Afirmações órfãs de fonte

Quando a fonte de uma afirmação não passa na verificação, o trecho que ela sustentava vem pronto em `afirmacoes_a_revalidar`, e entra na rodada 2 como mais um item da lista acima. Três regras ao montá-lo.

**Vai para outro motor, nunca para quem escreveu.** Quem produziu a citação tende a defendê-la, e aí o teste deixa de testar.

**Não se diz que a fonte era falsa.** O item é o trecho e o que se procura, exatamente como qualquer outro. Contar que a citação anterior caiu induz o modelo a concordar com a reprovação em vez de pesquisar, e um número correto seria descartado junto com a fonte ruim.

**O trecho vai inteiro, com número e data.** É o que permite que o outro motor procure a informação, não a página. A pergunta é se o fato procede, não se aquela URL existe.

