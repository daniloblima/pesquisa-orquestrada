---
name: qualidade
description: Mede o desempenho dos motores de pesquisa a partir das pesquisas já feitas, por tema, e mantém a memória da própria skill. Informa a escolha de composição, nunca decide sozinha. Roda no fim de uma pesquisa ou isolada, e não gasta crédito. Triggers "qualidade", "/qualidade", "como estão os motores", "qual motor usar para".
---

# /qualidade — a memória da skill sobre si mesma

Mede quanto cada motor acerta, em que tema, e a que custo. É dado da ferramenta: sem a skill,
não significa nada, e por isso não vai para o brain do Danilo.

## Quando roda

No fim de uma pesquisa, depois do relatório pronto, porque é aí que existem as duas naturezas de
informação que a medição precisa. E isolada, quando a pergunta for qual motor usar.

## O que mede

```bash
python3 ~/.claude/skills/pesquisa/scripts/qualidade.py
python3 ~/.claude/skills/pesquisa/scripts/dashboard.py    # painel, abre com duplo clique
```

Três medidas por motor, comparadas com os limiares do `config.json`:

**Precisão de fonte** — quantas URLs passaram na verificação. Só falha dura conta: URL
inexistente, inventada, suspeita ou removida. "Fora do tema" e "inconclusiva" medem a conferência
e não a citação, e contá-las derrubava a nota de todos os motores por erro nosso.

**Taxa de confirmação** — quanto do que o motor trouxe sobreviveu à validação cruzada.

**Confiabilidade operacional** — falha total pesa 1, truncamento pesa 0,5.

## Por tema, quando houver massa

Um motor pode ser bom em regulação brasileira e ruim em literatura acadêmica. A régua global
mistura os dois, então cada pesquisa grava o campo `area` no `meta.json` — "energia/regulação",
"varejo", "infraestrutura", "história econômica" — e o relatório por tema aparece a partir de
três pesquisas naquele tema. Antes disso, reportar por tema trocaria uma régua imprecisa por
várias.

## A parte qualitativa, que o número não pega

Depois de redigir o relatório, registre no `meta.json` o que só quem escreveu sabe: quantas
afirmações do texto final vieram de cada motor, qual deles trouxe o achado que organizou a peça,
e qual errou em quê. Um motor pode ter 98% de precisão de URL e não ter contribuído com nada
aproveitável — a diferença entre citar bem e servir.

## Informa, nunca decide

A composição padrão do `config.json` só muda por decisão do Danilo, registrada, com no mínimo
duas medições. Em 12/08/2026 ela mudou duas vezes em um dia, as duas por número que estava
errado, e uma delas tirou do padrão o motor com a melhor precisão da série.

Quando a `/pesquisa` consultar esta skill na clarificação, o resultado é sugestão de composição
para o tema. A escolha continua sendo dele.

## Quebra de série

A régua mudou em 12/08/2026: antes, falso positivo de conferência e falha de rede do próprio
verificador entravam como erro de citação. Nota anterior e nota posterior medem coisas
diferentes e não se comparam. O script marca isso sozinho — se a comparação de índice atravessar
essa data, ela fala da régua e não do motor.
