#!/usr/bin/env python3
"""
regressao.py — mostra o que uma mudança na régua faz com as pesquisas antigas.

Não gasta crédito. Roda a verificação duas vezes sobre uma cópia de cada pesquisa já
coletada, uma com o código de trabalho e outra com o código de um commit, e imprime só as
diferenças.

Existe porque a régua não tem teste e a evidência dela é histórica: melhorar a
classificação de uma URL pode, sem aviso, apagar um alerta legítimo numa pesquisa de duas
semanas atrás. O ponto não é que a saída fique idêntica — quem muda a régua quer que ela
mude. O ponto é que **toda diferença seja explicável pela mudança que se fez**, e o jeito
de saber é olhar uma a uma.

Em 21/08/2026, na estreia, rebaixar "domínio raiz" de falha dura para sinal fraco mexeu em
doze URLs de cinco pesquisas. As doze eram domínio raiz, nenhum alerta legítimo caiu, e
entre elas estavam lojasrenner.com.br numa pesquisa sobre a Renner e openrouter.ai numa
pesquisa sobre LLM.

Uso:
    python3 regressao.py                      # trabalho contra HEAD
    python3 regressao.py --contra d8a6709     # trabalho contra um commit específico
    python3 regressao.py --detalhe            # cada URL que mudou, com o motivo
"""

import argparse
import collections
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent          # a pasta do projeto, acima de skill/
OUTPUTS = RAIZ / "outputs"

# Os dois arquivos que decidem o veredito. `verificar.py` importa `verificacao.py` do
# próprio diretório, então basta pôr os dois lado a lado para ter a versão antiga inteira.
ARQUIVOS = ("verificar.py", "verificacao.py")


def log(msg):
    print(msg, flush=True)


def versao_do_commit(commit, destino):
    """Escreve em `destino` os scripts de verificação como estavam num commit."""
    destino.mkdir(parents=True, exist_ok=True)
    for nome in ARQUIVOS:
        r = subprocess.run(
            ["git", "-C", str(RAIZ), "show", f"{commit}:skill/scripts/{nome}"],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"não consegui ler {nome} em {commit}:\n{r.stderr.strip()}")
        (destino / nome).write_text(r.stdout, encoding="utf-8")
    return destino / "verificar.py"


def rodar(script, pesquisas):
    """Verifica cada pesquisa da cópia, em silêncio. Sem rede: só a régua sobre o texto.

    `--sem-rede` não é economia, é isolamento. Com rede, a mesma pesquisa muda de veredito
    entre duas execuções porque uma página saiu do ar ou um servidor devolveu 403, e a
    comparação passa a medir a internet em vez da mudança de código.
    """
    for p in pesquisas:
        subprocess.run([sys.executable, str(script), str(p), "--todas", "--sem-rede"],
                       capture_output=True, text=True)


def resumo(pasta):
    """O que uma pesquisa verificada afirma, em forma comparável."""
    out = {}
    for r in (1, 2):
        arq = pasta / f"r{r}_verificacao.json"
        if not arq.exists():
            continue
        d = json.loads(arq.read_text(encoding="utf-8"))
        estados, motivos = {}, {}
        for slot, urls in (d.get("por_motor") or {}).items():
            for u, x in (urls or {}).items():
                estados[(slot, u)] = x.get("estado")
                motivos[(slot, u)] = "; ".join(x.get("motivos") or [])
        gatilhos = collections.Counter(x.get("gatilho") for x in (d.get("decisoes") or []))
        out[f"r{r}"] = {"estados": estados, "motivos": motivos, "gatilhos": dict(gatilhos)}
    return out


def comparar(antes, depois, detalhe):
    """Imprime as diferenças. Devolve quantas URLs mudaram de estado."""
    mudancas = 0
    for nome in sorted(set(antes) | set(depois)):
        a, b = antes.get(nome, {}), depois.get(nome, {})
        linhas = []
        for r in sorted(set(a) | set(b)):
            ra, rb = a.get(r, {}), b.get(r, {})
            ea, eb = ra.get("estados", {}), rb.get("estados", {})

            trocas = collections.Counter()
            for k in sorted(set(ea) | set(eb)):
                va, vb = ea.get(k, "—"), eb.get(k, "—")
                if va != vb:
                    mudancas += 1
                    trocas[(va, vb)] += 1
                    if detalhe:
                        motivo = rb.get("motivos", {}).get(k) or ra.get("motivos", {}).get(k)
                        linhas.append(f"    {r} {k[0]}: {va} -> {vb}")
                        linhas.append(f"        {k[1][:78]}")
                        if motivo:
                            linhas.append(f"        motivo: {motivo[:100]}")
            if not detalhe:
                for (va, vb), n in sorted(trocas.items()):
                    linhas.append(f"    {r}: {n}x  {va} -> {vb}")

            ga, gb = ra.get("gatilhos", {}), rb.get("gatilhos", {})
            for g in sorted(set(ga) | set(gb)):
                if ga.get(g, 0) != gb.get(g, 0):
                    linhas.append(f"    {r}: item '{g}' {ga.get(g, 0)} -> {gb.get(g, 0)}")

        if linhas:
            log(f"\n{nome}")
            for x in linhas:
                log(x)
    return mudancas


def main():
    p = argparse.ArgumentParser(
        description="Compara a régua de trabalho com a de um commit, sobre as pesquisas já feitas.")
    p.add_argument("--contra", default="HEAD",
                   help="Commit de referência. Padrão: HEAD, ou seja, o último commitado.")
    p.add_argument("--outputs", default=None,
                   help="Pasta com as pesquisas. Padrão: outputs/ do projeto.")
    p.add_argument("--detalhe", action="store_true",
                   help="Mostra cada URL que mudou de estado, com o motivo.")
    args = p.parse_args()

    origem = Path(args.outputs) if args.outputs else OUTPUTS
    pesquisas = sorted(d for d in origem.glob("*") if d.is_dir() and (d / "r1.json").exists())
    if not pesquisas:
        log(f"nenhuma pesquisa em {origem} — nada com que comparar.")
        log("a régua se mede contra o histórico, e numa instalação nova ele ainda não existe.")
        return

    log(f"{len(pesquisas)} pesquisas · trabalho contra {args.contra}")

    with tempfile.TemporaryDirectory(prefix="regressao-") as tmp:
        tmp = Path(tmp)
        resumos = {}
        for lado, script in (("antes", None), ("depois", AQUI / "verificar.py")):
            # Cada lado roda sobre a própria cópia. Verificar sobrescreve
            # r*_verificacao.json e r*_decisoes.md, e as pesquisas do Danilo não são
            # material de teste.
            base = tmp / lado
            base.mkdir()
            for d in pesquisas:
                shutil.copytree(d, base / d.name)
            if script is None:
                script = versao_do_commit(args.contra, tmp / "versao-antiga")
            rodar(script, sorted(base.iterdir()))
            resumos[lado] = {d.name: resumo(d) for d in sorted(base.iterdir())}

        n = comparar(resumos["antes"], resumos["depois"], args.detalhe)

    log("")
    if n:
        log(f"{n} URLs mudaram de estado.")
        log("Cada uma precisa ser explicável pela mudança que você fez. Se alguma não for,")
        log("é regressão — rode de novo com --detalhe para ver o motivo de cada uma.")
    else:
        log("Nenhuma URL mudou de estado. A régua trata o histórico igual.")


if __name__ == "__main__":
    main()
