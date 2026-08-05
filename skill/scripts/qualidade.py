#!/usr/bin/env python3
"""
qualidade.py — mede o desempenho de cada motor a partir das pesquisas já feitas.

Nenhum modelo é julgado no código nem no config. Os limiares ficam no config.json e a
nota sai dos dados: um motor que melhora sobe de faixa sozinho, um que piora desce. É o
que transforma o uso da skill num benchmark contínuo em vez de uma opinião congelada.

Grava qualidade-motores.json com a foto atual e a série histórica, uma linha por
pesquisa, para que a evolução seja visível e não precise ser recalculada do zero.

Uso:
    python3 qualidade.py              # recalcula, grava e mostra o quadro
    python3 qualidade.py --resumo     # só o que a skill precisa saber, sem detalhe
"""

import argparse
import json
from datetime import date
from pathlib import Path

RAIZ_SKILL = Path(__file__).resolve().parent.parent
DESTINO = RAIZ_SKILL / "qualidade-motores.json"


def log(msg):
    print(msg, flush=True)


def carregar_cfg():
    cfg = json.loads((RAIZ_SKILL / "config.json").read_text(encoding="utf-8"))
    lim = cfg.get("limiares_qualidade") or {}
    if not lim:
        raise SystemExit("ERRO: config.json sem 'limiares_qualidade'.")
    return cfg, lim


def raiz_outputs(cfg):
    configurada = (cfg.get("saida_padrao") or "").strip()
    return Path(configurada).expanduser().resolve() if configurada else RAIZ_SKILL.parent / "outputs"


def ler(caminho):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        return None


def coletar(raiz):
    """Uma linha por motor por pesquisa. O motor é identificado pelo modelo, não pelo
    id nem pela letra: assim a série sobrevive a renomeações e a trocas de slot."""
    linhas = []
    for pasta in sorted(raiz.iterdir()):
        if not pasta.is_dir():
            continue
        meta = ler(pasta / "meta.json") or {}
        contrib = meta.get("contribuicao_por_motor") or {}

        por_modelo = {}
        for arq in sorted(pasta.glob("*.json")):
            if arq.name == "meta.json":
                continue
            d = ler(arq)
            if not d or "resultados" not in d:
                continue
            for r in d["resultados"]:
                modelo = r.get("modelo") or r.get("slot")
                a = por_modelo.setdefault(modelo, {
                    "rotulo": r.get("rotulo", modelo), "urls": 0, "reprovadas": 0,
                    "custo": 0.0, "execucoes": 0, "incidentes": 0, "slots": set(),
                    "erros": [], "reprovadas_detalhe": {}})
                a["slots"].add(r.get("slot"))
                a["urls"] += len(r.get("urls") or [])
                a["reprovadas"] += len(r.get("urls_problematicas") or {})
                a["custo"] += r.get("custo_usd", 0.0) or 0.0
                a["execucoes"] += 1
                # Falha total e resposta truncada não são a mesma coisa: uma perde tudo,
                # a outra perde o fim. Pesar igual condena quem só foi verboso demais.
                if r.get("erro") or r.get("finish_reason") == "error":
                    a["incidentes"] += 1.0
                    a["erros"].append({
                        "rodada": arq.name, "tipo": "falha",
                        "detalhe": (r.get("erro") or "finish_reason=error")[:220]})
                elif r.get("finish_reason") == "length":
                    a["incidentes"] += 0.5
                    a["erros"].append({
                        "rodada": arq.name, "tipo": "truncado",
                        "detalhe": f"resposta cortada no limite de tokens ({r.get('tokens_out')} de saída)"})
                if r.get("sem_fontes"):
                    a["erros"].append({"rodada": arq.name, "tipo": "sem fontes",
                                       "detalhe": "respondeu sem nenhuma URL"})
                if r.get("reprovadas_sem_rastro"):
                    a["erros"].append({"rodada": arq.name, "tipo": "reprovadas sem rastro",
                                       "detalhe": "fontes reprovadas só na lista final, sem trecho associado"})
                # Por que cada URL caiu: é o que permite ver se o motor melhora ou piora.
                for _, reg in (r.get("urls_problematicas") or {}).items():
                    est = reg.get("estado", "?")
                    a["reprovadas_detalhe"][est] = a["reprovadas_detalhe"].get(est, 0) + 1

        for modelo, a in por_modelo.items():
            # A contribuição vem chaveada pelo slot usado naquela pesquisa.
            c = {}
            for slot in a["slots"]:
                if slot in contrib:
                    c = contrib[slot]
                    break
            linhas.append({
                "pesquisa": pasta.name,
                "data": meta.get("data") or pasta.name[:10],
                "modelo": modelo,
                "rotulo": a["rotulo"],
                "urls": a["urls"],
                "reprovadas": a["reprovadas"],
                "custo": round(a["custo"], 4),
                "execucoes": a["execucoes"],
                "incidentes": round(a["incidentes"], 1),
                "afirmacoes": c.get("afirmacoes"),
                "confirmadas": c.get("confirmadas"),
                "reprovadas_por_motivo": a["reprovadas_detalhe"],
                "erros": a["erros"],
            })
    return linhas


def faixa(valor, cortes):
    """Compara o medido contra o limiar. Só isto é fixo; o valor vem sempre dos dados."""
    if valor is None:
        return "sem dados"
    if valor >= cortes["confiavel"]:
        return "confiável"
    if valor >= cortes["atencao"]:
        return "atenção"
    return "crítico"


def agregar(linhas, lim):
    motores = {}
    for l in linhas:
        m = motores.setdefault(l["modelo"], {
            "rotulo": l["rotulo"], "pesquisas": set(), "urls": 0, "reprovadas": 0,
            "custo": 0.0, "execucoes": 0, "incidentes": 0, "afirmacoes": 0,
            "confirmadas": 0, "tem_contrib": False})
        m["pesquisas"].add(l["pesquisa"])
        for k in ("urls", "reprovadas", "execucoes", "incidentes"):
            m[k] += l[k]
        m["custo"] += l["custo"]
        if l["afirmacoes"]:
            m["tem_contrib"] = True
            m["afirmacoes"] += l["afirmacoes"]
            m["confirmadas"] += l["confirmadas"] or 0

    pesos = lim["pesos_indice"]
    for modelo, m in motores.items():
        m["pesquisas"] = len(m["pesquisas"])
        m["precisao_fonte"] = ((m["urls"] - m["reprovadas"]) / m["urls"]) if m["urls"] else None
        m["taxa_confirmacao"] = (m["confirmadas"] / m["afirmacoes"]) if m["afirmacoes"] else None
        m["confiabilidade"] = (1 - m["incidentes"] / m["execucoes"]) if m["execucoes"] else None

        partes = [(m["precisao_fonte"], pesos["precisao_fonte"]),
                  (m["taxa_confirmacao"], pesos["taxa_confirmacao"]),
                  (m["confiabilidade"], pesos["confiabilidade"])]
        validas = [(v, p) for v, p in partes if v is not None]
        m["indice"] = (round(sum(v * p for v, p in validas) / sum(p for _, p in validas) * 100, 1)
                       if validas else None)

        # Amostra pequena não classifica ninguém: evita condenar motor por uma rodada ruim.
        suficiente = (m["urls"] >= lim["minimo_urls_para_avaliar"]
                      and m["pesquisas"] >= lim["minimo_pesquisas_para_avaliar"])
        m["amostra_suficiente"] = suficiente
        m["faixa_precisao"] = faixa(m["precisao_fonte"], lim["precisao_fonte"]) if suficiente else "amostra pequena"
        m["faixa_geral"] = faixa(m["indice"], lim["indice_geral"]) if suficiente else "amostra pequena"

        # O papel é derivado da medição, nunca escrito à mão em lugar nenhum.
        if not suficiente:
            m["papel"] = "em avaliação"
        elif m["faixa_geral"] == "confiável":
            m["papel"] = "confirmação"
        elif m["faixa_geral"] == "atenção":
            m["papel"] = "confirmação com ressalva"
        else:
            m["papel"] = "descoberta"
    return motores


PAPEL_EXPLICADO = {
    "confirmação": "pode sustentar afirmação junto com outro motor, como sempre",
    "confirmação com ressalva": "conta como confirmação, mas afirmação que dependa só dele merece um olhar antes de entrar",
    "descoberta": "serve para achar pistas e fontes; sozinho não confirma nada, e o que vier só dele vai para a rodada 2",
    "em avaliação": "amostra ainda pequena para classificar; trate como confirmação com ressalva",
}


def main():
    p = argparse.ArgumentParser(description="Mede a qualidade dos motores pelas pesquisas feitas.")
    p.add_argument("--resumo", action="store_true", help="Só o que a skill precisa saber.")
    args = p.parse_args()

    cfg, lim = carregar_cfg()
    raiz = raiz_outputs(cfg)
    if not raiz.exists():
        raise SystemExit(f"ERRO: pasta de pesquisas não encontrada: {raiz}")

    linhas = coletar(raiz)
    motores = agregar(linhas, lim)

    # A foto atual é sobrescrita a cada execução; a série de notas nunca. Sem ela não há
    # como saber se um motor melhorou ou piorou, que é o ponto de acompanhar.
    anterior = ler(DESTINO) or {}
    serie = anterior.get("serie_notas") or []
    hoje = str(date.today())

    for modelo, m in motores.items():
        registro = {
            "data": hoje, "modelo": modelo, "rotulo": m["rotulo"],
            "pesquisas": m["pesquisas"], "urls": m["urls"], "reprovadas": m["reprovadas"],
            "precisao_fonte": round(m["precisao_fonte"], 4) if m["precisao_fonte"] is not None else None,
            "taxa_confirmacao": round(m["taxa_confirmacao"], 4) if m["taxa_confirmacao"] is not None else None,
            "confiabilidade": round(m["confiabilidade"], 4) if m["confiabilidade"] is not None else None,
            "indice": m["indice"], "faixa_geral": m["faixa_geral"], "papel": m["papel"],
        }
        # Uma medição por motor por dia, sempre a mais recente. Rodar duas vezes no mesmo
        # dia atualiza a linha em vez de duplicar.
        serie = [x for x in serie if not (x["data"] == hoje and x["modelo"] == modelo)]
        serie.append(registro)

    serie.sort(key=lambda x: (x["data"], x["modelo"]))

    saida = {
        "atualizado_em": hoje,
        "_leia": ("motores = foto atual. serie_notas = uma medição por motor por dia, "
                  "nunca sobrescrita, para acompanhar evolução. historico = uma linha por "
                  "motor por pesquisa, com os erros e o motivo de cada URL reprovada. "
                  "Limiares em config.json; nada aqui é escrito à mão."),
        "limiares_usados": lim,
        "motores": {k: {x: y for x, y in v.items()} for k, v in motores.items()},
        "serie_notas": serie,
        "historico": linhas,
    }
    DESTINO.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")

    ordem = sorted(motores.items(), key=lambda kv: -(kv[1]["indice"] or 0))

    if not args.resumo:
        log(f"\n{len(linhas)} medições em {len({l['pesquisa'] for l in linhas})} pesquisas\n")
        log(f"{'MOTOR':30} {'PESQ':>4} {'URLs':>5} {'PRECISÃO':>9} {'CONFIRM':>8} {'CONFIAB':>8} {'ÍNDICE':>7}  FAIXA")
        log("-" * 96)
        for modelo, m in ordem:
            def pct(v):
                return f"{v * 100:.0f}%" if v is not None else "—"
            log(f"{m['rotulo'][:30]:30} {m['pesquisas']:>4} {m['urls']:>5} "
                f"{pct(m['precisao_fonte']):>9} {pct(m['taxa_confirmacao']):>8} "
                f"{pct(m['confiabilidade']):>8} {str(m['indice'] or '—'):>7}  {m['faixa_geral']}")

        c = lim["precisao_fonte"]
        log(f"\nRéguas atuais (config.json, não mexem em motor nenhum):")
        log(f"  precisão de fonte: confiável >= {c['confiavel']:.0%} · atenção >= {c['atencao']:.0%}")
        g = lim["indice_geral"]
        log(f"  índice geral: confiável >= {g['confiavel']} · atenção >= {g['atencao']}")
        log(f"  só classifica com {lim['minimo_urls_para_avaliar']}+ URLs e "
            f"{lim['minimo_pesquisas_para_avaliar']}+ pesquisas")

    if not args.resumo:
        # Variação desde a última data medida antes de hoje.
        datas = sorted({x["data"] for x in serie if x["data"] < hoje})
        if datas:
            ant = {x["modelo"]: x for x in serie if x["data"] == datas[-1]}
            log(f"\nVARIAÇÃO DO ÍNDICE desde {datas[-1]}")
            for modelo, m in ordem:
                a = ant.get(modelo)
                if a and a.get("indice") is not None and m["indice"] is not None:
                    d = m["indice"] - a["indice"]
                    seta = "subiu" if d > 0.05 else "caiu" if d < -0.05 else "estável"
                    log(f"  {m['rotulo'][:30]:30} {a['indice']:>5} -> {m['indice']:>5}  ({seta})")
                else:
                    log(f"  {m['rotulo'][:30]:30} sem medição anterior")
        else:
            log("\n  Primeira medição registrada. A variação aparece a partir da próxima data.")

        recentes = [(l["data"], l["rotulo"], e) for l in linhas for e in l["erros"]]
        if recentes:
            log(f"\nERROS REGISTRADOS ({len(recentes)}), do mais recente")
            for data, rot, e in sorted(recentes, key=lambda x: (x[0], x[1]), reverse=True)[:10]:
                log(f"  {data}  {rot[:26]:26} {e['tipo']:22} {e['detalhe'][:60]}")

        motivos = {}
        for l in linhas:
            for mot, n in (l.get("reprovadas_por_motivo") or {}).items():
                motivos.setdefault(l["rotulo"], {})[mot] = motivos.setdefault(l["rotulo"], {}).get(mot, 0) + n
        if motivos:
            log("\nURLs REPROVADAS, POR MOTIVO")
            for rot, m in sorted(motivos.items()):
                if m:
                    log(f"  {rot[:26]:26} " + " · ".join(f"{k}: {v}" for k, v in sorted(m.items())))

    if not ordem:
        log("\nNENHUMA PESQUISA MEDIDA AINDA\n")
        log("  A série começa vazia de propósito: a nota de um motor tem de sair das suas")
        log("  pesquisas, não das de outra pessoa. Até haver "
            f"{lim['minimo_pesquisas_para_avaliar']} pesquisas e "
            f"{lim['minimo_urls_para_avaliar']} URLs por motor,")
        log("  trate todos como 'confirmação com ressalva'.")
        log(f"\n  arquivo: {DESTINO}")
        return

    log("\nCOMO TRATAR CADA MOTOR NESTA PESQUISA\n")
    for modelo, m in ordem:
        log(f"  {m['rotulo']} — {m['papel']}")
        log(f"      {PAPEL_EXPLICADO[m['papel']]}")
    log(f"\n  arquivo: {DESTINO}")


if __name__ == "__main__":
    main()
