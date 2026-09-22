#!/usr/bin/env python3
"""
sustentacao.py — a fonte sustenta a afirmação, e não apenas existe e trata do tema.

É a camada que faltava, e o BACKLOG a chamava de "buraco de fundo" desde 12/08/2026. As
quatro primeiras camadas respondem "esta página existe e fala do assunto?"; a quinta
procura o número na página. Nenhuma responde "o que está escrito ali sustenta o que
disseram que ela sustenta?", porque isso exige julgar sentido.

Quem julga é o Jev, da TypeSafe, um modelo que responde pergunta tipada sobre um texto e
devolve valor com probabilidade, sem gerar texto. Medido em 22/09/2026 sobre 47 pares de
afirmação e fonte tirados de doze pesquisas em disco: US$ 0,0085 no total, 13 de 16
corrupções plantadas detectadas com o limiar de 0,80, e nenhum falso alarme nos 8 casos
de controle. Detalhe em `_planejamento/2026.09.22 NOTA - avaliacao do Jev.md`.

Três decisões de desenho, todas com medição atrás:

**Sem chave, nada quebra.** A skill viaja pelo GitHub e quem a instala pode não ter conta
na TypeSafe. Toda função daqui devolve `None` quando a chave falta, e quem chama segue com
a heurística de sempre. Isto nunca vira dependência dura.

**Recorte por âncora discriminante, nunca por densidade de palavra.** Numa lei do setor
elétrico, "energia" e "consumidor" aparecem do começo ao fim e não localizam nada. Na
estreia do teste, a janela caiu 2.658 caracteres antes do art. 16-B da Lei 9.074/1995 e o
modelo respondeu "não trata" com confiança 0,90, acima do limiar de auto-aceite. O recorte
errado produz veredito errado com cara de certeza, então identificador — `16-B`, `15.269`,
`30.000` — pesa oito vezes mais que palavra comum na escolha da fatia.

**Afirmação negativa não se julga aqui.** Em 3 das 7 negações plantadas o modelo respondeu
"sustenta", e indireção com dupla negação é limitação publicada do `jev-1.13`. Como a regra
dura 8 e o gatilho 1 da `/verificar` já mandam conferir ausência em fonte primária, a
afirmação negativa sai daqui marcada para o passo 5b, sem veredito. Um "sustenta" com
confiança 0,99 sobre uma negação viraria autorização, que é o pior erro possível neste
produto.
"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

# Duas rotas para o mesmo modelo, e a segunda é a que não pede nada de novo a quem instala.
#
# O OpenRouter serve o Jev desde 18/09/2026, por um endpoint próprio: como ele devolve
# decisão e não texto, não cabe no contrato `chat/completions` e por isso **não aparece em
# `/api/v1/models`**. Procurar o modelo naquele catálogo dá zero e não significa ausência —
# foi o erro cometido em 22/09/2026 antes de conferir a rota certa.
#
# Medido no mesmo dia: mesmo corpo de requisição, mesma resposta, 406 tokens custando
# US$ 0,000017052, que é exatamente a tabela da TypeSafe sem intermediação. Quem usa a
# skill já tem `OPENROUTER_API_KEY` configurada, porque é ela que faz a pesquisa rodar,
# então esta rota liga a sexta camada sem nenhuma conta nova.
ROTAS = (
    # (nome, endpoint, variável de ambiente, modelo)
    ("typesafe", "https://api.typesafe.ai/v1/systemone", "TYPESAFE_API_KEY", "jev-latest"),
    # O identificador é `jev-latest` nas duas, sem prefixo de provedor. Medido em
    # 22/09/2026: `typesafe/jev-latest` devolve HTTP 400 "does not exist", apesar de ser o
    # nome que a página do modelo sugere; `jev-latest` e `typesafe/jev-1.13` funcionam. O
    # alias sem versão é o que acompanha as próximas.
    ("openrouter", "https://openrouter.ai/api/alpha/decisions", "OPENROUTER_API_KEY",
     "jev-latest"),
)

# O endpoint do OpenRouter está marcado como alpha desde a estreia. Se ele mudar, a rota
# nativa continua valendo e é só configurar a chave da TypeSafe.
API = ROTAS[0][1]
MODELO = ROTAS[0][3]

# Limiar de auto-aceite. Vem do cookbook `citation_check` da TypeSafe e foi conferido nos
# 47 casos em disco: com 0,80, nenhum dos 8 controles deu falso alarme e 13 das 16
# corrupções plantadas foram pegas. Quem mudar este número mede de novo antes.
CONFIANCA_AUTO = 0.80

# Quanto da página vai na pergunta. O doc do Jev avisa que contexto irrelevante degrada a
# resposta, e o limite duro é 32k tokens para o material. 12 mil caracteres ficam perto de
# 4,3 mil tokens, que foi a média medida.
JANELA_CHARS = 12000

# Abaixo disto a página vai inteira: recortar texto curto só tira contexto útil.
PAGINA_CURTA = 30000

_URL_NO_TEXTO = re.compile(r"https?://\S+|www\.\S+")

# Afirmação de ausência, que é o que a regra dura 8 trata: "não existe dispositivo", "não
# há precedente", "nenhuma norma prevê". Não é qualquer negação.
#
# A primeira versão marcava todo "não" e roteou 33 de 73 julgamentos numa pesquisa real,
# medido em 22/09/2026. Entre os marcados estavam "recursos não reembolsáveis", que é termo
# técnico, e "a propriedade intelectual não é automaticamente da EMBRAPII", que qualifica
# em vez de negar existência. Encher o `r_decisoes.md` de item que não precisava existir é
# o modo de falha que a própria /verificar nomeia: "se não couber em dez minutos de
# leitura, a triagem falhou".
_NEGATIVA = re.compile(
    r"\bn[ãa]o\s+(?:h[áa]|existe[mn]?|consta[mn]?|se\s+aplica[mn]?|"
    r"est[áa]\s+previsto|est[ãa]o\s+previstos?|h[áa]via|houve|"
    r"foi\s+(?:localizad|encontrad|identificad)\w*|"
    r"foram\s+(?:localizad|encontrad|identificad)\w*|"
    r"(?:se\s+)?(?:localiz|encontr|identific)\w+)\b"
    r"|\binexist\w+\b"
    r"|\bnenhum[ao]?s?\s+(?:\w+\s+){0,2}(?:norma|lei|dispositivo|artigo|regra|previs\w+|"
    r"precedente|decis\w+|estudo|registro|refer\w+|fonte|vedaç\w+|exig\w+|obrigaç\w+)\b"
    r"|\bausência\s+de\b|\bausencia\s+de\b"
    r"|\bsem\s+(?:previsão|amparo|respaldo|base\s+legal|vedaç\w+|qualquer\s+\w+)\b",
    re.IGNORECASE)


class SemChave(Exception):
    """A TypeSafe não está configurada. Quem chama segue com a heurística."""


_ARQUIVOS_DE_CHAVE = (
    Path.home() / ".claude" / ".env",
    Path.home() / ".config" / "typesafe" / ".env",
    Path.home() / ".config" / "openrouter" / ".env",
)


def _valor(nome):
    """A chave, do ambiente ou dos `.env` conhecidos. Nunca é impressa em lugar nenhum."""
    v = (os.environ.get(nome) or "").strip()
    if v:
        return v
    for caminho in _ARQUIVOS_DE_CHAVE:
        try:
            for linha in caminho.read_text(encoding="utf-8").splitlines():
                if linha.startswith(f"{nome}="):
                    v = linha.split("=", 1)[1].strip().strip("\"'")
                    if v:
                        return v
        except OSError:
            continue
    return None


def rota():
    """A rota a usar, na ordem de preferência. Levanta `SemChave` se nenhuma serve.

    A nativa vem primeiro porque quem configurou a chave da TypeSafe de propósito quer usar
    ela. Quem não configurou cai no OpenRouter, que já está lá para a pesquisa funcionar, e
    a camada liga sozinha sem pedir conta nova.
    """
    for nome, endpoint, var, modelo in ROTAS:
        k = _valor(var)
        if k:
            return {"nome": nome, "endpoint": endpoint, "modelo": modelo, "chave": k}
    raise SemChave(
        "Nem TYPESAFE_API_KEY nem OPENROUTER_API_KEY foram encontradas. A camada de "
        "sustentação fica desligada e o resto da verificação roda igual. Para ligar, basta "
        "uma das duas em ~/.claude/.env, com permissão 600 — e a do OpenRouter você já "
        "precisa ter para a pesquisa rodar.")


def chave():
    return rota()["chave"]


def disponivel():
    """Se a camada pode rodar. Chamar antes de prometer veredito a quem lê o relatório."""
    try:
        rota()
        return True
    except SemChave:
        return False


def rota_em_uso():
    """O nome da rota, para o log e para o relatório dizerem por onde o julgamento passou."""
    try:
        return rota()["nome"]
    except SemChave:
        return None


def e_negativa(afirmacao):
    """A afirmação nega algo, e por isso vai para a fonte primária em vez do modelo."""
    return bool(_NEGATIVA.search(afirmacao or ""))


# ------------------------------------------------------------------ recorte

def _ancoras(afirmacao):
    """O que discrimina uma passagem, separado do que ocorre em qualquer parágrafo."""
    fortes = set()
    for padrao in (r"\b\d{1,3}(?:[.,]\d{3})+\b",      # 15.269, 30.000
                   r"\b\d+[./-]\d+\b",                # 9.074/1995
                   r"\b\d+-[A-Z]\b",                  # 16-B
                   r"\b\d+[.,]\d+\b",                 # 92,5
                   r"\b\d{3,}\b"):                    # 2026
        fortes.update(m.group().lower() for m in re.finditer(padrao, afirmacao))
    for m in re.finditer(r"\b[A-ZÀ-Ý]{2,}\b|(?<![.!?]\s)(?<!^)\b[A-ZÀ-Ý][a-zà-ÿ]{3,}\b",
                         afirmacao):
        fortes.add(m.group().lower())
    fracas = [p.lower() for p in re.findall(r"[A-Za-zÀ-ÿ]{5,}", afirmacao)]
    fracas = [p for p in dict.fromkeys(fracas) if p not in fortes]
    return list(fortes)[:30], fracas[:25]


def janela(texto, afirmacao, alvo=JANELA_CHARS):
    """A fatia da página que mais ancora a afirmação, e onde ela começa."""
    if len(texto) <= max(alvo, PAGINA_CURTA):
        return texto, 0
    fortes, fracas = _ancoras(_URL_NO_TEXTO.sub(" ", afirmacao))
    baixo = texto.lower()
    pontos = []
    for grupo, peso in ((fortes, 8.0), (fracas, 1.0)):
        for p in grupo:
            i = baixo.find(p)
            while i >= 0:
                pontos.append((i, peso))
                i = baixo.find(p, i + 1)
    if not pontos:
        return texto[:alvo], 0
    pontos.sort()
    pos = [p for p, _ in pontos]
    peso = [w for _, w in pontos]
    melhor, melhor_soma, j, acum = 0, -1.0, 0, 0.0
    for i in range(len(pos)):
        while j < len(pos) and pos[j] < pos[i] + alvo:
            acum += peso[j]
            j += 1
        if acum > melhor_soma:
            melhor_soma, melhor = acum, pos[i]
        acum -= peso[i]
    ini = max(0, melhor - alvo // 4)
    return texto[ini:ini + alvo], ini


# ------------------------------------------------------------------ perguntas

def _perguntas(afirmacao, com_tema):
    q = {
        "sustenta": {
            "type": "choice",
            "instructions": (
                "Uma fonte foi citada como prova da AFIRMAÇÃO abaixo. Leia o trecho da "
                "página citada e diga como ele se relaciona com a afirmação.\n\n"
                f"AFIRMAÇÃO: {afirmacao}"),
            "criteria": {
                "sustenta": "O trecho afirma o que a afirmação diz, ou implica diretamente "
                            "que é verdade, com os mesmos valores e o mesmo objeto",
                "sustenta_em_parte": "O trecho trata do mesmo ponto e apoia parte da "
                                     "afirmação, mas os valores, o escopo ou o objeto "
                                     "diferem do que a afirmação declara",
                "contradiz": "O trecho afirma o oposto da afirmação, ou traz valores "
                             "incompatíveis com os dela",
                "nao_trata": "O trecho não aborda o que a afirmação declara, em nenhuma "
                             "direção",
            },
        },
    }
    if com_tema:
        # Substitui a conferência por casamento de raiz de palavra, que reprova fonte
        # legítima em outro idioma. Medido em 22/09/2026: dos 8 casos marcados como "fora
        # do tema" pela heurística, o Jev julgou 8 como tratando do assunto, e cinco como
        # sustentação plena — entre eles a página da FranklinCovey, em inglês, que traz a
        # frase que a afirmação traduz. O caso do texto de Capoche sobre Potosí, em
        # espanhol com termos em inglês, está no BACKLOG desde 13/08 pela mesma causa.
        q["tema"] = {
            "type": "noul",
            "instructions": ("O trecho é de uma página citada como fonte. Ela trata do "
                             "assunto desta afirmação?\n\n"
                             f"AFIRMAÇÃO: {afirmacao}"),
            "criteria": {
                "true": "A página trata do assunto da afirmação, em qualquer idioma, ainda "
                        "que não confirme os valores dela",
                "false": "A página é sobre outro assunto, ou é tela de bloqueio, menu de "
                         "navegação ou casca sem conteúdo",
            },
        }
    return q


def _pedir(state, questions, timeout=60):
    r = rota()
    corpo = json.dumps({"state": state, "model": r["modelo"],
                        "questions": questions}).encode("utf-8")
    cabecalho = {"Authorization": f"Bearer {r['chave']}",
                 "Content-Type": "application/json"}
    if r["nome"] == "openrouter":
        # O OpenRouter pede identificação do chamador para atribuir uso e ranking.
        cabecalho["HTTP-Referer"] = "https://github.com/daniloblima/pesquisa-orquestrada"
        cabecalho["X-Title"] = "pesquisa-orquestrada"
    req = urllib.request.Request(r["endpoint"], data=corpo, headers=cabecalho)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        saida = json.loads(resp.read())
    saida["_rota"] = r["nome"]
    return saida


# ------------------------------------------------------------------ julgamento

def julgar(afirmacao, pagina, com_tema=True):
    """Como a página se relaciona com a afirmação.

    Devolve `None` quando não há chave, quando a página não foi lida ou quando a afirmação
    é negativa — nos três casos quem chama segue com o que já tinha. O dicionário traz
    `estado`, `confianca`, `probabilidades` e, quando pedido, `trata_do_tema`.
    """
    if not afirmacao or not pagina or len(pagina) < 200:
        return None
    if e_negativa(afirmacao):
        return {"estado": "afirmação negativa", "confianca": None,
                "para_fonte_primaria": True,
                "motivo": "afirmação nega algo: o veredito do modelo não se aplica e a "
                          "conferência é no texto oficial, pelo passo 5b"}
    try:
        trecho, deslocamento = janela(pagina, afirmacao)
        r = _pedir(trecho, _perguntas(afirmacao, com_tema))
    except SemChave:
        return None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        # Falha de rede não é veredito. Some em silêncio, como a conferência de tema faz.
        return {"estado": "não julgada", "confianca": None,
                "motivo": f"a camada de sustentação não respondeu: {type(e).__name__}"}

    a = r.get("answers", {})
    s = a.get("sustenta", {})
    saida = {
        "estado": s.get("choice"),
        "confianca": round(s.get("confidence", 0.0), 3),
        "probabilidades": {k: round(v, 3) for k, v in (s.get("probabilities") or {}).items()},
        "auto": s.get("confidence", 0.0) >= CONFIANCA_AUTO,
        "deslocamento": deslocamento,
        "chars_julgados": len(trecho),
        "tokens": (r.get("usage") or {}).get("input_tokens"),
        "modelo": r.get("model"),
        "rota": r.get("_rota"),
    }
    # O OpenRouter devolve o custo medido da chamada; a rota nativa não devolve, e ali o
    # custo se deriva dos tokens. Ter o número reportado evita estimar o que já foi medido.
    custo = (r.get("usage") or {}).get("cost")
    if custo is not None:
        saida["custo_usd"] = custo
    if "tema" in a:
        saida["trata_do_tema"] = round(a["tema"].get("noul", 0.0), 3)
    return saida


def mesma_grandeza(trecho_a, trecho_b, valor_a, valor_b, unidade):
    """Os dois trechos atribuem valores diferentes à mesma grandeza sobre o mesmo objeto?

    A heurística de coerência acha pares por unidade igual mais vocabulário compartilhado, e
    vocabulário não identifica objeto. Medido em 22/09/2026 sobre as pesquisas em disco: na
    de tributação, as 8 divergências apontadas eram 8 falsos positivos — os motores
    concordavam que o IRPJ sobre venda de mercadoria presume 8%, a CSLL 12% e serviços em
    geral 32%, e o detector comparava esses percentuais entre si como se fossem o mesmo
    número medido duas vezes. Na de valor residual de ASIC, comparava a queda do S19 com a
    do S19j Pro, em datas diferentes.

    Devolve `None` sem chave, e aí quem chama mantém o par como candidato — que é o
    comportamento de sempre.
    """
    if not trecho_a or not trecho_b:
        return None
    state = {
        "trecho_A": trecho_a,
        "valor_A": f"{valor_a} {unidade}",
        "trecho_B": trecho_b,
        "valor_B": f"{valor_b} {unidade}",
    }
    perguntas = {
        "mesma": {
            "type": "noul",
            "instructions": (
                "Dois trechos de pesquisas diferentes citam um número na mesma unidade. "
                "Eles estão medindo a MESMA grandeza sobre o MESMO objeto, no mesmo "
                "recorte de tempo e de escopo? Responda sobre o que cada trecho mede, não "
                "sobre os números serem parecidos."),
            "criteria": {
                "true": "Os dois medem a mesma coisa sobre o mesmo objeto, então valores "
                        "diferentes seriam uma contradição real entre as fontes",
                "false": "Medem coisas diferentes, ou a mesma coisa sobre objetos, "
                         "tributos, categorias, períodos ou escopos distintos, e por isso "
                         "valores diferentes são esperados e não se contradizem",
            },
        },
    }
    try:
        r = _pedir(state, perguntas, timeout=40)
    except SemChave:
        return None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    return round((r.get("answers", {}).get("mesma") or {}).get("noul", 0.0), 3)


def motivo_legivel(j):
    """A linha que entra em `motivos`, escrita para quem lê o r_decisoes.md."""
    if not j:
        return None
    if j.get("para_fonte_primaria"):
        return j["motivo"]
    if j["estado"] == "não julgada":
        return j["motivo"]
    rotulo = {
        "sustenta": "a página sustenta a afirmação",
        "sustenta_em_parte": "a página apoia parte da afirmação, com divergência de valor, "
                             "escopo ou objeto",
        "contradiz": "a página contradiz a afirmação",
        "nao_trata": "a página não trata do que a afirmação declara",
    }.get(j["estado"], j["estado"])
    certeza = "" if j.get("auto") else " (confiança baixa, confira você mesmo)"
    return f"{rotulo}, confiança {j['confianca']:.2f}{certeza}"
