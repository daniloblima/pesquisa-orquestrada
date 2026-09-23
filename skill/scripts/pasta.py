#!/usr/bin/env python3
"""Onde ficam as pesquisas. Única fonte dessa resposta para todos os scripts.

Ordem de busca:
  1. variável PESQUISA_SAIDA no ambiente
  2. PESQUISA_SAIDA em ~/.claude/.env (o mesmo arquivo da chave do OpenRouter)
  3. "saida_padrao" no config.json da skill
  4. outputs/ ao lado da pasta skill/, dentro do repositório (ignorada pelo git)

Uso:
  python3 pasta.py              mostra a pasta e se ela foi escolhida pelo usuário
  python3 pasta.py --definir X  grava PESQUISA_SAIDA=X em ~/.claude/.env e cria a pasta
"""
import argparse
import json
import os
from pathlib import Path

RAIZ_SKILL = Path(__file__).resolve().parent.parent
ENV = Path.home() / ".claude" / ".env"


def _do_env():
    if not ENV.exists():
        return ""
    for linha in ENV.read_text(encoding="utf-8").splitlines():
        if linha.strip().startswith("PESQUISA_SAIDA="):
            return linha.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def resolver():
    """Devolve (pasta, origem). origem: 'ambiente', 'env', 'config' ou 'padrão'."""
    valor = os.environ.get("PESQUISA_SAIDA", "").strip()
    if valor:
        return Path(valor).expanduser().resolve(), "ambiente"
    valor = _do_env()
    if valor:
        return Path(valor).expanduser().resolve(), "env"
    cfg = json.loads((RAIZ_SKILL / "config.json").read_text(encoding="utf-8"))
    valor = (cfg.get("saida_padrao") or "").strip()
    if valor:
        return Path(valor).expanduser().resolve(), "config"
    return RAIZ_SKILL.parent / "outputs", "padrão"


def raiz_saida(criar=True):
    pasta, _ = resolver()
    if criar:
        pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def definir(caminho):
    pasta = Path(caminho).expanduser().resolve()
    pasta.mkdir(parents=True, exist_ok=True)
    ENV.parent.mkdir(parents=True, exist_ok=True)
    linhas = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    linhas = [l for l in linhas if not l.strip().startswith("PESQUISA_SAIDA=")]
    linhas.append(f"PESQUISA_SAIDA={pasta}")
    ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    os.chmod(ENV, 0o600)
    return pasta


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Mostra ou define a pasta das pesquisas.")
    p.add_argument("--definir", metavar="CAMINHO", help="grava a pasta em ~/.claude/.env")
    a = p.parse_args()
    if a.definir:
        print(f"pasta definida: {definir(a.definir)}")
    else:
        pasta, origem = resolver()
        escolhida = "sim" if origem in ("ambiente", "env", "config") else "não"
        print(f"pasta: {pasta}")
        print(f"escolhida pelo usuário: {escolhida} (origem: {origem})")
