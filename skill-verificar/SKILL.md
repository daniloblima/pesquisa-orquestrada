---
name: verificar
description: Verifica se o material coletado numa pesquisa presta, antes de ele virar relatório. Confere existência e procedência de cada fonte, mede coerência entre os números dos motores, conta origens independentes e devolve no máximo dez perguntas para o Danilo decidir. Não gasta crédito de API e roda sobre pesquisa nova ou antiga. Triggers "verificar", "/verificar", "confere essa pesquisa", "essa coleta presta?".
---

# /verificar — o miolo do sistema

Coletar é commodity. O que separa uma pesquisa boa de um amontoado de links é a pergunta que
esta skill responde: **o que veio presta, e o que dele dá para usar?**

É o erro clássico do pesquisador júnior — sair recolhendo páginas sem perguntar se cada uma
sustenta o que se diz que ela sustenta. Aqui isso é feito em duas camadas, e nenhuma delas
gasta crédito de API.

## Quando roda

Sempre depois de cada rodada da `/pesquisa`, antes de decidir qualquer coisa com o material.
E sozinha, sempre que quiser reverificar uma pesquisa antiga — o que é o ponto de existir
separada: melhorar a régua deixou de exigir comprar pesquisa nova a cada tentativa.

## Camada 1 — mecânica

```bash
python3 ~/.claude/skills/pesquisa/scripts/verificar.py <pasta-da-pesquisa> \
  --rodada 1 --termos "termo1,termo2,termo3" --criticidade media
```

Confere, para cada fonte: se a URL existe, se a forma é de fonte real, se o modelo confessou
tê-la construído, se a página trata do assunto, e qual trecho do texto ela sustentava.

E duas medidas sobre o conjunto, que nenhuma fonte isolada revela:

**Coerência** — o mesmo número aparecendo com valores diferentes entre motores, unidade
incompatível para a mesma grandeza. É o sinal de erro mais barato que existe e não exige ser
especialista no assunto: quando um motor diz 9 pontos percentuais e outro diz 13,5 sobre o mesmo
estudo, alguém leu a versão errada.

**Independência** — quantos domínios distintos sustentam o material e quantos foram citados por
mais de um motor. Três motores apontando para o mesmo domínio são uma fonte, e não três.

Grava `r1_verificacao.json` e `r1_decisoes.md`.

Sobre `--termos`: passe a raiz curta, nunca a forma derivada, e cubra o vocabulário que a fonte
usaria sem cair na palavra que serve para tudo. Detalhe em `references/termos.md`.

## Camada 2 — parecer independente

Sempre, nas duas rodadas, salvo pedido explícito do Danilo para pular numa pesquisa leve.

Lance um subagente com a instrução de `references/prompt-parecer.md`. Ele recebe os markdowns
brutos dos motores e a pergunta original, **sem ver a sua análise**, e devolve o que considera
sustentado, o que é fonte única e o que cheira a resposta de memória.

O ganho não é dividir trabalho, é isolar contexto: quem coletou não é bom juiz do que coletou.
Quatro auditorias independentes em 12 e 13/08/2026 derrubaram, cada uma, algo que quem escreveu
o código tinha declarado testado.

Onde o parecer divergir da sua leitura, a divergência vira item de decisão. Não escolha sozinho.

## Os cinco gatilhos que param para perguntar

Não são sugestões. Se qualquer um disparar, o Danilo é chamado antes de seguir.

1. **Afirmação negativa que importa.** Nunca escreva que algo não existe. Escreva que não foi
   localizado, diga onde procurou e peça a conferência na fonte primária. Ausência de evidência
   não é evidência de ausência, e em 04/08/2026 os três motores afirmaram que nenhum dispositivo
   impunha teto de 75 kW — o art. 23, § 6º da REN ANEEL 1.000/2021 diz exatamente isso.
2. **Consenso com origem única.** Vários motores, um domínio só.
3. **Incoerência interna.** Número que não fecha, unidade trocada, valor fora de ordem de
   grandeza.
4. **Divergência de escola.** Quando a contradição é de corrente de pensamento e não de fato,
   pergunte qual corrente interessa ao uso. Não arbitre.
5. **Fonte decisiva atrás de muro.** Paywall, proteção anti-robô, documento que o servidor não
   entrega. Peça o arquivo ao Danilo — ele baixa.

O `r1_decisoes.md` já vem no formato certo: no máximo dez itens, cada um com uma linha de
contexto e uma pergunta fechada. Se não couber em dez minutos de leitura, a triagem falhou e
você deve enxugar antes de mostrar.

## Criticidade

Eixo separado de profundidade. Profundidade governa custo; criticidade governa rigor.

| Criticidade | Origens para consenso | Gatilhos | Fonte primária |
|---|---|---|---|
| baixa | 1 | só marcam o relatório | opcional |
| média | 2 | marcam e listam | recomendada |
| alta | 2 | **param o fluxo** | obrigatória em afirmação negativa |

## O que esta skill nunca faz

Não gasta crédito de API. Não reescreve o material coletado. Não decide o que entra no
relatório — ela informa, e quem decide é a `/pesquisa` com o Danilo.
