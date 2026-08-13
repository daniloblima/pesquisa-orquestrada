#!/usr/bin/env python3
"""
buscar.py — dispara os motores de pesquisa em paralelo via OpenRouter.

Este script é o único ponto que gasta crédito. Toda a inteligência de
orquestração (clarificação, consenso, divergência, consolidação) fica no
Claude Code, no SKILL.md.

Só usa biblioteca padrão do Python. Não precisa instalar nada.

Uso:
    # Rodada 1 — mesmo prompt para os três agentes
    python3 buscar.py --prompt-file prompt.md --saida r1.json --rodada 1

    # Rodada 2 — prompt diferente por agente (None = não chama aquele agente)
    python3 buscar.py --prompts-file prompts.json --saida r2.json --rodada 2

    # Só estimar o custo, sem chamar
    python3 buscar.py --prompt-file prompt.md --estimar
"""

import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
import threading
import traceback
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

API_URL = "https://openrouter.ai/api/v1/chat/completions"
RAIZ_SKILL = Path(__file__).resolve().parent.parent
CONFIG_PATH = RAIZ_SKILL / "config.json"

# Ordem de procura da chave. O primeiro que tiver valor vence.
# Nunca dentro do repositório: chave não mora junto do código.
LOCAIS_CHAVE = [
    Path.home() / ".claude" / ".env",
    Path.home() / ".config" / "openrouter" / ".env",
]


# ---------------------------------------------------------------- infra

_ARQUIVO_LOG = None
_LOCK_LOG = threading.Lock()


def abrir_log(caminho):
    """Passa a gravar o log em arquivo, além da tela.

    Log que só vai para a tela morre quando a sessão fecha, e aí não há como saber o que
    quebrou, onde nem por quê. O arquivo fica ao lado do JSON da rodada.
    """
    global _ARQUIVO_LOG
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        _ARQUIVO_LOG = open(caminho, "a", encoding="utf-8")
        _ARQUIVO_LOG.write(f"\n{'=' * 78}\n")
        _ARQUIVO_LOG.write(f"execução iniciada em {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        _ARQUIVO_LOG.write(f"comando: {' '.join(sys.argv)}\n")
        _ARQUIVO_LOG.write(f"{'=' * 78}\n")
        _ARQUIVO_LOG.flush()
        return caminho
    except Exception as e:
        print(f"AVISO: não consegui abrir o log em {caminho}: {type(e).__name__}: {e}", flush=True)
        return None


def log(etapa, mensagem):
    """Formato de log do projeto: [HH:MM:SS] [ETAPA] mensagem."""
    linha = f"[{datetime.now():%H:%M:%S}] [{etapa}] {mensagem}"
    print(linha, flush=True)
    if _ARQUIVO_LOG:
        # Os agentes rodam em paralelo e escrevem no mesmo arquivo.
        with _LOCK_LOG:
            try:
                _ARQUIVO_LOG.write(linha + "\n")
                _ARQUIVO_LOG.flush()
            except Exception:
                pass  # log quebrado nunca derruba a pesquisa


def log_excecao(etapa, e):
    """Registra a exceção inteira, com pilha, no arquivo e na tela."""
    log(etapa, f"EXCEÇÃO {type(e).__name__}: {e}")
    pilha = traceback.format_exc()
    print(pilha, flush=True)
    if _ARQUIVO_LOG:
        with _LOCK_LOG:
            try:
                _ARQUIVO_LOG.write(pilha + "\n")
                _ARQUIVO_LOG.flush()
            except Exception:
                pass


def carregar_config():
    """Lê o config e normaliza os motores num dicionário por id.

    Não há teto nem letra de slot: acrescentar motor é acrescentar item na lista
    'motores' do config.json. O id é o nome usado em --motores e nas chaves do
    arquivo de prompts da rodada 2.
    """
    log("CONFIG", f"lendo {CONFIG_PATH}")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)

    if "motores" not in cfg:
        raise SystemExit(
            "ERRO: config.json sem a lista 'motores'. Este script não usa mais os slots "
            "A, B e C. Migre o config para o formato de lista com 'id' por motor."
        )

    catalogo, vistos = {}, set()
    for m in cfg["motores"]:
        mid = (m.get("id") or "").strip()
        if not mid:
            raise SystemExit(f"ERRO: motor sem 'id' no config.json: {m.get('modelo')}")
        if mid in vistos:
            raise SystemExit(f"ERRO: id repetido no config.json: {mid}")
        vistos.add(mid)
        catalogo[mid] = m
    cfg["_catalogo"] = catalogo

    padrao = [mid for mid, m in catalogo.items() if m.get("padrao")]
    log("CONFIG", f"{len(catalogo)} motores no config: {', '.join(catalogo)}")
    log("CONFIG", f"padrão quando --motores é omitido: {', '.join(padrao) or 'nenhum'}")
    return cfg


def carregar_chave():
    """Procura OPENROUTER_API_KEY no ambiente e depois nos arquivos .env conhecidos."""
    chave = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if chave:
        log("CHAVE", "encontrada na variável de ambiente OPENROUTER_API_KEY")
        return chave

    for caminho in LOCAIS_CHAVE:
        if not caminho.exists():
            continue
        try:
            for linha in caminho.read_text(encoding="utf-8").splitlines():
                linha = linha.strip()
                if linha.startswith("OPENROUTER_API_KEY="):
                    valor = linha.split("=", 1)[1].strip().strip('"').strip("'")
                    if valor:
                        log("CHAVE", f"encontrada em {caminho}")
                        return valor
        except Exception as e:
            log("CHAVE", f"falha ao ler {caminho}: {e}")

    locais = "\n  ".join(str(p) for p in LOCAIS_CHAVE)
    raise SystemExit(
        "ERRO: chave do OpenRouter não encontrada.\n"
        "Defina a variável OPENROUTER_API_KEY ou coloque a linha\n"
        "  OPENROUTER_API_KEY=sua_chave\n"
        f"em um destes arquivos:\n  {locais}"
    )


# ---------------------------------------------------------------- chamada

def extrair_urls(conteudo, annotations):
    """Junta as URLs das citações estruturadas com as que aparecem no texto."""
    urls = []

    for a in annotations or []:
        if isinstance(a, dict) and a.get("type") == "url_citation":
            u = (a.get("url_citation") or {}).get("url")
            if u:
                urls.append(u)

    # Fallback: nem todo modelo devolve citação estruturada.
    for u in re.findall(r"https?://[^\s\)\]\>\"'`,;]+", conteudo or ""):
        urls.append(u.rstrip(".,;:"))

    vistas, unicas = set(), []
    for u in urls:
        if u not in vistas:
            vistas.add(u)
            unicas.append(u)
    return unicas


def urls_das_citacoes(annotations):
    """A lista de citações na ordem original, com as repetições preservadas.

    Motor que cita em estilo acadêmico escreve `[7]` no parágrafo e deixa a URL para a
    lista do fim. O número é a posição da citação, então a N-ésima annotation é a fonte
    do marcador `[N]`. Esta lista existe separada de `extrair_urls` justamente porque lá
    a repetição é removida: uma página citada duas vezes encurtaria a lista e deslocaria
    todos os marcadores seguintes, trocando a fonte de cada afirmação em silêncio.
    """
    saida = []
    for a in annotations or []:
        if isinstance(a, dict) and a.get("type") == "url_citation":
            u = (a.get("url_citation") or {}).get("url")
            if u:
                saida.append(u)
    return saida


MAX_TENTATIVAS = 3
ESPERA_ENTRE_TENTATIVAS = [10, 30]  # segundos, entre a 1ª e a 2ª, e entre a 2ª e a 3ª

# Sinais de falha passageira do provedor. Erro de conteúdo não se reenvia.
SINAIS_TRANSITORIOS = (
    "timed out", "timeout", "502", "503", "504", "bad gateway",
    "upstream error", "temporarily", "overloaded", "rate limit", "connection reset",
)


def vale_retentar(e):
    """Só reenvia quando a falha é do provedor, não quando é do pedido."""
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (408, 429, 500, 502, 503, 504)
    texto = f"{type(e).__name__} {e}".lower()
    return any(s in texto for s in SINAIS_TRANSITORIOS)


class _SemRedirect(urllib.request.HTTPRedirectHandler):
    """Interrompe no primeiro redirect para capturar o destino sem baixar a página."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, newurl, headers, fp)


# Domínios que devolvem link opaco em vez da fonte real.
DOMINIOS_REDIRECT = ("vertexaisearch.cloud.google.com",)


def resolver_redirects(urls, slot, mapa_saida=None):
    """Troca links de redirecionamento pela URL real da fonte.

    O grounding do Google devolve URLs opacas que expiram e não dizem nada a quem
    lê o relatório. Falha aqui não é grave: mantém a original e segue.
    """
    alvos = [u for u in urls if any(d in u for d in DOMINIOS_REDIRECT)]
    if not alvos:
        return urls

    log(f"AGENTE {slot}", f"resolvendo {len(alvos)} links de redirecionamento")
    opener = urllib.request.build_opener(_SemRedirect)
    mapa = {}

    def resolver(u):
        try:
            opener.open(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20)
            return u, None
        except urllib.error.HTTPError as e:
            destino = e.msg if isinstance(e.msg, str) and e.msg.startswith("http") else None
            return u, destino
        except Exception as e:
            log(f"AGENTE {slot}", f"não resolveu {u[:60]}: {type(e).__name__}: {e}")
            return u, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(alvos))) as ex:
        for original, destino in ex.map(resolver, alvos):
            if destino:
                mapa[original] = destino

    log(f"AGENTE {slot}", f"{len(mapa)} de {len(alvos)} links resolvidos para a fonte real")
    # O chamador precisa do mapa para aplicar a mesma troca na lista de citações. Sem
    # isso, `problemas` guarda a URL resolvida e `citacoes` a opaca, e o caminho por
    # marcador nunca encontra alvo — some justamente no Gemini, que é o motor com sete das
    # oito URLs inventadas da série e o único que devolve link de redirecionamento.
    if mapa_saida is not None:
        mapa_saida.update(mapa)

    vistas, saida = set(), []
    for u in urls:
        final = mapa.get(u, u)
        if final not in vistas:
            vistas.add(final)
            saida.append(final)
    return saida


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
SINAIS_FRACOS = ("fora do tema", "inconclusiva")


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
            achados[u] = {"estado": "suspeita", "motivos": motivos}

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
                if reg["estado"] != "suspeita":
                    reg["estado"] = "ok"
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

    graves = [u for u, r in achados.items()
              if r["estado"] in ("inexistente", "suspeita", "inventada", "removida")]
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


def chamar_agente(slot, agente, prompt, max_tokens, max_results, timeout, chave, verificar_rede=True,
                  termos=None):
    """Chama um motor. Nunca levanta exceção — devolve o erro dentro do dict."""
    modelo = agente["modelo"]
    inicio = time.time()
    log(f"AGENTE {slot}", f"iniciando · modelo={modelo} · max_tokens={max_tokens} · prompt={len(prompt)} chars")

    body = {
        "model": modelo,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "usage": {"include": True},
    }

    if not agente.get("busca_nativa"):
        # O 'engine' precisa ser explícito. Sem ele, os modelos Google ignoram
        # o plugin em silêncio e respondem de memória, sem fonte nenhuma.
        engine = agente.get("engine_busca", "native")
        body["plugins"] = [{"id": "web", "max_results": max_results, "engine": engine}]
        log(f"AGENTE {slot}", f"busca web via plugin · engine={engine} · max_results={max_results}")
    else:
        log(f"AGENTE {slot}", "busca nativa do próprio modelo (sem plugin)")

    # Sem limitar o raciocínio, modelos como o Gemini gastam o orçamento inteiro
    # pensando e devolvem texto curto. Pesquisa quer cobertura, não raciocínio longo.
    if agente.get("reasoning_effort"):
        body["reasoning"] = {"effort": agente["reasoning_effort"]}
        log(f"AGENTE {slot}", f"reasoning effort={agente['reasoning_effort']}")

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {chave}",
            "Content-Type": "application/json",
            "X-Title": "pesquisa-orquestrada",
        },
        method="POST",
    )

    resultado = {
        "slot": slot,
        "modelo": modelo,
        "rotulo": agente.get("rotulo", modelo),
        "conteudo": "",
        "urls": [],
        "citacoes": [],
        "falhas_duras": 0,
        "falhas_duras_sem_rastro": 0,
        "urls_fora_do_tema": [],
        "tokens_in": 0,
        "tokens_out": 0,
        "custo_usd": 0.0,
        "duracao_s": 0.0,
        "sem_fontes": False,
        "urls_problematicas": {},
        "urls_inexistentes": [],
        "urls_suspeitas": [],
        "afirmacoes_a_revalidar": [],
        "reprovadas_sem_rastro": False,
        "erro": None,
    }

    try:
        # O sonar-deep-research trabalha por minutos e o provedor às vezes derruba a
        # conexão com 502. Falha transitória não pode custar o agente inteiro.
        dados = None
        ultimo_erro = None
        for tentativa in range(1, MAX_TENTATIVAS + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    dados = json.loads(resp.read().decode("utf-8"))
                erro_api = dados.get("error")
                if erro_api:
                    raise RuntimeError(f"OpenRouter devolveu erro: {json.dumps(erro_api, ensure_ascii=False)}")
                break
            except Exception as e:
                ultimo_erro = e
                if tentativa >= MAX_TENTATIVAS or not vale_retentar(e):
                    raise
                espera = ESPERA_ENTRE_TENTATIVAS[tentativa - 1]
                log(
                    f"AGENTE {slot}",
                    f"tentativa {tentativa} falhou ({type(e).__name__}: {str(e)[:160]}). "
                    f"Nova tentativa em {espera}s.",
                )
                time.sleep(espera)

        if dados is None:
            raise ultimo_erro or RuntimeError("sem resposta do provedor")

        escolhas = dados.get("choices") or []
        if not escolhas:
            raise RuntimeError(f"resposta sem 'choices': {json.dumps(dados, ensure_ascii=False)[:800]}")

        msg = escolhas[0].get("message") or {}
        conteudo = msg.get("content") or ""
        uso = dados.get("usage") or {}

        mapa_redirect = {}
        resultado["conteudo"] = conteudo
        resultado["urls"] = resolver_redirects(
            extrair_urls(conteudo, msg.get("annotations")), slot, mapa_redirect)
        resultado["citacoes"] = [mapa_redirect.get(u, u)
                                 for u in urls_das_citacoes(msg.get("annotations"))]
        resultado["tokens_in"] = uso.get("prompt_tokens", 0)
        resultado["tokens_out"] = uso.get("completion_tokens", 0)
        resultado["custo_usd"] = float(uso.get("cost", 0.0) or 0.0)
        resultado["finish_reason"] = escolhas[0].get("finish_reason")

        if not conteudo.strip():
            resultado["erro"] = "modelo respondeu vazio"
            log(f"AGENTE {slot}", "ATENÇÃO: conteúdo vazio na resposta")

        # O provedor às vezes devolve 200 com finish_reason de erro. Sem isto o agente
        # entra em agentes_ok e a rodada parece ter dado certo.
        if resultado.get("finish_reason") == "error":
            resultado["erro"] = (resultado["erro"] or "") + \
                " | provedor devolveu finish_reason=error"
            log(f"AGENTE {slot}", "FALHOU: finish_reason=error — resposta interrompida pelo provedor")

        # Trava de qualidade. Um agente que não devolveu nenhuma URL provavelmente
        # respondeu de memória. Não pode contar como fonte de confirmação.
        if not resultado["erro"] and not resultado["urls"]:
            resultado["sem_fontes"] = True
            log(
                f"AGENTE {slot}",
                "ALERTA: zero URLs. Provavelmente respondeu de memória, sem pesquisar. "
                "NÃO usar como confirmação de nada.",
            )

        # A trava acima cobre o caso benigno. Esta cobre o grave: URL presente que
        # não existe ou que o próprio modelo construiu.
        if resultado["urls"]:
            problemas = verificar_urls(resultado["urls"], conteudo, slot, verificar_rede)
            if verificar_rede and termos:
                verificar_tema(problemas, resultado["urls"], termos, slot)
            problemas = {u: r for u, r in problemas.items() if r["estado"] != "ok"}

            # Sem o trecho em que a fonte foi usada, descartar a afirmação apaga
            # informação possivelmente verdadeira sem deixar rastro.
            citacoes = resultado.get("citacoes") or []
            for u, reg in problemas.items():
                reg["contexto"] = contexto_da_url(u, conteudo, citacoes=citacoes)
                lote = citacoes_no_trecho(reg["contexto"])
                if lote > 2:
                    reg["citacoes_no_trecho"] = lote

            graves = duras(problemas)
            fracas = {u: r for u, r in problemas.items() if u not in graves}
            sem_rastro = [u for u, r in graves.items() if not r.get("contexto")]

            if problemas:
                log(f"AGENTE {slot}",
                    f"{len(graves)} falhas duras e {len(fracas)} sinais fracos "
                    f"(fora do tema ou sem conferência). Das duras, "
                    f"{len(graves) - len(sem_rastro)} têm o trecho que sustentavam")

            # A quarentena alcança as afirmações que dependem da fonte reprovada. Quando
            # nem o trecho se localiza, o que fica em aberto é aquela afirmação, e não a
            # contribuição inteira do agente: a regra antiga descartava trinta afirmações
            # bem citadas por causa de quatro fontes sem rastro, e em 12/08 descartou seis
            # respostas boas do Perplexity, que cita por marcador numerado.
            if sem_rastro:
                resultado["reprovadas_sem_rastro"] = True
                log(f"AGENTE {slot}",
                    f"ATENÇÃO: {len(sem_rastro)} de {len(graves)} fontes com falha dura não "
                    "têm trecho localizável, nem por URL no corpo nem por marcador numerado. "
                    "Só o que se apoia nelas fica em quarentena; o restante do agente vale.")

            resultado["falhas_duras"] = len(graves)
            resultado["falhas_duras_sem_rastro"] = len(sem_rastro)
            resultado["urls_problematicas"] = problemas
            # Todo estado que não seja "ok" e tenha trecho vai para a rodada 2, inclusive
            # inconclusiva. Excluí-la custou caro por dez minutos: URL fabricada que
            # responde 200 com página curta cai em inconclusiva, e sairia da revalidação
            # sem que ninguém notasse — que é exatamente o modo de falha que a regra dura
            # 2 do SKILL.md chama de mais perigoso do produto. Revalidar é barato.
            resultado["afirmacoes_a_revalidar"] = [
                {"url": u, "estado": r["estado"], "motivos": r["motivos"],
                 "trecho": r["contexto"], "citacoes_no_trecho": r.get("citacoes_no_trecho")}
                for u, r in problemas.items()
                if r.get("contexto") and r.get("origem") != "rede"
            ]
            resultado["urls_inexistentes"] = [
                u for u, r in problemas.items() if r["estado"] == "inexistente"
            ]
            resultado["urls_suspeitas"] = [u for u in graves if u not in resultado["urls_inexistentes"]]
            resultado["urls_fora_do_tema"] = [
                u for u, r in problemas.items() if r["estado"] == "fora do tema"
            ]

        if resultado.get("finish_reason") == "length":
            log(f"AGENTE {slot}", "ATENÇÃO: resposta truncada por limite de tokens (finish=length)")

    except urllib.error.HTTPError as e:
        corpo = ""
        try:
            corpo = e.read().decode("utf-8")[:1500]
        except Exception as e2:
            corpo = f"(não foi possível ler o corpo do erro: {e2})"
        resultado["erro"] = f"HTTP {e.code}: {corpo}"
        log(f"AGENTE {slot}", f"FALHOU · HTTP {e.code} · {corpo[:400]}")

    except Exception as e:
        resultado["erro"] = f"{type(e).__name__}: {e}"
        log_excecao(f"AGENTE {slot}", e)

    resultado["duracao_s"] = round(time.time() - inicio, 1)

    if not resultado["erro"]:
        log(
            f"AGENTE {slot}",
            f"concluído · {resultado['duracao_s']}s · in={resultado['tokens_in']} out={resultado['tokens_out']} "
            f"· {len(resultado['urls'])} URLs · US$ {resultado['custo_usd']:.4f} "
            f"· finish={resultado.get('finish_reason')}",
        )
    return resultado


# ---------------------------------------------------------------- fluxo

def escolher_motores(args, cfg):
    """Quais motores rodam. Sem --motores, só os marcados como padrão no config.

    Motor caro nunca entra por omissão: quem não é padrão precisa ser pedido pelo nome.
    """
    catalogo = cfg["_catalogo"]
    pedido = args.motores or args.agentes  # --agentes continua aceito como apelido antigo

    if not pedido:
        escolhidos = [mid for mid, m in catalogo.items() if m.get("padrao")]
        if not escolhidos:
            raise SystemExit("ERRO: nenhum motor marcado como padrão no config.json e "
                             "nenhum informado em --motores.")
        return escolhidos

    escolhidos, desconhecidos = [], []
    for nome in (x.strip() for x in pedido.split(",")):
        if not nome:
            continue
        if nome in catalogo:
            escolhidos.append(nome)
            continue
        # Aceita também o id do modelo inteiro, para quem preferir ser explícito.
        por_modelo = [mid for mid, m in catalogo.items() if m["modelo"] == nome]
        if por_modelo:
            escolhidos.append(por_modelo[0])
        else:
            desconhecidos.append(nome)

    if desconhecidos:
        raise SystemExit(
            f"ERRO: motor não encontrado no config.json: {', '.join(desconhecidos)}\n"
            f"Disponíveis: {', '.join(catalogo)}"
        )
    return list(dict.fromkeys(escolhidos))


def avisar_composicao(escolhidos, cfg):
    """As regras de desenho continuam valendo, agora calculadas sobre o número escolhido."""
    catalogo = cfg["_catalogo"]
    n = len(escolhidos)

    indices = {}
    for mid in escolhidos:
        indices.setdefault(catalogo[mid].get("indice", "?"), []).append(mid)
    repetidos = {i: ms for i, ms in indices.items() if len(ms) > 1}
    if repetidos:
        for indice, ms in repetidos.items():
            log("COMPOSIÇÃO", f"ATENÇÃO: {len(ms)} motores do índice {indice} ({', '.join(ms)}). "
                              "Eles leem as mesmas páginas, então concordância entre eles não valida nada.")

    if n < 2:
        log("COMPOSIÇÃO", "ATENÇÃO: um motor só. Não há validação cruzada nenhuma nesta pesquisa.")
    elif n == 2:
        log("COMPOSIÇÃO", "ATENÇÃO: dois motores. Sem terceiro, contradição não tem árbitro na rodada 2.")
    elif n > 3:
        log("COMPOSIÇÃO", f"{n} motores: mais material para comparar, sem ganho proporcional de "
                          "independência. A análise tende a ficar mais rasa.")

    custo = sum(catalogo[m].get("custo_tipico_usd", 0) for m in escolhidos)
    log("COMPOSIÇÃO", f"{n} motores · {len(indices)} índices distintos · custo típico US$ {custo:.2f} por rodada")


def montar_prompts(args, cfg, escolhidos):
    """Devolve {id: prompt|None} a partir de --prompt-file ou --prompts-file."""
    if args.prompts_file:
        with open(args.prompts_file, encoding="utf-8") as f:
            bruto = json.load(f)
        prompts = {mid: (bruto.get(mid) or None) for mid in escolhidos}
        desconhecidos = set(bruto) - set(cfg["_catalogo"])
        if desconhecidos:
            log("PROMPTS", f"ATENÇÃO: ignorados por não existirem no config: {sorted(desconhecidos)}")
        fora = set(bruto) & set(cfg["_catalogo"]) - set(escolhidos)
        if fora:
            log("PROMPTS", f"ATENÇÃO: têm prompt mas não foram escolhidos: {sorted(fora)}")
    else:
        with open(args.prompt_file, encoding="utf-8") as f:
            texto = f.read()
        prompts = {mid: texto for mid in escolhidos}

    for mid in escolhidos:
        estado = f"{len(prompts[mid])} chars" if prompts[mid] else "não será chamado"
        log("PROMPTS", f"{mid}: {estado}")
    return prompts


def teto_de_saida(agente, par, rodada):
    """Teto de saída do motor. O do modo vale, salvo quando o motor declara o próprio.

    Um teto único para todos quebra em motor que raciocina antes de escrever: o orçamento
    vai no raciocínio e a resposta sai truncada muito antes do número declarado. Medido em
    12/08/2026 no sonar-deep-research, quatro chamadas em quatro com finish=length, uma
    delas entregando 622 tokens visíveis contra teto de 5.000. Motor com esse perfil
    declara `max_tokens` por rodada no config.
    """
    padrao = par["max_tokens_r1"] if rodada == 1 else par["max_tokens_r2"]
    proprio = (agente.get("max_tokens") or {}).get(f"r{rodada}")
    return int(proprio) if proprio else padrao


def _faixa_entrada(preco):
    """Tokens de entrada esperados: um número, ou a faixa medida quando o motor varia.

    O Grok multi-agent lê o material que decide ler, e isso mede entre 179 mil e 720 mil
    tokens em doze chamadas — fator 4,0 sem variável nossa que explique, nem número de
    perguntas, nem modo, nem tamanho do prompt. Estimar um motor assim por valor único
    produz teto que estoura de um lado e infla do outro.
    """
    faixa = preco.get("tokens_input_busca", 20000)
    if isinstance(faixa, dict):
        tipico = faixa.get("tipico", faixa.get("max", 20000))
        return tipico, faixa.get("max", tipico)
    return faixa, faixa


def estimar(prompts, cfg, par, rodada):
    """Faixa de custo, não número único.

    Cada motor tem perfil de input próprio e medido: o que recebe os resultados de
    busca no prompt chega a dezenas de milhares de tokens; o que pesquisa do lado do
    provedor recebe quase nada e cobra por busca. Um valor médio para todos erra por
    fator de 2 a 3 nas duas direções.
    """
    precos = cfg.get("precos_por_milhao_usd", {})
    fracao = cfg.get("fracao_saida_tipica", 0.55)

    minimo, teto, detalhe = 0.0, 0.0, {}
    for mid, prompt in prompts.items():
        if not prompt:
            continue
        agente = cfg["_catalogo"][mid]
        p = precos.get(
            agente["modelo"],
            {"in": 3.0, "out": 15.0, "taxa_fixa": 0.0, "tokens_input_busca": 20000},
        )
        max_tokens = teto_de_saida(agente, par, rodada)
        entrada_tipica, entrada_maxima = _faixa_entrada(p)

        chars = len(prompt) / 3.5  # ~3,5 chars por token
        base_tip = ((chars + entrada_tipica) / 1e6) * p["in"] + p.get("taxa_fixa", 0.0)
        base_max = ((chars + entrada_maxima) / 1e6) * p["in"] + p.get("taxa_fixa", 0.0)
        c_teto = base_max + (max_tokens / 1e6) * p["out"]
        c_min = base_tip + (max_tokens * fracao / 1e6) * p["out"]

        detalhe[mid] = {"tipico": round(c_min, 4), "teto": round(c_teto, 4)}
        minimo += c_min
        teto += c_teto

    log("CUSTO", f"estimado entre US$ {minimo:.2f} e US$ {teto:.2f} · por agente: {detalhe}")
    if any(cfg["_catalogo"][m].get("busca_nativa") for m, pr in prompts.items() if pr):
        log("CUSTO", "o motor de busca profunda cobra por consulta interna, então o valor real "
                     "varia com o tema e pode passar do teto em pesquisa muito ampla")
    return {"tipico_usd": round(minimo, 2), "teto_usd": round(teto, 2), "por_agente": detalhe}


def main():
    p = argparse.ArgumentParser(description="Dispara os motores de pesquisa via OpenRouter.")
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--prompt-file", help="Arquivo com o prompt único, enviado a todos os agentes.")
    grupo.add_argument("--prompts-file", help='JSON {"A": "...", "B": null, "C": "..."} com prompt por agente.')
    p.add_argument("--saida", help="Caminho do JSON de saída. Os .md por agente ficam ao lado.")
    p.add_argument("--rodada", type=int, default=1, choices=[1, 2], help="1 ou 2. Define o teto de tokens.")
    p.add_argument("--modo", default=None, choices=["rapida", "normal", "profunda"])
    p.add_argument("--motores", default=None,
                   help="Motores a usar, por id, ex: grok,gpt,gemini. Omitido, usa os marcados "
                        "como padrão no config.json. Não há teto.")
    p.add_argument("--agentes", default=None, help="Apelido antigo de --motores.")
    p.add_argument("--estimar", action="store_true", help="Só estima o custo e sai, sem chamar nada.")
    p.add_argument("--sem-verificar-urls", action="store_true",
                   help="Pula a checagem de existência das URLs. Não recomendado.")
    p.add_argument("--termos", default=None,
                   help="Termos centrais do tema, separados por vírgula. Ativa a conferência "
                        "de que cada página realmente trata do assunto.")
    args = p.parse_args()

    if not args.estimar and not args.saida:
        p.error("--saida é obrigatório quando não se usa --estimar")

    if args.saida:
        caminho_log = abrir_log(Path(args.saida).expanduser().resolve().with_suffix(".log"))
        if caminho_log:
            print(f"log desta execução: {caminho_log}", flush=True)

    cfg = carregar_config()
    modo = args.modo or cfg.get("modo_padrao", "normal")
    par = cfg["modos"][modo]
    max_tokens = par["max_tokens_r1"] if args.rodada == 1 else par["max_tokens_r2"]
    max_results = par["max_results_busca"]
    timeout = cfg.get("timeout_segundos", 900)

    termos = [t.strip() for t in (args.termos or "").split(",") if t.strip()]
    log("INÍCIO", f"rodada={args.rodada} · modo={modo} · max_tokens do modo={max_tokens} · timeout={timeout}s")
    if termos:
        log("INÍCIO", f"conferência de tema ligada: {', '.join(termos)}")
    else:
        log("INÍCIO", "sem --termos: as páginas não serão conferidas quanto ao assunto")

    escolhidos = escolher_motores(args, cfg)
    avisar_composicao(escolhidos, cfg)

    prompts = montar_prompts(args, cfg, escolhidos)
    ativos = [m for m, pr in prompts.items() if pr]
    if not ativos:
        raise SystemExit("ERRO: nenhum motor tem prompt. Nada a fazer.")

    for m in ativos:
        proprio = teto_de_saida(cfg["_catalogo"][m], par, args.rodada)
        if proprio != max_tokens:
            log("CONFIG", f"{m}: teto de saída próprio, {proprio} tokens em vez dos {max_tokens} do modo")

    estimativa = estimar(prompts, cfg, par, args.rodada)
    if args.estimar:
        print(json.dumps(estimativa, ensure_ascii=False, indent=2))
        return

    chave = carregar_chave()
    log("RODADA", f"disparando {len(ativos)} motores em paralelo: {', '.join(ativos)}")
    for m in ativos:
        if cfg["_catalogo"][m].get("busca_nativa"):
            log("RODADA", f"{m} faz busca profunda própria e pode levar de 3 a 10 minutos")

    inicio = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ativos)) as executor:
        futuros = {
            executor.submit(
                chamar_agente, m, cfg["_catalogo"][m], prompts[m],
                teto_de_saida(cfg["_catalogo"][m], par, args.rodada), max_results,
                timeout, chave, not args.sem_verificar_urls, termos
            ): m
            for m in ativos
        }
        resultados = [f.result() for f in concurrent.futures.as_completed(futuros)]

    resultados.sort(key=lambda r: r["slot"])
    duracao = round(time.time() - inicio, 1)
    custo_total = round(sum(r["custo_usd"] for r in resultados), 4)
    ok = [r["slot"] for r in resultados if not r["erro"]]
    falhos = [r["slot"] for r in resultados if r["erro"]]
    sem_fontes = [r["slot"] for r in resultados if r.get("sem_fontes")]
    com_url_falsa = {
        r["slot"]: len(r.get("urls_inexistentes", [])) + len(r.get("urls_suspeitas", []))
        for r in resultados
        if r.get("urls_inexistentes") or r.get("urls_suspeitas")
    }

    saida = Path(args.saida).expanduser().resolve()
    saida.parent.mkdir(parents=True, exist_ok=True)

    pacote = {
        "rodada": args.rodada,
        "modo": modo,
        "quando": datetime.now().isoformat(timespec="seconds"),
        "duracao_s": duracao,
        "custo_real_usd": custo_total,
        "custo_estimado_usd": estimativa["teto_usd"],
        "agentes_ok": ok,
        "agentes_com_falha": falhos,
        "agentes_sem_fontes": sem_fontes,
        "agentes_com_url_falsa": com_url_falsa,
        "resultados": resultados,
    }
    saida.write_text(json.dumps(pacote, ensure_ascii=False, indent=2), encoding="utf-8")

    # Um .md por agente, para leitura seletiva sem carregar o JSON inteiro.
    for r in resultados:
        if r["erro"]:
            continue
        md = saida.parent / f"{saida.stem}_{r['slot']}.md"
        aviso = (
            "\n> ALERTA: este agente não devolveu nenhuma URL. Provavelmente respondeu de\n"
            "> memória, sem pesquisar. Não usar como confirmação de nada.\n"
            if r.get("sem_fontes") else ""
        )
        if r.get("urls_problematicas"):
            problemas_md = r["urls_problematicas"]
            duras_md = {u: d for u, d in problemas_md.items() if d["estado"] in FALHAS_DURAS}
            fracas_md = {u: d for u, d in problemas_md.items() if u not in duras_md}
            if duras_md:
                linhas_p = "\n".join(
                    f"> - [{d['estado']}] {u} — {'; '.join(d['motivos'][:2])}"
                    for u, d in list(duras_md.items())[:15]
                )
                aviso += (
                    f"\n> ALERTA DE FONTE: {len(duras_md)} URLs não existem ou são suspeitas.\n"
                    "> Nada que se apoie apenas nelas entra no relatório sem passar pela\n"
                    "> rodada 2.\n>\n"
                    f"{linhas_p}\n"
                )
            if fracas_md:
                linhas_f = "\n".join(
                    f"> - [{d['estado']}] {u} — {'; '.join(d['motivos'][:2])}"
                    for u, d in list(fracas_md.items())[:15]
                )
                aviso += (
                    f"\n> SINAL FRACO: {len(fracas_md)} URLs existem e a conferência de assunto\n"
                    "> não concluiu. Vale como aviso de leitura, e não desqualifica o agente:\n"
                    "> a página pode estar atrás de muro de acesso, ser documento sem HTML ou\n"
                    "> tratar do tema com outro vocabulário.\n>\n"
                    f"{linhas_f}\n"
                )
            if r.get("afirmacoes_a_revalidar"):
                blocos = "\n\n".join(
                    f"**{i}.** [{a['estado']}] {a['url']}"
                    + (f" · trecho cita {a['citacoes_no_trecho']} fontes de uma vez, então "
                       "sustenta menos do que parece"
                       if a.get("citacoes_no_trecho") else "")
                    + f"\n\n> {a['trecho']}"
                    for i, a in enumerate(r["afirmacoes_a_revalidar"], 1)
                )
                aviso += (
                    "\n### Afirmações a revalidar na rodada 2\n\n"
                    "Cada trecho abaixo se apoiava numa fonte que não passou. Pode ser verdadeiro "
                    "com a citação errada, então vai para verificação em vez de descarte. "
                    "Quem cita não valida a própria citação.\n\n"
                    f"{blocos}\n"
                )
        md.write_text(
            f"# Agente {r['slot']} — {r['rotulo']}\n\n"
            f"Modelo: `{r['modelo']}` · {r['duracao_s']}s · {len(r['urls'])} URLs · US$ {r['custo_usd']:.4f}\n"
            f"{aviso}\n"
            f"---\n\n{r['conteudo']}\n\n"
            f"---\n\n## URLs capturadas\n\n"
            + ("\n".join(f"- {u}" for u in r["urls"]) if r["urls"] else "(nenhuma)")
            + "\n",
            encoding="utf-8",
        )

    log("FIM", f"{duracao}s · ok={ok or 'nenhum'} · falhas={falhos or 'nenhuma'}")

    # Composição efetiva depois da rodada. O aviso da largada conta os motores escolhidos,
    # e o que sustenta consenso é o que sobrou de pé: agente que falhou ou respondeu sem
    # fonte nenhuma não arbitra contradição. Em 12/08 uma pesquisa começou com três e
    # terminou com dois sem que nada dissesse isso.
    elegiveis = [r["slot"] for r in resultados if not r["erro"] and not r.get("sem_fontes")]
    if len(elegiveis) < len(ativos):
        log("FIM", f"COMPOSIÇÃO EFETIVA: {len(elegiveis)} de {len(ativos)} motores continuam "
                   f"elegíveis para sustentar consenso: {elegiveis or 'nenhum'}")
    if len(elegiveis) < 2:
        log("FIM", "ATENÇÃO: menos de dois motores elegíveis. Não há validação cruzada nesta rodada.")
    elif len(elegiveis) == 2:
        log("FIM", "ATENÇÃO: dois motores elegíveis. Contradição entre eles fica sem árbitro na rodada 2.")

    if sem_fontes:
        log("FIM", f"ALERTA: agentes sem nenhuma URL (não valem como confirmação): {sem_fontes}")
    if com_url_falsa:
        log("FIM", f"ALERTA DE FONTE: URLs inexistentes ou suspeitas por agente: {com_url_falsa}")
        log("FIM", "Confira o topo do markdown de cada agente antes de usar qualquer afirmação.")
    log("FIM", f"custo real US$ {custo_total:.4f} (teto estimado US$ {estimativa['teto_usd']:.2f})")
    log("FIM", f"JSON: {saida}")
    for r in resultados:
        if not r["erro"]:
            caminho_md = saida.parent / f"{saida.stem}_{r['slot']}.md"
            log("FIM", f"markdown do agente {r['slot']}: {caminho_md}")

    if falhos:
        for r in resultados:
            if r["erro"]:
                log("FIM", f"agente {r['slot']} falhou: {r['erro'][:300]}")


if __name__ == "__main__":
    main()
