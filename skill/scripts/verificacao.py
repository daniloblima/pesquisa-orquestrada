#!/usr/bin/env python3
"""
verificacao.py — decide se a fonte que um motor devolveu vale alguma coisa.

Separado de buscar.py em 13/08/2026. O motivo é operacional: enquanto coleta e
verificação moravam na mesma execução, melhorar a régua exigia pagar uma pesquisa nova
a cada tentativa. Aqui a verificação roda sobre material já em disco, quantas vezes for
preciso, sem custo.

Nada neste arquivo chama API paga. Ele lê texto e visita páginas públicas.

As quatro camadas, em ordem de gravidade do que detectam:
  1. a URL existe, e o domínio resolve
  2. a forma é de fonte real, e o modelo não confessou ter construído o link
  3. a página trata do assunto da pesquisa
  4. o trecho que a fonte sustentava foi localizado no texto do motor

E duas medidas que não são sobre a fonte isolada, e sim sobre o conjunto:
  5. coerência interna — números que não fecham entre si
  6. independência — quantas origens distintas sustentam a mesma afirmação
"""

import concurrent.futures
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import html
import urllib.request
from datetime import datetime
from urllib.parse import urlparse


def log(etapa, mensagem):
    """Substituível: buscar.py e verificar.py injetam o log com arquivo."""
    print(f"[{datetime.now():%H:%M:%S}] [{etapa}] {mensagem}", flush=True)


# Hospedagem, encurtadores e agregadores que não são fonte de nada quando aparecem
# como domínio raiz numa lista de "páginas consultadas".
DOMINIOS_NAO_FONTE = (
    "github.io", "netlify.app", "vercel.app", "herokuapp.com", "firebaseapp.com",
    "wordpress.com", "blogspot.com", "medium.com", "wixsite.com", "weebly.com",
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "lnkd.in", "example.com",
)

# O archive.org limita requisições com agressividade. Acima disto a checagem passa a
# devolver 429, que não conclui nada. As primeiras já bastam para revelar o padrão.
LIMITE_ARQUIVO = 12

# Teto de páginas baixadas por agente para a conferência de tema.
LIMITE_TEMA = 40

# Quanto se baixa de cada página. Eram 120 KB, e isso reprovava fonte boa por leitura
# curta: o artigo do IMF sobre 167 anos de dados de energia tem 622 KB de HTML, com
# "consumption" e "income" começando depois do caractere 14.900 do texto limpo — fora do
# alcance antigo. Página maior que isto é rara e a leitura acontece em paralelo.
BYTES_POR_PAGINA = 1_500_000

# Acima disto, uma menção só não sustenta que a página trate do assunto.
TEXTO_LONGO = 30_000

# O modelo às vezes confessa a invenção no próprio texto, ao lado do link.
MARCADORES_SUBSTITUICAO = (
    "substitu", "aproximad", "ilustrativ", "exemplo de url", "url fictícia",
    "não foi possível recuperar", "link genérico", "placeholder", "hipotétic",
)

# Gravidade do estado de verificação, medida em 12/08/2026 sobre sete pesquisas.
#
# Antes desta separação, quarentena, alerta e índice de qualidade liam o mesmo balde de
# `urls_problematicas` e tratavam tudo como prova contra o motor. Das 161 reprovações do
# histórico, 103 eram "fora do tema" ou "inconclusiva" — a primeira com falso positivo
# comprovado, a segunda sendo falha de rede do próprio verificador. Com isso um motor
# perdia a contribuição inteira e a nota dele caía por erro nosso.
#
# Só o que está em FALHAS_DURAS é indício de que a fonte foi construída ou não existe.
FALHAS_DURAS = ("inexistente", "inventada", "suspeita", "removida")

# Sinal para leitura humana. Entra no relatório, e vai para a revalidação sempre que
# houver trecho, como qualquer outro estado reprovado. O que muda é o peso: sinal fraco
# nunca invalida agente nem conta como erro de citação no índice de qualidade.
SINAIS_FRACOS = ("fora do tema", "inconclusiva", "citação imprecisa")

# Motivos de forma que dizem que a citação é imprecisa, e não que a página não existe.
# Rebaixados de falha dura para sinal fraco em 21/08/2026: numa pesquisa sobre valor
# residual de ASIC, as duas únicas falhas duras da rodada 1 eram asicminervalue.com e
# hashrateindex.com, ambas raiz, ambas existentes e ambas as referências centrais do
# tema. Quando a fonte é uma plataforma cujo produto é o próprio índice, citar a raiz é
# a citação correta. A heurística julga forma, e forma não prova invenção — imprecisão
# de citação já tem tratamento próprio, que é a revalidação.
MOTIVOS_FRACOS_DE_FORMA = ("domínio raiz, sem página específica",)


def duras(problemas):
    """As reprovações que pesam contra o motor, separadas do que é só sinal."""
    return {u: r for u, r in problemas.items() if r.get("estado") in FALHAS_DURAS}


def classificar_url(url, texto):
    """Marca a URL como suspeita antes mesmo de ir à rede, pela forma e pelo contexto."""
    motivos = []
    try:
        p = urlparse(url)
    except Exception:
        return ["url malformada"]

    host = (p.netloc or "").lower().removeprefix("www.")
    caminho = (p.path or "").strip("/")

    # Fonte real tem caminho. Domínio raiz numa lista de fontes não sustenta afirmação.
    if not caminho:
        motivos.append("domínio raiz, sem página específica")
    if any(host.endswith(d) or host == d for d in DOMINIOS_NAO_FONTE) and len(caminho) < 2:
        motivos.append("domínio de hospedagem ou encurtador")

    # O modelo às vezes admite, ao lado do link, que o construiu. A janela precisa ser
    # curta e travada na quebra de linha: uma confissão numa linha não contamina o link
    # legítimo da linha seguinte.
    pos = texto.find(url)
    if pos >= 0:
        inicio = max(texto.rfind("\n", 0, pos), texto.rfind(". ", 0, pos), pos - 150)
        janela = texto[max(0, inicio): pos].lower()
        for m in MARCADORES_SUBSTITUICAO:
            if m in janela:
                motivos.append(f'o texto imediatamente antes do link admite que ele foi construído ("{m}")')
                break
    return motivos


def verificar_urls(urls, texto, slot, verificar_rede=True):
    """Confere se cada URL existe de fato.

    URL ausente é o caso benigno: dá para notar. URL presente sustentando conteúdo
    inventado é o caso grave, porque parece verificada e ninguém confere. Esta função
    existe só para esse caso.
    """
    if not urls:
        return {}

    achados = {}
    for u in urls:
        motivos = classificar_url(u, texto)
        if motivos:
            duro = any(m not in MOTIVOS_FRACOS_DE_FORMA for m in motivos)
            achados[u] = {"estado": "suspeita" if duro else "citação imprecisa",
                          "motivos": motivos}

    if not verificar_rede:
        return achados

    log(f"AGENTE {slot}", f"verificando existência de {len(urls)} URLs")

    def checar(u):
        req = urllib.request.Request(
            u, method="HEAD",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return u, r.status, None
        except urllib.error.HTTPError as e:
            # Alguns servidores recusam HEAD mas respondem GET.
            if e.code in (403, 405, 501):
                try:
                    req2 = urllib.request.Request(
                        u, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
                    )
                    with urllib.request.urlopen(req2, timeout=15) as r2:
                        return u, r2.status, None
                except urllib.error.HTTPError as e2:
                    return u, e2.code, None
                except Exception as e2:
                    return u, None, f"{type(e2).__name__}: {e2}"
            return u, e.code, None
        except Exception as e:
            return u, None, f"{type(e).__name__}: {e}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        for u, status, erro in ex.map(checar, list(urls)):
            reg = achados.setdefault(u, {"estado": "ok", "motivos": []})
            reg["http"] = status

            if status in (404, 410):
                reg["estado"] = "inexistente"
                reg["motivos"].append(f"HTTP {status} — a página não existe")
            elif erro and ("NameResolution" in erro or "getaddrinfo" in erro or "nodename" in erro):
                reg["estado"] = "inexistente"
                reg["motivos"].append("o domínio não resolve")
            elif status and 200 <= status < 400:
                # Responder 200 não lava acusação de forma. O domínio raiz responde bem
                # e continua sendo citação imprecisa; a confissão de link construído
                # continua sendo suspeita. Quem chegou aqui sem acusação já está "ok".
                pass
            elif erro:
                reg["motivos"].append(f"não deu para verificar: {erro[:90]}")
                if reg["estado"] == "ok":
                    reg["estado"] = "inconclusiva"

    # Para o que não resolveu, o arquivo da internet separa dois casos que a resposta
    # HTTP confunde: página que existiu e saiu do ar, contra URL que nunca existiu.
    # Só a segunda é indício de invenção. Critério emprestado da literatura de
    # verificação de citações (arXiv 2604.03173, 2605.06635).
    mortas = [u for u, r in achados.items() if r["estado"] == "inexistente"][:LIMITE_ARQUIVO]
    if mortas:
        log(f"AGENTE {slot}", f"consultando o arquivo da internet para {len(mortas)} URLs que não resolveram")

        # Sequencial e com pausa: o archive.org devolve 429 rapidamente sob paralelismo,
        # e 429 não distingue nada — só desperdiça a checagem.
        for i, u in enumerate(mortas):
            if i:
                time.sleep(1.2)
            try:
                api = "https://archive.org/wayback/available?url=" + urllib.parse.quote(u, safe="")
                with urllib.request.urlopen(api, timeout=25) as r:
                    d = json.loads(r.read().decode("utf-8"))
                arquivada = bool((d.get("archived_snapshots") or {}).get("closest"))
            except Exception as e:
                log(f"AGENTE {slot}", f"arquivo não respondeu para {u[:50]}: {type(e).__name__} — sem conclusão")
                continue

            if arquivada:
                achados[u]["motivos"].append("existiu e saiu do ar — há registro no arquivo da internet")
                achados[u]["estado"] = "removida"
            else:
                achados[u]["motivos"].append("nenhum registro no arquivo da internet — provavelmente nunca existiu")
                achados[u]["estado"] = "inventada"

    graves = [u for u, r in achados.items() if r["estado"] in FALHAS_DURAS]
    if graves:
        log(f"AGENTE {slot}", f"ALERTA: {len(graves)} URLs inexistentes ou suspeitas")
        for u in graves[:6]:
            log(f"AGENTE {slot}", f"  {achados[u]['estado']}: {u[:80]} — {'; '.join(achados[u]['motivos'][:2])}")
    return {u: r for u, r in achados.items() if r["estado"] != "ok"}


# Cabeçalhos da lista de fontes no fim da resposta. URL que aparece só ali não tem
# afirmação colada nela, e o contexto precisa ser procurado de outro jeito.
CABECALHOS_FONTES = ("fontes consultadas", "fontes:", "referências", "referencias", "sources",
                     "bibliografia", "links consultados", "fontes utilizadas",
                     "fontes", "referências bibliográficas", "works cited")

# Fim de frase, incluindo o ponto colado num marcador de citação. Sem o `.[`, o estilo
# acadêmico (`...CE.[1][2][4]`) não tem fronteira nenhuma para o recorte de trecho.
FIM_DE_FRASE = re.compile(r"[.!?](?=[\s\[])|\.\n")


def contexto_da_url(url, texto, janela=700, citacoes=None):
    """Devolve o trecho onde a URL é usada como prova.

    Uma fonte reprovada não pode simplesmente sumir: a afirmação que ela sustentava pode
    ser verdadeira, com a citação errada. Sem recuperar o trecho, o descarte apaga
    informação boa em silêncio e ninguém fica sabendo.

    Há duas formas de citar, e as duas precisam ser lidas. A URL escrita ao lado da
    afirmação se acha por busca literal. O marcador numerado em estilo acadêmico, `[7]`,
    se resolve pela lista ordenada de citações. Sem a segunda, motor que cita como artigo
    aparece como se não tivesse citado nada, e perde a contribuição inteira.
    """
    literal = _contexto_literal(url, texto, janela)
    if literal:
        return literal
    # Janela menor no caminho por marcador: ali o parágrafo costuma ser uma linha só, e a
    # janela larga devolvia meio sumário para cada citação.
    return _contexto_por_marcador(url, texto, citacoes, janela=350)


def mencoes_de_fonte(texto, urls, citacoes=None):
    """Quantas vezes cada URL é usada como prova, e não apenas exibida numa lista.

    Contar URL distinta esconde concentração. Em 21/08/2026, `noxhash.com` aparecia como
    uma URL em cada motor e parecia uma fonte entre trinta; contando as vezes em que é
    invocada, responde por 23% das provas do Perplexity e sustentava a espinha numérica
    inteira da pesquisa. As duas formas de citar contam, como em `contexto_da_url`: o
    endereço escrito ao lado da afirmação e o marcador numerado do estilo acadêmico.
    """
    conta = {}
    for u in urls or ():
        n, pos = 0, texto.find(u)
        while pos >= 0:
            if not _e_linha_de_lista(texto, pos):
                n += 1
            pos = texto.find(u, pos + 1)
        if n:
            conta[u] = conta.get(u, 0) + n
    for i, u in enumerate(citacoes or (), 1):
        # `(?!\()` deixa de fora o link markdown `[1](http...)`, que é exibição e não
        # invocação.
        n = len(re.findall(rf"\[{i}\](?!\()", texto))
        if n:
            conta[u] = conta.get(u, 0) + n
    return conta


# Como o site se apresenta: o que o dono escreveu para aparecer na aba do navegador e no
# resultado de busca. Não é análise, é a vitrine — e é o suficiente.
_TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_DESCRICAO = (
    re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', re.I | re.S),
    re.compile(r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']', re.I | re.S),
    re.compile(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']', re.I | re.S),
)


def cartao_do_dominio(dominio, timeout=15):
    """Como o domínio se apresenta, em uma linha. `None` quando não dá para saber.

    Existe para responder a pergunta que nenhuma camada de verificação fazia: quem publica
    isto, e o que ele ganha com a afirmação? Em 21/08/2026 a espinha numérica de uma
    pesquisa inteira se apoiava em `noxhash.com`, que passou nas quatro camadas — existe,
    tem forma de fonte, não foi confessado como construído, trata do tema. O que ele é só
    aparece na própria home: "Cloud Mining Platform | Rent Mining Machines... Start from
    $20/mo". Um vendedor de aluguel de máquina, cujo interesse aponta na mesma direção da
    afirmação que sustentava.

    **Mostra, não julga.** Procurar sinal comercial por palavra-chave foi testado e
    reprovado no mesmo dia: mesmo com fronteira de palavra, `aneel.gov.br` casa "assinatura"
    e "preço" e seria acusada de parte interessada — a agência reguladora, que é a fonte
    primária por excelência. Seria o erro do domínio raiz outra vez, agora contra a melhor
    fonte que existe. Quem lê o cartão decide em dois segundos; quem classifica erra em
    silêncio.
    """
    for esquema in ("https", "http"):
        try:
            req = urllib.request.Request(
                f"{esquema}://{dominio}/",
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if "html" not in (r.headers.get("Content-Type") or "").lower():
                    return None
                bruto = r.read(150_000).decode("utf-8", "ignore")
            break
        except Exception:
            if esquema == "http":
                # Domínio que não responde não vira acusação. A ausência de cartão é
                # ausência de informação, e o item de decisão segue com a pergunta.
                return None

    def limpo(m):
        if not m:
            return ""
        return re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()

    titulo = limpo(_TITULO.search(bruto))
    descricao = ""
    for padrao in _DESCRICAO:
        descricao = limpo(padrao.search(bruto))
        if descricao:
            break
    if not titulo and not descricao:
        return None
    return {"titulo": titulo[:120], "descricao": descricao[:220]}


def _linha_em(texto, pos):
    ini = texto.rfind("\n", 0, pos) + 1
    fim = texto.find("\n", pos)
    return texto[ini: fim if fim > 0 else len(texto)], ini


def _e_linha_de_lista(texto, pos):
    """A ocorrência é só a exibição do endereço, sem afirmação ao lado.

    O critério é quanto texto sobra fora da URL, e não o marcador de lista: bullet com
    análise dentro é afirmação, e tratá-lo como item de lista descartou o trecho de três
    URLs fabricadas em 13/08/2026, uma delas com 290 caracteres de prosa na mesma linha.

    Isto substitui o corte por cabeçalho de fontes, que descartava metade do relatório —
    "referências", "sources" e "fontes:" são palavras comuns dentro da análise.
    """
    linha, _ = _linha_em(texto, pos)
    linha = linha.strip()
    # O que sobra fora do endereço vem antes do teste de comprimento: URL nua de 477
    # caracteres, como as da ANEEL e os links de redirecionamento do Gemini, passava por
    # afirmação só por ser comprida.
    sem_url = re.sub(r"https?://\S+", "", linha)
    sem_url = re.sub(r"^\s*([-*+•]|\d+[.)]|\[\d+\])\s*", "", sem_url).strip(" -–—·:|[]()*_")
    if len(sem_url) < 40:
        return True
    return len(linha) <= 400 and len(sem_url) < 60


def _prosa_acima(texto, pos, janela=700):
    """A afirmação escrita logo antes de uma linha que só exibe o endereço.

    Padrão comum na rodada 2: o motor escreve o veredito e põe `URL: <endereço>` na linha
    seguinte. A linha do endereço não tem afirmação nenhuma, e descartá-la sem olhar para
    cima perdia justamente o julgamento que a fonte sustentava.

    Devolve None quando acima só há outras linhas de endereço, que é o caso da lista de
    fontes no fim do relatório — ali não existe trecho a recuperar.
    """
    _, ini_linha = _linha_em(texto, pos)
    anterior = texto[:ini_linha].rstrip()
    if not anterior:
        return None

    linhas = []
    for linha in reversed(anterior.split("\n")):
        limpa = linha.strip()
        # Cabeçalho de lista de fontes: acima dele está outro assunto, e a URL abaixo é
        # item de índice. É o caso das sete URLs inventadas do slot C em 04/08/2026, que
        # ficam sob "FONTES CONSULTADAS", cada uma sozinha na linha — nunca tiveram trecho
        # e não devem ganhar um por vizinhança.
        if any(cab in limpa.lower() for cab in CABECALHOS_FONTES) and len(limpa) < 80:
            return None
        if not limpa:
            if linhas:
                break
            continue
        sem_url = re.sub(r"https?://\S+", "", limpa)
        sem_url = re.sub(r"^\s*([-*+•]|\d+[.)]|\[\d+\])\s*", "", sem_url).strip(" -–—·:|[]()*_")
        if len(sem_url) < 40:
            if linhas:
                break
            continue  # outra linha de endereço: segue subindo
        linhas.insert(0, limpa)
        if sum(len(x) for x in linhas) > janela:
            break
    if not linhas:
        return None
    trecho = re.sub(r"\s+", " ", " ".join(linhas)).strip()
    return trecho[-janela:] if len(trecho) > janela else trecho


def _contexto_literal(url, texto, janela=700):
    """A URL escrita no corpo do texto, junto da afirmação que sustenta."""
    if not texto or url not in texto:
        return None

    # A URL termina onde termina, e não onde começa outra maior. `find` casava por
    # prefixo, então `https://loja.com/` encontrava a ocorrência de
    # `https://loja.com/masculino/camisetas` e herdava o trecho dela: a home citada como
    # se fosse fonte ficava coberta pela prova da página específica, e o motor recebia na
    # rodada 2 uma afirmação que outra URL já sustentava. Seis casos no acervo.
    padrao = re.compile(re.escape(url) + r"(?![\w/\-])(?!\.[\w/])")

    inicio_busca, acima = 0, None
    while True:
        achado = padrao.search(texto, inicio_busca)
        pos = achado.start() if achado else -1
        if pos < 0:
            # Nenhuma ocorrência com afirmação ao lado. Se alguma delas tinha prosa logo
            # acima, ela vale mais que nada: é o veredito que precede `URL: <endereço>`.
            return acima
        if not _e_linha_de_lista(texto, pos):
            break
        acima = acima or _prosa_acima(texto, pos)
        inicio_busca = pos + len(url)

    # O parágrafo em que a URL aparece, mais o que vem logo antes dela.
    ini = texto.rfind("\n\n", 0, pos)
    if ini < 0 or pos - ini > janela:
        ini = max(0, pos - janela)
    fim = texto.find("\n\n", pos)
    if fim < 0 or fim - pos > 300:
        fim = min(len(texto), pos + 300)

    trecho = texto[ini:fim].strip()
    trecho = re.sub(r"\s+", " ", trecho)
    return trecho or None


def _contexto_por_marcador(url, texto, citacoes, janela=700):
    """Resolve `[N]` pela N-ésima citação e devolve o parágrafo onde o marcador aparece.

    Duas travas antes de confiar na numeração, porque mapeamento errado é pior que
    mapeamento ausente: ele costura a afirmação de um lugar na fonte de outro.

    A primeira é a consistência da série. Se o maior marcador do texto passar do número
    de citações devolvidas, a numeração não é posicional e nada aqui vale. A segunda é a
    presença: só se resolve marcador que exista no texto, e o trecho devolvido é o
    parágrafo em que ele aparece.
    """
    if not texto or not citacoes:
        return None

    # O corpo inteiro é lido. Cortar no cabeçalho de fontes, como faz a busca literal,
    # descarta texto bom: "referências", "sources" e "fontes:" são palavras comuns dentro
    # da análise, e o corte por última ocorrência chegou a reduzir o corpo a 4,8% do
    # relatório, no meio de uma frase sobre engenhos de açúcar. Item de lista se descarta
    # pela linha, logo abaixo, que é onde a informação de fato está.
    corpo = texto
    marcadores = [int(m.group(1)) for m in re.finditer(r"\[(\d{1,3})\]", corpo)]
    if not marcadores or max(marcadores) > len(citacoes):
        return None

    alvos = {i + 1 for i, u in enumerate(citacoes) if u == url}
    if not alvos:
        return None

    # Marcador isolado antes de marcador em lote. `[12]` sozinho ao fim de uma frase diz
    # o que aquela fonte sustenta; `[1][2][4][8][9][10][11][13][16][18]` no fim de um
    # resumo não diz nada sobre a fonte 12. Medido em 13/08/2026: em 22 de 24 resoluções,
    # a primeira ocorrência estava num lote, e seis "trechos" recuperados de uma mesma
    # resposta eram a mesma frase de abstract, deslocada de um caractere.
    candidatos = [m for m in re.finditer(r"\[(\d{1,3})\]", corpo) if int(m.group(1)) in alvos]
    isolados = [m for m in candidatos
                if not re.match(r"\s*\[\d", corpo[m.end(): m.end() + 4])
                and not corpo[max(0, m.start() - 4): m.start()].rstrip().endswith("]")]

    for m in (isolados + candidatos):
        pos = m.start()
        if _e_linha_de_lista(corpo, pos):
            continue

        # A frase em que o marcador aparece, e não a janela fixa: parágrafo de uma linha
        # só transformava `pos - 700` em janela deslizante, devolvendo o mesmo texto com
        # deslocamento de um caractere para citações diferentes.
        ini_par = corpo.rfind("\n\n", 0, pos)
        ini_par = 0 if ini_par < 0 else ini_par + 2

        # Fronteira de frase que enxerga o estilo acadêmico. Procurar ". " não funciona
        # aqui, porque o marcador cola no ponto: `...second century CE.[1][2][4]`. Sem
        # reconhecer o `.[`, o recuo ia para a frase anterior e seis URLs diferentes
        # recebiam o mesmo parágrafo de resumo, três deles byte a byte idênticos.
        limites = [m.end() for m in FIM_DE_FRASE.finditer(corpo, ini_par, pos)]
        ini = limites[-1] if limites else max(ini_par, pos - janela)
        seguinte = FIM_DE_FRASE.search(corpo, pos)
        fim_par = corpo.find("\n\n", pos)
        fim = (seguinte.start() + 1 if seguinte
               else (fim_par if fim_par > 0 else len(corpo)))
        fim = min(fim, pos + 400, len(corpo))
        if fim <= pos:
            fim = min(len(corpo), pos + 400)
        trecho = re.sub(r"\s+", " ", corpo[ini:fim]).strip()
        if trecho:
            return trecho
    return None


def citacoes_no_trecho(trecho):
    """Quantas fontes o trecho cita de uma vez.

    Citação em lote sustenta menos que citação isolada, e quem monta a rodada 2 precisa
    saber disso. Vai como número em campo próprio, e não como aviso colado no texto: o
    trecho é entregue ao motor como a afirmação a verificar, e frase em português dentro
    dele vira parte do que ele acha que precisa checar.
    """
    return len(re.findall(r"\[\d{1,3}\]", trecho or ""))


def _sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower())
                   if unicodedata.category(c) != "Mn")


def _texto_do_html(html):
    """Título, descrição e corpo inteiro. Regex basta: não é para renderizar a página,
    é só para saber do que ela trata.

    O corpo era cortado em 4.000 caracteres, e isso reprovava página boa por leitura
    curta: em `hdr.undp.org` e `elibrary.imf.org` os primeiros milhares de caracteres são
    navegação e aviso de cookie, com o assunto começando adiante. Medido em 12/08/2026.
    """
    partes = []
    for padrao in (r"<title[^>]*>(.*?)</title>",
                   r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
                   r'<meta[^>]+property=["\']og:(?:title|description)["\'][^>]+content=["\'](.*?)["\']',
                   r"<h1[^>]*>(.*?)</h1>"):
        partes += re.findall(padrao, html, re.I | re.S)

    corpo = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    corpo = re.sub(r"<[^>]+>", " ", corpo)
    partes.append(corpo)

    texto = " ".join(partes)
    texto = re.sub(r"&[a-z]+;|&#\d+;", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


# Página que responde 200 e não entrega conteúdo: parede de cookie, muro de assinatura,
# desafio de robô, casca que só se preenche por JavaScript. Ler pouco texto num destes é
# resultado do intermediário, e concluir "fora do tema" a partir daí acusa a fonte pelo
# que o intermediário fez. O caso medido foi `econstor.eu/...pdf`, que devolveu 4.732
# bytes de HTML com aviso de cookie no lugar do PDF, e foi reprovada por termo.
# Frase que só existe em tela de bloqueio. Uma basta para concluir que a leitura não vale.
SINAIS_DE_MURO = (
    "enable javascript", "javascript is disabled", "javascript is required",
    "requires javascript", "checking your browser", "verify you are human",
    "verifying you are human", "not a bot", "access denied", "403 forbidden",
    "subscribe to continue", "sign in to continue", "log in to continue",
    "accept all cookies", "por favor, habilite o javascript",
    "verificando seu navegador", "erro no site", "acesso negado",
    "conteudo restrito", "acesso restrito", "nao tem permissao",
    "mensagem incorretamente",
)

# Palavra que aparece em tela de bloqueio e também no assunto de páginas de tecnologia.
# Uma só não conclui nada: `quantica.scorasacademy.com.br` lista "Cloudflare" entre as
# competências do professor e foi acusada de ser muro de acesso em 13/08/2026. Duas ou
# mais, numa página curta, já descrevem a tela e não o conteúdo.
SINAIS_AMBIGUOS = (
    "cloudflare", "captcha", "anubis", "unauthorized", "site error", "error_type",
    "please wait", "loading...", "consent",
)


def _muro_ou_casca(texto, url, tipo):
    """Motivo pelo qual a leitura não conclui nada, ou None quando a página serve.

    O limiar é generoso de propósito. Uma tela de bloqueio tem pouco texto e some se for
    lida como página real: foi o que aconteceu com `econstor.eu`, que devolveu 1.473
    caracteres de aviso do Anubis, o desafio anti-robô, e virou "fora do tema" numa fonte
    que estava no tema. Errar para inconclusiva custa um aviso a mais; errar para fora do
    tema acusa a fonte pelo que o intermediário fez.
    """
    # Sem acento, porque metade dos avisos de bloqueio da internet brasileira tem: o
    # portal da ANEEL responde "Conteúdo Restrito" e a comparação acentuada não casava.
    baixo = _sem_acento(texto)
    # 3.500 porque a página de erro do Zope no portal da ANEEL tem 3.206 caracteres, e
    # sob o limite anterior a FAQ do regulador foi acusada de não tratar do tema numa
    # pesquisa sobre minigeração distribuída.
    curto = len(texto) < 3500

    if curto and any(s in baixo for s in SINAIS_DE_MURO):
        return "a resposta é muro de acesso, desafio de robô ou casca de JavaScript"

    if curto and sum(1 for s in SINAIS_AMBIGUOS if s in baixo) >= 2:
        return "a resposta parece tela de bloqueio: página curta com mais de um sinal"

    # Endereço de documento respondendo como página: o servidor entregou o intermediário.
    if re.search(r"\.(pdf|xml|docx?|pptx?|csv)(\?|$)", url, re.I) and "html" in (tipo or "") and curto:
        return "endereço de documento devolveu página HTML curta em vez do arquivo"

    if len(texto) < 900:
        return "página com texto legível insuficiente para concluir"
    return None


# Sufixos que separam a forma da raiz. Cortar aqui deixa "milling" casar com "mill" e
# "moinhos" casar com "moinho", sem precisar de dicionário.
SUFIXOS = ("ings", "ing", "ies", "es", "s")

# Sufixos aceitos ao casar a raiz no texto da página, e o casamento termina em fronteira
# de palavra. Isto é o que separa flexão de palavra diferente: com prefixo livre, a raiz
# "mill" casava "million", "millennium" e "milliondollar", e a conferência de assunto
# aprovava a página da Wikipédia sobre o Instagram numa pesquisa sobre moinhos medievais.
# Regressão introduzida e pega em auditoria no mesmo dia, 12/08/2026.
#
# O sufixo agentivo -er ficou de fora numa segunda passagem, e o motivo é o mesmo: "mill"
# mais "er" casa o sobrenome Miller, que aparece em qualquer bibliografia. Quem precisar
# de "miller", "moleiro" ou "sailor" passa a palavra inteira em --termos.
SUFIXOS_ACEITOS = "(?:s|es|ing|ings|ed)?"


def _raizes(termos):
    """Formas de busca derivadas de cada termo: o termo, suas partes e a raiz sem sufixo.

    Termo composto escrito junto não casa com a forma separada: `watermill` nunca acha
    "water mill", que é como a maioria das páginas históricas escreve. Quebrar por espaço
    e hífen resolve a metade separada; a outra metade é instrução de uso, e está no
    SKILL.md — em `--termos` se passa raiz curta.
    """
    saida = set()
    for bruto in termos:
        t = _sem_acento(bruto).strip()
        pedacos = [p for p in re.split(r"[\s\-_/]+", t) if p]
        for p in pedacos + ([t] if len(pedacos) > 1 else []):
            if len(p) < 4:
                continue
            saida.add(p)
            raiz = p
            for suf in SUFIXOS:
                if len(raiz) - len(suf) >= 4 and raiz.endswith(suf):
                    raiz = raiz[: -len(suf)]
                    break
            saida.add(raiz)
    return sorted(saida)


def verificar_tema(problemas, urls, termos, slot):
    """Confere se a página trata do tema da pesquisa.

    Existir não é sustentar. Uma URL pode responder 200 e falar de outra coisa — é o que
    acontece quando o modelo acerta o domínio e inventa o caminho, ou quando cita a home
    de um site em vez do artigo. Não julga se a página prova a afirmação: só se ela é
    sobre o assunto. O julgamento fino continua sendo trabalho de leitura.
    """
    uteis = _raizes(termos)
    curtos = [t for t in termos if len(_sem_acento(t).strip()) < 4]
    if curtos:
        log(f"AGENTE {slot}", f"termos ignorados por terem menos de 4 letras: {', '.join(curtos)}")
    if not uteis:
        log(f"AGENTE {slot}", "ATENÇÃO: nenhum termo utilizável sobrou. A conferência de "
                              "assunto não vai rodar nesta chamada.")
    if not uteis or not urls:
        return

    alvos = [u for u in urls if problemas.get(u, {}).get("estado") not in
             ("inexistente", "inventada", "removida")][:LIMITE_TEMA]
    if not alvos:
        return

    log(f"AGENTE {slot}",
        f"conferindo se {len(alvos)} páginas tratam do tema ({len(uteis)} formas: {', '.join(uteis[:8])}"
        f"{'…' if len(uteis) > 8 else ''})")

    def baixar(u, tentar_get_simples=True):
        # Sem cabeçalho Range. Servidor cujo arquivo é menor que o fim da faixa responde
        # 416 e a leitura falha: medido em 13/08/2026 num PDF do MPRA, que devolve 416
        # para `bytes=0-1500000` e 206 para `bytes=0-120000`. Ler N bytes do fluxo tem o
        # mesmo efeito prático e não depende do servidor aceitar faixa.
        req = urllib.request.Request(u, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        })
        with urllib.request.urlopen(req, timeout=25) as r:
            tipo = (r.headers.get("Content-Type") or "").lower()
            # O tipo vem no cabeçalho, antes do corpo. Documento sem HTML seria baixado
            # inteiro para ser descartado no passo seguinte: são megabytes de PDF por
            # pesquisa, jogados fora depois de trafegados.
            if "html" not in tipo and "text" not in tipo:
                return tipo, b""
            return tipo, r.read(BYTES_POR_PAGINA)

    def checar(u):
        try:
            tipo, bruto = baixar(u)
        except urllib.error.HTTPError as e:
            # Mesmo fallback do verificador de existência: servidor que recusa o pedido
            # automatizado não é fonte ruim, e o código HTTP precisa aparecer no motivo.
            if e.code in (403, 405, 429, 501):
                return u, None, f"rede: HTTP {e.code} — o servidor recusou a leitura"
            return u, None, f"rede: HTTP {e.code}"
        except Exception as e:
            return u, None, f"rede: {type(e).__name__}"

        # PDF e afins não têm HTML para ler. Não dá para concluir, e não se acusa.
        if "html" not in tipo and "text" not in tipo:
            return u, None, f"tipo {tipo.split(';')[0] or 'desconhecido'}"

        texto = _texto_do_html(bruto.decode("utf-8", errors="ignore"))
        muro = _muro_ou_casca(texto, u, tipo)
        if muro:
            return u, None, muro

        alvo = _sem_acento(texto)
        achados, intervalos = [], []
        for t in uteis:
            spans = [m.span() for m in
                     re.finditer(rf"\b{re.escape(t)}{SUFIXOS_ACEITOS}\b", alvo)]
            if spans:
                achados.append(t)
                intervalos += spans

        # Trecho do documento, e não contagem por raiz. `_raizes` emite a forma e cada
        # pedaço ("water mill", "water" e "mill"), e todos casam a MESMA passagem: contar
        # por raiz, e mesmo por posição inicial, fazia a mesma página passar ou reprovar
        # conforme a digitação do termo, o que é propriedade do pedido e não do documento.
        posicoes, fim_ultimo = 0, -1
        for ini_s, fim_s in sorted(intervalos):
            if ini_s >= fim_ultimo:
                posicoes += 1
                fim_ultimo = fim_s
            else:
                fim_ultimo = max(fim_ultimo, fim_s)

        # Menção única perdida num documento longo é ruído, e em página da Wikipédia é
        # quase sempre sobrenome em bibliografia: a página sobre insulina traz "Mills GB"
        # numa referência e passaria numa pesquisa sobre moinhos medievais. Medido em
        # 13/08/2026 — as páginas legítimas do teste têm de 1,2 a 49,7 ocorrências por 10
        # mil caracteres, e a de insulina tem 0,08.
        if posicoes == 1 and len(alvo) > TEXTO_LONGO:
            return u, [], "densidade"
        return u, achados, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for u, achados, motivo_nulo in ex.map(checar, alvos):
            if achados is None:
                # PDF e planilha não têm HTML para ler, e isso é o esperado numa fonte
                # acadêmica: não vira registro nenhum. Muro de acesso e falha de rede,
                # sim, porque ali houve tentativa de leitura que não concluiu, e o estado
                # precisa dizer isso — antes, página boa e página errada recebiam o mesmo
                # carimbo de "fora do tema".
                if motivo_nulo and motivo_nulo.startswith("tipo "):
                    continue
                reg = problemas.setdefault(u, {"estado": "ok", "motivos": []})
                # O motivo se registra sempre, mesmo quando o estado já é mais grave: quem
                # lê `motivos` precisa saber que a página estava atrás de muro, e antes
                # esse aviso sumia em silêncio nas URLs já marcadas como suspeitas.
                reg["motivos"].append(f"tema não conferido: {motivo_nulo}")
                # Falha do verificador não vai para a rodada 2. Sem esta marca, um 403 de
                # editora acadêmica viraria item de revalidação, e as cinco pesquisas com
                # termos registrados produziriam 157 itens desses contra 13 reais.
                # Só marca origem em registro que ainda não carrega acusação própria. URL
                # já suspeita ou inexistente precisa da rodada 2 justamente porque ninguém
                # conseguiu ler a página: excluí-la por causa de um 403 do verificador
                # esconde o caso mais grave atrás de uma falha nossa.
                if motivo_nulo and motivo_nulo.startswith("rede:") and reg["estado"] == "ok":
                    reg["origem"] = "rede"
                if reg["estado"] == "ok":
                    reg["estado"] = "inconclusiva"
                continue
            if not achados:
                reg = problemas.setdefault(u, {"estado": "ok", "motivos": []})
                # O motivo precisa dizer o que de fato aconteceu. Quando o corte é por
                # densidade, a página mencionou o termo uma vez, e escrever que ela não
                # menciona nenhum é afirmação falsa que viaja para o relatório e para o
                # prompt da rodada 2.
                if motivo_nulo == "densidade":
                    reg["motivos"].append(
                        "a página menciona um termo central uma única vez em documento "
                        "longo, o que não sustenta que ela trate do assunto")
                else:
                    reg["motivos"].append(
                        "a página existe mas não menciona nenhum termo central da pesquisa")
                # Sinal fraco nunca rebaixa falha dura. A URL de domínio raiz que já era
                # `suspeita` continuava suspeita antes desta guarda; sem ela, a conferência
                # de tema lavava a acusação mais grave e o motor deixava de responder por
                # ela. Caso real em 12/08/2026: scorasacademy.com.br, marcada por forma e
                # depois sobrescrita para fora do tema.
                if reg["estado"] == "ok":
                    reg["estado"] = "fora do tema"

    fora = [u for u, r in problemas.items() if r["estado"] == "fora do tema"]
    if fora:
        log(f"AGENTE {slot}", f"ALERTA: {len(fora)} páginas existem mas não falam do tema")
        for u in fora[:5]:
            log(f"AGENTE {slot}", f"  fora do tema: {u[:80]}")


def problemas_gravados(pasta, nome_arquivo, slot, resultado):
    """O veredito de um motor numa rodada, venha ele de onde vier.

    Desde 13/08/2026 a verificação é passo separado e grava `r1_verificacao.json`. As
    pesquisas anteriores guardam o mesmo dado dentro do próprio `r1.json`, no campo
    `urls_problematicas`. Quem mede qualidade precisa ler as duas formas, senão a série
    histórica se parte em duas no dia da mudança.
    """
    from pathlib import Path
    import json as _json

    base = Path(nome_arquivo).stem
    arq = Path(pasta) / f"{base}_verificacao.json"
    if arq.exists():
        try:
            d = _json.loads(arq.read_text(encoding="utf-8"))
            return (d.get("por_motor") or {}).get(slot) or {}
        except Exception:
            pass
    return resultado.get("urls_problematicas") or {}
