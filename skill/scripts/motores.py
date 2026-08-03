#!/usr/bin/env python3
"""
motores.py — consulta o catálogo do OpenRouter e mostra os candidatos a motor de pesquisa.

O catálogo muda rápido: modelo sai, preço muda, geração nova aparece. Rode isto antes de
decidir trocar um motor, e sempre que um agente começar a falhar sem explicação.

Só considera famílias com busca nativa no OpenRouter — Anthropic, Google, OpenAI, Perplexity
e xAI. Modelo sem busca nativa depende de motor externo, e aí os agentes passam a ler as
mesmas páginas, o que destrói a independência entre eles.

Uso:
    python3 motores.py                 # candidatos + conferência do que está configurado
    python3 motores.py --todos         # não filtra por preço
"""

import argparse
import json
import urllib.request
from pathlib import Path

RAIZ_SKILL = Path(__file__).resolve().parent.parent
API = "https://openrouter.ai/api/v1/models"

# Famílias com índice de busca próprio. A independência entre motores vem daqui.
FAMILIAS = {
    "perplexity/": "Perplexity",
    "openai/": "OpenAI",
    "google/": "Google",
    "x-ai/": "xAI",
    "anthropic/": "Anthropic",
}

# Ruído que nunca serve como motor de pesquisa aqui. Além dos formatos que não são de
# texto, exclui modelos de peso aberto — que rodam em provedor terceiro e por isso não
# têm o índice de busca da família — e gerações antigas.
EXCLUIR = (
    "-image", "-codex", "-nano", "-lite", "embedding", "tts", "whisper",
    "-chat", "guard", "moderation", "relace", "build", "audio",
    "gemma", "gpt-oss",                      # peso aberto, sem busca nativa
    "gpt-3.5", "gpt-4", "claude-3", "gemini-2", "o1-", "o3-mini",   # gerações antigas
)


def preco(m, campo):
    try:
        return float(m.get("pricing", {}).get(campo, 0) or 0) * 1e6
    except (TypeError, ValueError):
        return 0.0


def familia(mid):
    for prefixo, nome in FAMILIAS.items():
        if mid.startswith(prefixo):
            return nome
    return None


def main():
    p = argparse.ArgumentParser(description="Candidatos a motor de pesquisa no OpenRouter.")
    p.add_argument("--todos", action="store_true", help="Não filtra por preço de saída.")
    p.add_argument("--teto-saida", type=float, default=15.0,
                   help="Preço máximo de saída por milhão de tokens (padrão 15).")
    args = p.parse_args()

    print(f"consultando {API} ...\n")
    with urllib.request.urlopen(API, timeout=60) as r:
        dados = json.loads(r.read().decode("utf-8"))["data"]

    cfg = json.loads((RAIZ_SKILL / "config.json").read_text(encoding="utf-8"))
    em_uso = {a["modelo"]: s for s, a in cfg["agentes"].items()}
    catalogo = {m["id"] for m in dados}

    candidatos = []
    for m in dados:
        mid = m["id"]
        fam = familia(mid)
        if not fam or any(x in mid for x in EXCLUIR):
            continue
        p_out = preco(m, "completion")
        if not args.todos and (p_out > args.teto_saida or p_out == 0):
            continue
        candidatos.append({
            "id": mid, "familia": fam,
            "in": preco(m, "prompt"), "out": p_out,
            "ctx": m.get("context_length") or 0,
            "usando": em_uso.get(mid),
        })

    candidatos.sort(key=lambda c: (c["familia"], c["out"]))

    print(f"{'MODELO':45} {'FAMÍLIA':11} {'IN':>7} {'OUT':>7} {'CONTEXTO':>10}  EM USO")
    print("-" * 96)
    fam_ant = None
    for c in candidatos:
        if c["familia"] != fam_ant:
            if fam_ant:
                print()
            fam_ant = c["familia"]
        marca = f"slot {c['usando']}" if c["usando"] else ""
        print(f"{c['id']:45} {c['familia']:11} {c['in']:7.2f} {c['out']:7.2f} "
              f"{c['ctx']:>10,}  {marca}")

    print("\n" + "=" * 96)
    print("CONFERÊNCIA DO QUE ESTÁ CONFIGURADO\n")
    problema = False
    for slot, a in cfg["agentes"].items():
        if a["modelo"] in catalogo:
            m = next(x for x in dados if x["id"] == a["modelo"])
            print(f"  slot {slot}: {a['modelo']} — no catálogo, "
                  f"in {preco(m,'prompt'):.2f} out {preco(m,'completion'):.2f}")
        else:
            problema = True
            print(f"  slot {slot}: {a['modelo']} — SUMIU DO CATÁLOGO, precisa trocar")

    if problema:
        print("\n  Edite skill/config.json e ajuste também precos_por_milhao_usd.")

    print("""
COMO ESCOLHER

  Independência antes de preço. Três motores de famílias diferentes valem mais que
  cinco da mesma, porque o que dá validação é ler páginas diferentes, não gerar
  mais texto sobre as mesmas.

  Preço de saída pesa mais que o de entrada em modelo que escreve relatório longo,
  exceto onde a cobrança é por busca — aí o preço por token engana e só a medição
  real resolve. Ver o CHANGELOG do projeto.

  Ao trocar um motor: atualize modelo e precos_por_milhao_usd no config.json, rode
  uma pesquisa em modo rapida e confira no log se ele traz URLs. Modelo que volta
  sem URL não está buscando, e nesse estado não serve para nada aqui.
""")


if __name__ == "__main__":
    main()
