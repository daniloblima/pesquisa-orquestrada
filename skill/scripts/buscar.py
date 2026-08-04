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
    log("CONFIG", f"lendo {CONFIG_PATH}")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    log("CONFIG", f"agentes: {', '.join(a['modelo'] for a in cfg['agentes'].values())}")
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


def resolver_redirects(urls, slot):
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

# O modelo às vezes confessa a invenção no próprio texto, ao lado do link.
MARCADORES_SUBSTITUICAO = (
    "substitu", "aproximad", "ilustrativ", "exemplo de url", "url fictícia",
    "não foi possível recuperar", "link genérico", "placeholder", "hipotétic",
)


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
CABECALHOS_FONTES = ("fontes consultadas", "fontes:", "referências", "referencias", "sources")


def contexto_da_url(url, texto, janela=700):
    """Devolve o trecho onde a URL é usada como prova.

    Uma fonte reprovada não pode simplesmente sumir: a afirmação que ela sustentava pode
    ser verdadeira, com a citação errada. Sem recuperar o trecho, o descarte apaga
    informação boa em silêncio e ninguém fica sabendo.
    """
    if not texto or url not in texto:
        return None

    # Onde começa a lista de fontes. Ocorrência depois disso é item de lista, não uso.
    minusculo = texto.lower()
    corte = len(texto)
    for cab in CABECALHOS_FONTES:
        pos = minusculo.rfind(cab)
        if pos > 0:
            corte = min(corte, pos)

    inicio_busca = 0
    while True:
        pos = texto.find(url, inicio_busca)
        if pos < 0:
            return None
        if pos < corte:
            break
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


def _sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower())
                   if unicodedata.category(c) != "Mn")


def _texto_do_html(html):
    """Título, descrição e começo do corpo. Regex basta: não é para renderizar a página,
    é só para saber do que ela trata."""
    partes = []
    for padrao in (r"<title[^>]*>(.*?)</title>",
                   r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
                   r'<meta[^>]+property=["\']og:(?:title|description)["\'][^>]+content=["\'](.*?)["\']',
                   r"<h1[^>]*>(.*?)</h1>"):
        partes += re.findall(padrao, html, re.I | re.S)

    corpo = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    corpo = re.sub(r"<[^>]+>", " ", corpo)
    partes.append(corpo[:4000])

    texto = " ".join(partes)
    texto = re.sub(r"&[a-z]+;|&#\d+;", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def verificar_tema(problemas, urls, termos, slot):
    """Confere se a página trata do tema da pesquisa.

    Existir não é sustentar. Uma URL pode responder 200 e falar de outra coisa — é o que
    acontece quando o modelo acerta o domínio e inventa o caminho, ou quando cita a home
    de um site em vez do artigo. Não julga se a página prova a afirmação: só se ela é
    sobre o assunto. O julgamento fino continua sendo trabalho de leitura.
    """
    uteis = [t for t in (_sem_acento(x).strip() for x in termos) if len(t) >= 4]
    if not uteis or not urls:
        return

    alvos = [u for u in urls if problemas.get(u, {}).get("estado") not in
             ("inexistente", "inventada", "removida")][:LIMITE_TEMA]
    if not alvos:
        return

    log(f"AGENTE {slot}", f"conferindo se {len(alvos)} páginas tratam do tema ({len(uteis)} termos)")

    def checar(u):
        try:
            req = urllib.request.Request(u, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "Range": "bytes=0-120000",
            })
            with urllib.request.urlopen(req, timeout=20) as r:
                tipo = (r.headers.get("Content-Type") or "").lower()
                bruto = r.read(120000)
        except Exception as e:
            return u, None, f"{type(e).__name__}"

        # PDF e afins não têm HTML para ler. Não dá para concluir, e não se acusa.
        if "html" not in tipo and "text" not in tipo:
            return u, None, f"tipo {tipo.split(';')[0] or 'desconhecido'}"

        texto = _texto_do_html(bruto.decode("utf-8", errors="ignore"))
        if len(texto) < 250:
            return u, None, "página quase sem texto legível"

        alvo = _sem_acento(texto)
        achados = [t for t in uteis if re.search(rf"\b{re.escape(t)}", alvo)]
        return u, achados, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for u, achados, motivo_nulo in ex.map(checar, alvos):
            if achados is None:
                continue  # inconclusivo: nunca vira acusação
            if not achados:
                reg = problemas.setdefault(u, {"estado": "ok", "motivos": []})
                reg["estado"] = "fora do tema"
                reg["motivos"].append(
                    "a página existe mas não menciona nenhum termo central da pesquisa")

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

        resultado["conteudo"] = conteudo
        resultado["urls"] = resolver_redirects(extrair_urls(conteudo, msg.get("annotations")), slot)
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
            sem_contexto = 0
            for u, reg in problemas.items():
                reg["contexto"] = contexto_da_url(u, conteudo)
                if not reg["contexto"]:
                    sem_contexto += 1
            if problemas:
                log(f"AGENTE {slot}",
                    f"{len(problemas) - sem_contexto} de {len(problemas)} fontes reprovadas "
                    f"têm o trecho que sustentavam; {sem_contexto} aparecem só na lista de fontes")
            if sem_contexto and sem_contexto == len(problemas):
                resultado["reprovadas_sem_rastro"] = True
                log(f"AGENTE {slot}",
                    "ALERTA GRAVE: todas as fontes reprovadas deste agente aparecem apenas na "
                    "lista final, sem trecho associado. Não dá para saber o que se apoiava "
                    "nelas, então NADA deste agente pode contar como confirmação.")

            resultado["urls_problematicas"] = problemas
            resultado["afirmacoes_a_revalidar"] = [
                {"url": u, "estado": r["estado"], "motivos": r["motivos"], "trecho": r["contexto"]}
                for u, r in problemas.items() if r.get("contexto")
            ]
            resultado["urls_inexistentes"] = [
                u for u, r in problemas.items() if r["estado"] == "inexistente"
            ]
            resultado["urls_suspeitas"] = [
                u for u, r in problemas.items() if r["estado"] in ("suspeita", "fora do tema")
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

def montar_prompts(args, cfg):
    """Devolve {slot: prompt|None} a partir de --prompt-file ou --prompts-file."""
    slots = list(cfg["agentes"].keys())

    if args.prompts_file:
        with open(args.prompts_file, encoding="utf-8") as f:
            bruto = json.load(f)
        prompts = {s: (bruto.get(s) or None) for s in slots}
        desconhecidos = set(bruto) - set(slots)
        if desconhecidos:
            log("PROMPTS", f"ATENÇÃO: slots ignorados por não existirem no config: {sorted(desconhecidos)}")
    else:
        with open(args.prompt_file, encoding="utf-8") as f:
            texto = f.read()
        prompts = {s: texto for s in slots}

    if args.agentes:
        pedidos = {s.strip().upper() for s in args.agentes.split(",") if s.strip()}
        prompts = {s: (p if s in pedidos else None) for s, p in prompts.items()}

    for s in slots:
        estado = f"{len(prompts[s])} chars" if prompts[s] else "não será chamado"
        log("PROMPTS", f"slot {s}: {estado}")
    return prompts


def estimar(prompts, cfg, max_tokens):
    """Faixa de custo, não número único.

    Cada motor tem perfil de input próprio e medido: o que recebe os resultados de
    busca no prompt chega a dezenas de milhares de tokens; o que pesquisa do lado do
    provedor recebe quase nada e cobra por busca. Um valor médio para todos erra por
    fator de 2 a 3 nas duas direções.
    """
    precos = cfg.get("precos_por_milhao_usd", {})
    fracao = cfg.get("fracao_saida_tipica", 0.55)

    minimo, teto, detalhe = 0.0, 0.0, {}
    for s, prompt in prompts.items():
        if not prompt:
            continue
        agente = cfg["agentes"][s]
        p = precos.get(
            agente["modelo"],
            {"in": 3.0, "out": 15.0, "taxa_fixa": 0.0, "tokens_input_busca": 20000},
        )

        tokens_in = len(prompt) / 3.5 + p.get("tokens_input_busca", 20000)  # ~3,5 chars por token
        base = (tokens_in / 1e6) * p["in"] + p.get("taxa_fixa", 0.0)
        c_teto = base + (max_tokens / 1e6) * p["out"]
        c_min = base + (max_tokens * fracao / 1e6) * p["out"]

        detalhe[s] = {"tipico": round(c_min, 4), "teto": round(c_teto, 4)}
        minimo += c_min
        teto += c_teto

    log("CUSTO", f"estimado entre US$ {minimo:.2f} e US$ {teto:.2f} · por agente: {detalhe}")
    if any(cfg["agentes"][s].get("busca_nativa") for s, pr in prompts.items() if pr):
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
    p.add_argument("--agentes", default=None, help="Subconjunto, ex: A,C")
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
    log("INÍCIO", f"rodada={args.rodada} · modo={modo} · max_tokens={max_tokens} · timeout={timeout}s")
    if termos:
        log("INÍCIO", f"conferência de tema ligada: {', '.join(termos)}")
    else:
        log("INÍCIO", "sem --termos: as páginas não serão conferidas quanto ao assunto")

    prompts = montar_prompts(args, cfg)
    ativos = [s for s, pr in prompts.items() if pr]
    if not ativos:
        raise SystemExit("ERRO: nenhum agente tem prompt. Nada a fazer.")

    estimativa = estimar(prompts, cfg, max_tokens)
    if args.estimar:
        print(json.dumps(estimativa, ensure_ascii=False, indent=2))
        return

    chave = carregar_chave()
    log("RODADA", f"disparando {len(ativos)} agentes em paralelo: {', '.join(ativos)}")
    if "A" in ativos and cfg["agentes"]["A"].get("busca_nativa"):
        log("RODADA", "o agente A faz busca profunda e pode levar de 3 a 10 minutos")

    inicio = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ativos)) as executor:
        futuros = {
            executor.submit(
                chamar_agente, s, cfg["agentes"][s], prompts[s], max_tokens, max_results,
                timeout, chave, not args.sem_verificar_urls, termos
            ): s
            for s in ativos
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
            linhas_p = "\n".join(
                f"> - [{d['estado']}] {u} — {'; '.join(d['motivos'][:2])}"
                for u, d in list(r["urls_problematicas"].items())[:15]
            )
            aviso += (
                f"\n> ALERTA DE FONTE: {len(r['urls_problematicas'])} URLs não passaram na\n"
                "> verificação. Nada que se apoie apenas nelas entra no relatório sem passar\n"
                "> pela rodada 2.\n>\n"
                f"{linhas_p}\n"
            )
            if r.get("afirmacoes_a_revalidar"):
                blocos = "\n\n".join(
                    f"**{i}.** [{a['estado']}] {a['url']}\n\n> {a['trecho']}"
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
