#!/usr/bin/env python3
"""
memoria.py — o que a pesquisa já estabeleceu, uma linha por afirmação.

Existe para que a quarta pesquisa não pague de novo pelo que a primeira descobriu, e para
que ninguém contradiga o próprio acervo sem perceber.

Formato JSONL, uma afirmação por linha, consultado por busca e nunca lido inteiro. O erro
que se evita aqui tem nome e data: o arquivo de conexões do brain v2 chegou a duas mil
linhas e consumia o orçamento de contexto numa única consulta. Documento longo é documento
morto.

Porta estreita na entrada: só entra afirmação sustentada por duas origens independentes ou
validada pelo Danilo. O resto continua vivendo no relatório da pesquisa.

Uso:
    python3 memoria.py buscar "minigeração 75 kW"
    python3 memoria.py inserir --fato "..." --valor "75 kW" --fonte URL --pesquisa PASTA \\
        --origens 2 --vale-ate 2027-12-31 --invalida-se "REN 1.000 for revista"
    python3 memoria.py listar --tema energia
"""

import argparse
import json
import sys
import unicodedata
from datetime import date
from pathlib import Path

RAIZ_SKILL = Path(__file__).resolve().parent.parent


def caminho_memoria():
    cfg = json.loads((RAIZ_SKILL / "config.json").read_text(encoding="utf-8"))
    configurada = (cfg.get("saida_padrao") or "").strip()
    raiz = Path(configurada).expanduser().resolve() if configurada else RAIZ_SKILL.parent / "outputs"
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz / "memoria.jsonl"


def _sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower())
                   if unicodedata.category(c) != "Mn")


def carregar():
    arq = caminho_memoria()
    if not arq.exists():
        return []
    itens = []
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha:
            try:
                itens.append(json.loads(linha))
            except Exception:
                pass
    return itens


def inserir(args):
    if args.origens < 2 and not args.validado:
        raise SystemExit(
            "ERRO: a porta é estreita de propósito. Só entra afirmação com duas origens "
            "independentes ou com --validado, que significa que o Danilo conferiu.\n"
            "O resto continua no relatório da pesquisa, que não se apaga."
        )
    item = {
        "fato": args.fato,
        "valor": args.valor,
        "tema": args.tema,
        "fonte": args.fonte,
        "origens_independentes": args.origens,
        "validado_por_humano": bool(args.validado),
        "pesquisa": args.pesquisa,
        "data": args.data or str(date.today()),
        "vale_ate": args.vale_ate,
        "invalida_se": args.invalida_se,
    }
    with open(caminho_memoria(), "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"gravado em {caminho_memoria()}")
    print(json.dumps(item, ensure_ascii=False, indent=2))


def buscar(args):
    termos = [_sem_acento(t) for t in args.termos if t.strip()]
    achados = []
    for item in carregar():
        alvo = _sem_acento(" ".join(str(item.get(k) or "") for k in
                                    ("fato", "valor", "tema", "fonte", "pesquisa")))
        if all(t in alvo for t in termos):
            achados.append(item)

    if not achados:
        print("nada na memória sobre isso. A pesquisa começa do zero.")
        return
    print(f"{len(achados)} afirmação(ões) já estabelecida(s):\n")
    hoje = str(date.today())
    for i in sorted(achados, key=lambda x: x.get("data") or "", reverse=True):
        marca = ""
        if i.get("vale_ate") and i["vale_ate"] < hoje:
            marca = "  [VENCIDA — reconferir]"
        selo = "validado" if i.get("validado_por_humano") else f"{i.get('origens_independentes')} origens"
        print(f"- {i['fato']}")
        print(f"    valor: {i.get('valor') or '—'} · {selo} · {i.get('data')}{marca}")
        print(f"    fonte: {i.get('fonte') or '—'}")
        if i.get("invalida_se"):
            print(f"    invalida-se se: {i['invalida_se']}")
        print(f"    pesquisa: {i.get('pesquisa') or '—'}")
        print()


def listar(args):
    itens = carregar()
    if args.tema:
        alvo = _sem_acento(args.tema)
        itens = [i for i in itens if alvo in _sem_acento(i.get("tema") or "")]
    print(f"{len(itens)} afirmações na memória · arquivo: {caminho_memoria()}")
    for i in itens[-(args.limite):]:
        print(f"- [{i.get('data')}] {i['fato']} ({i.get('valor') or '—'})")


def main():
    p = argparse.ArgumentParser(description="Memória de afirmações verificadas.")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("buscar", help="Procura antes de disparar uma pesquisa nova")
    b.add_argument("termos", nargs="+")
    b.set_defaults(func=buscar)

    i = sub.add_parser("inserir", help="Grava uma afirmação estabelecida")
    i.add_argument("--fato", required=True)
    i.add_argument("--valor", default="")
    i.add_argument("--tema", default="")
    i.add_argument("--fonte", required=True)
    i.add_argument("--pesquisa", required=True, help="Pasta da pesquisa que estabeleceu")
    i.add_argument("--origens", type=int, default=0, help="Origens independentes que sustentam")
    i.add_argument("--validado", action="store_true", help="O Danilo conferiu na fonte primária")
    i.add_argument("--data", default=None)
    i.add_argument("--vale-ate", default=None, dest="vale_ate")
    i.add_argument("--invalida-se", default=None, dest="invalida_se")
    i.set_defaults(func=inserir)

    l = sub.add_parser("listar", help="Lista o que existe")
    l.add_argument("--tema", default=None)
    l.add_argument("--limite", type=int, default=20)
    l.set_defaults(func=listar)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
