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


# A verificação de fonte mora em verificacao.py, e roda como passo separado (verificar.py).
# Coletar e verificar na mesma execução obrigava a pagar uma pesquisa nova a cada ajuste de
# régua — foi o que consumiu 12 e 13/08/2026.
from verificacao import FALHAS_DURAS, SINAIS_FRACOS  # noqa: E402,F401
import verificacao  # noqa: E402

verificacao.log = log



def chamar_agente(slot, agente, prompt, max_tokens, max_results, timeout, chave):
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
        "tokens_in": 0,
        "tokens_out": 0,
        "custo_usd": 0.0,
        "duracao_s": 0.0,
        "sem_fontes": False,
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

        # A verificação de fonte não acontece mais aqui. Ela lê este JSON depois, pelo
        # verificar.py, e grava o veredito ao lado — o que permite reverificar sem
        # recomprar a pesquisa.

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

    log("INÍCIO", f"rodada={args.rodada} · modo={modo} · max_tokens do modo={max_tokens} · timeout={timeout}s")

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
                timeout, chave
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
        md.write_text(
            f"# Agente {r['slot']} — {r['rotulo']}\n\n"
            f"Modelo: `{r['modelo']}` · {r['duracao_s']}s · {len(r['urls'])} URLs · US$ {r['custo_usd']:.4f}\n"
            f"{aviso}\n"
            f"\n> A verificação de fonte deste material roda em separado, pelo verificar.py,\n"
            f"> e o veredito fica em `{saida.stem}_verificacao.json` e `{saida.stem}_decisoes.md`.\n"
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
