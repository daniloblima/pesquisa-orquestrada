#!/usr/bin/env python3
"""
motores.py — mantém o catálogo de motores de pesquisa do OpenRouter.

Na primeira execução classifica o catálogo inteiro e grava em catalogo-motores.json.
Nas seguintes consulta a API e trabalha apenas o diferencial: modelos novos entram
para classificação, modelos que sumiram são marcados. O que já foi classificado fica
como está, inclusive as correções feitas à mão.

Uso:
    python3 motores.py                 # atualiza o catálogo e mostra o diferencial
    python3 motores.py --listar        # mostra os candidatos já classificados
    python3 motores.py --reclassificar # joga fora a classificação e refaz do zero
"""

import argparse
import json
import urllib.request
from datetime import date
from pathlib import Path

RAIZ_SKILL = Path(__file__).resolve().parent.parent
CATALOGO = RAIZ_SKILL / "catalogo-motores.json"
API = "https://openrouter.ai/api/v1/models"

# Famílias com índice de busca próprio. A independência entre motores vem daqui.
FAMILIAS = {
    "perplexity/": "Perplexity",
    "openai/": "OpenAI",
    "google/": "Google",
    "x-ai/": "xAI",
    "anthropic/": "Anthropic",
}

# Não serve como motor de pesquisa: outros formatos, peso aberto (roda em provedor
# terceiro, portanto sem o índice da família) e gerações antigas.
DESCARTAR = (
    "-image", "-codex", "-nano", "-lite", "embedding", "tts", "whisper",
    "-chat", "guard", "moderation", "relace", "build", "audio",
    "gemma", "gpt-oss", "gpt-3.5", "gpt-4", "claude-3", "gemini-2", "o1-", "o3-mini",
    "lyria", "veo", "imagen", "sora",   # áudio, vídeo e imagem
)

# Sinais de que o modelo faz pesquisa profunda, não só uma consulta e uma resposta.
SINAIS_DEEP = ("deep-research", "multi-agent", "pro-search", "sonar")


def log(msg):
    print(msg, flush=True)


def preco(m, campo):
    try:
        return round(float(m.get("pricing", {}).get(campo, 0) or 0) * 1e6, 4)
    except (TypeError, ValueError):
        return 0.0


def familia(mid):
    for prefixo, nome in FAMILIAS.items():
        if mid.startswith(prefixo):
            return nome
    return None


def classificar(m):
    """Classe do modelo. Heurística, revisável à mão no catálogo depois."""
    mid = m["id"]
    fam = familia(mid)

    # Preço de saída zerado indica modelo que não gera texto cobrado por token —
    # imagem, áudio ou embedding. Não serve como motor.
    if any(x in mid for x in DESCARTAR) or preco(m, "completion") == 0:
        classe = "descartado"
    elif not fam:
        classe = "sem-busca"       # família sem índice próprio no OpenRouter
    elif any(s in mid for s in SINAIS_DEEP):
        classe = "deep-research"
    else:
        classe = "busca-nativa"

    return {
        "familia": fam or mid.split("/")[0],
        "classe": classe,
        "in": preco(m, "prompt"),
        "out": preco(m, "completion"),
        "contexto": m.get("context_length") or 0,
        "testado": False,
        "notas": "",
        "visto_em": str(date.today()),
    }


def carregar():
    if CATALOGO.exists():
        return json.loads(CATALOGO.read_text(encoding="utf-8"))
    return {"atualizado_em": None, "modelos": {}}


def main():
    p = argparse.ArgumentParser(description="Catálogo de motores de pesquisa.")
    p.add_argument("--listar", action="store_true", help="Só mostra os candidatos já classificados.")
    p.add_argument("--reclassificar", action="store_true", help="Refaz a classificação do zero.")
    args = p.parse_args()

    cat = {"atualizado_em": None, "modelos": {}} if args.reclassificar else carregar()
    conhecidos = cat["modelos"]

    if not args.listar:
        log(f"consultando {API} ...")
        with urllib.request.urlopen(API, timeout=60) as r:
            dados = json.loads(r.read().decode("utf-8"))["data"]
        vivos = {m["id"] for m in dados}

        # O diferencial: só o que ainda não foi classificado passa pela heurística.
        novos = [m for m in dados if m["id"] not in conhecidos]
        for m in novos:
            conhecidos[m["id"]] = classificar(m)

        # Preço muda sem o modelo mudar de nome, então vale reler sempre.
        mudou_preco = []
        for m in dados:
            reg = conhecidos[m["id"]]
            p_in, p_out = preco(m, "prompt"), preco(m, "completion")
            if (reg["in"], reg["out"]) != (p_in, p_out) and m["id"] not in {x["id"] for x in novos}:
                mudou_preco.append((m["id"], reg["in"], reg["out"], p_in, p_out))
                reg["in"], reg["out"] = p_in, p_out
            reg["visto_em"] = str(date.today())

        sumidos = [mid for mid in conhecidos if mid not in vivos and not conhecidos[mid].get("sumiu")]
        for mid in sumidos:
            conhecidos[mid]["sumiu"] = str(date.today())

        cat["atualizado_em"] = str(date.today())
        CATALOGO.write_text(json.dumps(cat, ensure_ascii=False, indent=2), encoding="utf-8")

        primeira = novos and len(novos) == len(conhecidos)
        log(f"\n{'PRIMEIRA CLASSIFICAÇÃO' if primeira else 'DIFERENCIAL'}")
        log(f"  {len(conhecidos)} modelos no catálogo · {len(novos)} novos · "
            f"{len(sumidos)} sumiram · {len(mudou_preco)} mudaram de preço")

        interessantes = [m for m in novos
                         if conhecidos[m["id"]]["classe"] in ("deep-research", "busca-nativa")]
        if interessantes:
            log("\n  NOVOS CANDIDATOS A MOTOR")
            for m in sorted(interessantes, key=lambda x: x["id"]):
                r = conhecidos[m["id"]]
                log(f"    {m['id']:44} {r['classe']:14} in {r['in']:6.2f}  out {r['out']:6.2f}")
            log("\n    Nenhum foi testado ainda. Antes de promover a slot, rode uma pesquisa em")
            log("    modo rapida e confira no log se ele traz URLs.")
        elif novos:
            log(f"\n  Os {len(novos)} novos são descartados ou sem busca nativa. Nada a fazer.")

        if mudou_preco:
            log("\n  MUDANÇA DE PREÇO")
            for mid, ai, ao, ni, no in mudou_preco:
                log(f"    {mid:44} in {ai:.2f}→{ni:.2f}  out {ao:.2f}→{no:.2f}")

        if sumidos:
            log("\n  SUMIRAM DO CATÁLOGO")
            for mid in sumidos:
                log(f"    {mid}")

    # Conferência do que está configurado
    cfg = json.loads((RAIZ_SKILL / "config.json").read_text(encoding="utf-8"))
    log("\n" + "=" * 92)
    log("EM USO AGORA\n")
    for m in cfg.get("motores", []):
        reg = conhecidos.get(m["modelo"])
        marca = "padrão" if m.get("padrao") else "opcional"
        if not reg:
            log(f"  {m['id']:12} {m['modelo']:42} não está no catálogo  ({marca})")
        elif reg.get("sumiu"):
            log(f"  {m['id']:12} {m['modelo']:42} SUMIU DO CATÁLOGO em {reg['sumiu']}, precisa trocar")
        else:
            log(f"  {m['id']:12} {m['modelo']:42} {reg['classe']:14} "
                f"in {reg['in']:6.2f}  out {reg['out']:6.2f}  "
                f"~US$ {m.get('custo_tipico_usd', 0):.2f}  ({marca})")

    log("\n  Só os marcados como padrão rodam quando --motores é omitido.")

    log(f"""
COMO USAR ISTO

  O catálogo fica em {CATALOGO.name}, ao lado do config. A classificação é heurística
  e pode ser corrigida à mão: mude "classe", marque "testado": true e escreva em "notas"
  o que você mediu. A próxima execução respeita o que já está lá.

  Para acrescentar um motor: um item novo na lista "motores" do config.json, com um id
  curto e "padrao": false, mais a entrada correspondente em precos_por_milhao_usd. Não
  há teto de quantidade e nada mais precisa ser mexido. Depois rode uma pesquisa em modo
  rapida com --motores <id> e confira se ele traz URLs. Modelo que volta sem URL não
  está buscando, e nesse estado não serve para nada aqui.

  Independência antes de preço: um índice por família. Dois motores da mesma família
  leem as mesmas páginas, e aí a concordância entre eles não valida nada.
""")


if __name__ == "__main__":
    main()
