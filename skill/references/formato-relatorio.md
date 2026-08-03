# Formato do relatório final

Documento que o Danilo vai ler e usar, muitas vezes carregando em NotebookLM ou anexando a um material de cliente. Precisa se sustentar sozinho, sem a conversa que o gerou.

Vale o perfil de voz: português correto, sem emoji, sem negrito decorativo, sem vírgula antes de "e" ou "ou" em adição simples, sem a estrutura "não é X, é Y".

---

## Estrutura

```markdown
# [Tema da pesquisa]

Data: [AAAA-MM-DD HH:MM]
Objetivo: [para que serve, uma linha]
Motores: Perplexity Deep Research · GPT-5.6 Terra · Gemini 3.1 Pro
Rodadas: 2 · Fontes consultadas: [N] · Custo: US$ [X,XX]

---

## Sumário executivo

[Três a cinco parágrafos que respondem diretamente o objetivo e a hipótese da
clarificação. Se a hipótese se confirmou, dizer. Se não, dizer. Se ficou
indeterminada, dizer por quê.

Este bloco precisa bastar para quem não vai ler o resto. Sem rodeio de abertura,
sem recapitular a pergunta antes de responder.]

---

## Achados

### [Ângulo ou tema]

[Informação confirmada por dois ou mais motores é apresentada como fato, direto,
sem ressalva e sem citar quantos confirmaram.

Informação de um motor só leva o marcador literal ao fim da frase (fonte única — verificar).

Número, data e nome próprio sempre que existirem. Evitar adjetivo sem dado:
"crescimento expressivo" vira o número.]

### [Próximo ângulo]

...

---

## Divergências

[Só existe se houver. Uma subseção por divergência.]

### [Ponto em disputa]

Versões encontradas: [as duas ou três leituras, sem nomear qual motor disse o quê]
Resolução: [o que a rodada 2 determinou, com a fonte que decidiu]

[Se não resolveu, dizer que permanece em aberto e qual seria o caminho para fechar.]

---

## Limitações

[Obrigatória sempre que qualquer uma destas ocorrer:

- algum motor falhou ou respondeu sem fontes
- algum ângulo pedido não foi coberto por nenhum motor
- as fontes se concentram em poucos veículos ou num único período
- a hipótese não pôde ser testada com o material encontrado

Se nada disso aconteceu, escrever "Nenhuma limitação relevante identificada".
Nunca omitir a seção.]

---

## Referências

### Confirmadas por mais de uma fonte

- [URL] — [o que sustenta, meia linha]

### Fonte única

- [URL] — [o que sustenta] — verificar antes de usar

### Demais páginas consultadas

- [URL]
```

---

## Critérios de qualidade

**O sumário responde a pergunta.** Se o Danilo precisa ler os achados para saber a resposta, o sumário falhou.

**Toda URL aparece.** As três listas somadas contêm cada URL de cada agente das duas rodadas, sem exceção. Repetida entre agentes, aparece uma vez, na categoria mais alta a que faz jus.

**O marcador de fonte única é literal.** Escrito `(fonte única — verificar)`, sempre igual, para dar para varrer o documento buscando o que ainda não está firme.

**Duas citações da mesma matéria não são duas fontes.** Antes de classificar como confirmado, compare as URLs. Motores diferentes lendo o mesmo release são uma fonte só.

**Não relatar processo.** O relatório traz o que se descobriu, não a narrativa de como a pesquisa correu. O que aconteceu de errado no caminho vai em Limitações, em uma linha objetiva.

**Contradição não some.** Se dois motores discordam e a rodada 2 não decidiu, isso vira seção própria. Escolher silenciosamente um lado é o pior desfecho possível para este produto.
