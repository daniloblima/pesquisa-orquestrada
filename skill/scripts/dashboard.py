#!/usr/bin/env python3
"""
dashboard.py — compila todas as pesquisas feitas num HTML único.

Varre a pasta outputs/, lê os JSON de cada rodada e monta um painel que abre
com duplo clique, sem servidor e sem terminal.

Funciona mesmo em pesquisa antiga que não tenha meta.json: nesse caso infere o
tema pelo título do relatório e o restante pelos JSON das rodadas.

Uso:
    python3 dashboard.py                    # usa a pasta padrão do config.json
    python3 dashboard.py --raiz <pasta>     # aponta para outra pasta
"""

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

RAIZ_SKILL = Path(__file__).resolve().parent.parent


def log(etapa, mensagem):
    print(f"[{datetime.now():%H:%M:%S}] [{etapa}] {mensagem}", flush=True)


# ---------------------------------------------------------------- coleta

def ler_json(caminho):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception as e:
        log("AVISO", f"não consegui ler {caminho.name}: {type(e).__name__}: {e}")
        return None


def titulo_do_relatorio(pasta):
    rel = pasta / "relatorio.md"
    if not rel.exists():
        return None
    try:
        for linha in rel.read_text(encoding="utf-8").splitlines():
            if linha.startswith("# "):
                return linha[2:].strip()
    except Exception as e:
        log("AVISO", f"não li o título de {rel}: {e}")
    return None


def tema_pelo_nome(pasta):
    nome = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", pasta.name)
    return nome.replace("-", " ").replace("_", " ").strip().capitalize()


def coletar(pasta):
    """Reúne uma pesquisa a partir dos arquivos que existirem na pasta."""
    rodadas = []
    for nome in ("r1.json", "r2.json"):
        d = ler_json(pasta / nome)
        if d:
            rodadas.append(d)

    # Rodadas avulsas, como a recuperação de um agente que falhou.
    for extra in sorted(pasta.glob("*.json")):
        if extra.name in ("r1.json", "r2.json", "meta.json"):
            continue
        d = ler_json(extra)
        if d and "resultados" in d:
            rodadas.append(d)

    if not rodadas:
        return None

    meta = ler_json(pasta / "meta.json") or {}

    urls, dominios, agentes = set(), Counter(), {}
    custo = 0.0
    duracao = 0.0

    for r in rodadas:
        custo += r.get("custo_real_usd", 0.0) or 0.0
        duracao += r.get("duracao_s", 0.0) or 0.0
        for res in r.get("resultados", []):
            slot = res["slot"]
            info = agentes.setdefault(
                slot,
                {"rotulo": res.get("rotulo", slot), "modelo": res.get("modelo", ""),
                 "urls": 0, "custo": 0.0, "falhas": 0, "sem_fontes": False,
                 "truncou": False, "url_set": set()},
            )
            info["custo"] += res.get("custo_usd", 0.0) or 0.0
            info["urls"] += len(res.get("urls") or [])
            if res.get("erro"):
                info["falhas"] += 1
            if res.get("sem_fontes"):
                info["sem_fontes"] = True
            if res.get("finish_reason") == "length":
                info["truncou"] = True
            info["reprovadas"] = info.get("reprovadas", 0) + len(res.get("urls_problematicas") or {})
            for u in res.get("urls") or []:
                urls.add(u)
                info["url_set"].add(u)
                try:
                    host = urlparse(u).netloc.lower().removeprefix("www.")
                    if host:
                        dominios[host] += 1
                except Exception:
                    pass

    # Fonte exclusiva: URL que só aquele motor alcançou nesta pesquisa. É a medida de
    # quanto ele acrescenta que os outros não alcançariam sozinhos.
    for slot, info in agentes.items():
        dos_outros = set()
        for outro, oinfo in agentes.items():
            if outro != slot:
                dos_outros |= oinfo["url_set"]
        info["exclusivas"] = len(info["url_set"] - dos_outros)
        # Quanto do relatório final se apoiou neste motor. Gravado pela skill no passo 7.
        info["contrib"] = (meta.get("contribuicao_por_motor") or {}).get(slot) or {}
        info["nota"] = (meta.get("nota_manual") or {}).get(slot)

    data = meta.get("data") or (pasta.name[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", pasta.name) else "")

    return {
        "pasta": pasta.name,
        "data": data,
        "tema": meta.get("tema") or titulo_do_relatorio(pasta) or tema_pelo_nome(pasta),
        "objetivo": meta.get("objetivo", ""),
        "modo": meta.get("modo") or (rodadas[0].get("modo", "")),
        "rodadas": len(rodadas),
        "custo": round(custo, 4),
        "duracao_min": round(duracao / 60, 1),
        "urls": len(urls),
        "dominios": dominios,
        "agentes": agentes,
        "fonte_unica": meta.get("afirmacoes_fonte_unica"),
        "divergencias_abertas": meta.get("divergencias_nao_resolvidas"),
        "tem_relatorio": (pasta / "relatorio.md").exists(),
    }


# ---------------------------------------------------------------- html

CSS = """
*,*::before,*::after{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
  background:var(--plane);color:var(--ink);line-height:1.5;
  -webkit-font-smoothing:antialiased}
.viz-root{
  color-scheme:light;
  --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --ring:rgba(11,11,11,0.10);
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a;
  --seq-100:#cde2fb; --seq-250:#86b6ef; --seq-450:#2a78d6;
  --good:#0ca30c; --critical:#d03b3b; --warning:#ec835a;
}
@media (prefers-color-scheme:dark){
  :root:where(:not([data-theme="light"])) .viz-root{
    color-scheme:dark;
    --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink-2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --ring:rgba(255,255,255,0.10);
    --s1:#3987e5; --s2:#d95926; --s3:#199e70;
    --seq-100:#104281; --seq-250:#184f95; --seq-450:#3987e5;
    --good:#0ca30c; --critical:#d03b3b; --warning:#ec835a;
  }
}
:root[data-theme="dark"] .viz-root{
  color-scheme:dark;
  --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink-2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --ring:rgba(255,255,255,0.10);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
  --seq-100:#104281; --seq-250:#184f95; --seq-450:#3987e5;
  --good:#0ca30c; --critical:#d03b3b; --warning:#ec835a;
}
.wrap{max-width:1080px;margin:0 auto;padding:40px 24px 72px}
header h1{font-size:26px;font-weight:600;margin:0 0 6px;letter-spacing:-0.01em}
header p{margin:0;color:var(--ink-2);font-size:14px}
h2{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:0.07em;
  color:var(--muted);margin:40px 0 14px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-top:26px}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:16px 18px}
.tile .rot{font-size:12px;color:var(--ink-2);margin-bottom:6px}
.tile .val{font-size:30px;font-weight:600;letter-spacing:-0.02em;line-height:1.1}
.tile .sub{font-size:12px;color:var(--muted);margin-top:4px}
.tabela-wrap{overflow-x:auto;background:var(--surface);border:1px solid var(--ring);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:14px;min-width:720px}
th{text-align:left;font-weight:600;font-size:12px;color:var(--muted);
  text-transform:uppercase;letter-spacing:0.05em;padding:12px 14px;border-bottom:1px solid var(--grid)}
td{padding:13px 14px;border-bottom:1px solid var(--grid);vertical-align:top}
tr:last-child td{border-bottom:none}
.num{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
.tema{font-weight:500}
.obj{color:var(--ink-2);font-size:12.5px;margin-top:3px;max-width:380px}
a{color:var(--s1);text-decoration:none}
a:hover{text-decoration:underline}
.chip{display:inline-flex;align-items:center;gap:5px;font-size:12px;
  padding:2px 8px;border-radius:99px;border:1px solid var(--ring);margin:2px 3px 2px 0;
  white-space:nowrap;font-variant-numeric:tabular-nums}
.chip .dot{width:7px;height:7px;border-radius:50%;flex:none}
.ok .dot{background:var(--good)} .bad .dot{background:var(--critical)}
.warn .dot{background:var(--warning)}
.bad{color:var(--critical)} .warn{color:var(--ink-2)}
.barras{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:20px 22px}
.linha{display:grid;grid-template-columns:1fr 44px;align-items:center;gap:12px}
.barras>div{margin-bottom:18px}
.barras>div:last-child{margin-bottom:0}
.rotulo{font-size:13px;color:var(--ink-2);margin-bottom:6px}
.trilho{height:9px;background:var(--grid);border-radius:4px;overflow:hidden}
.barra{height:100%;background:var(--seq-450);border-radius:4px}
.qtd{font-size:13px;color:var(--ink-2);text-align:right;font-variant-numeric:tabular-nums}
.legenda{font-size:12.5px;color:var(--muted);margin:10px 2px 0;max-width:760px;line-height:1.55}
.legenda strong{color:var(--ink-2);font-weight:600}
td .linha{margin:0;min-width:120px}
.vazio{background:var(--surface);border:1px dashed var(--ring);border-radius:10px;
  padding:36px;text-align:center;color:var(--muted);font-size:14px}
footer{margin-top:44px;padding-top:18px;border-top:1px solid var(--grid);
  color:var(--muted);font-size:12px}
"""


def esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def nome_curto(rotulo):
    """'Perplexity Deep Research' vira 'Perplexity'; 'GPT-5.6 Terra' vira 'GPT-5.6'."""
    partes = str(rotulo).split()
    if not partes:
        return rotulo
    if len(partes) > 1 and any(c.isdigit() for c in partes[1]):
        return " ".join(partes[:2])
    return partes[0]


def chips_agentes(agentes):
    partes = []
    for slot in sorted(agentes):
        a = agentes[slot]
        nome = nome_curto(a["rotulo"])
        if a["falhas"] and not a["urls"]:
            cls, marca = "bad", "falhou"
        elif a["sem_fontes"]:
            cls, marca = "warn", "sem fontes"
        elif a["truncou"]:
            cls, marca = "warn", f"{a['urls']} fontes, truncado"
        else:
            cls, marca = "ok", f"{a['urls']} fontes"
        partes.append(
            f'<span class="chip {cls}" title="{esc(a["modelo"])}"><span class="dot"></span>'
            f'{esc(nome)} · {esc(marca)}</span>'
        )
    return "".join(partes)


def montar_html(pesquisas, raiz):
    total_custo = sum(p["custo"] for p in pesquisas)
    total_urls = sum(p["urls"] for p in pesquisas)
    media = total_custo / len(pesquisas) if pesquisas else 0

    dominios = Counter()
    for p in pesquisas:
        dominios.update(p["dominios"])

    kpis = [
        ("Pesquisas", f"{len(pesquisas)}", "concluídas"),
        ("Custo acumulado", f"US$ {total_custo:.2f}", f"média de US$ {media:.2f} por pesquisa"),
        ("Fontes coletadas", f"{total_urls}", f"{len(dominios)} domínios distintos"),
        ("Tempo total", f"{sum(p['duracao_min'] for p in pesquisas):.0f} min", "só as chamadas de busca"),
    ]
    html_kpis = "".join(
        f'<div class="tile"><div class="rot">{esc(r)}</div>'
        f'<div class="val">{esc(v)}</div><div class="sub">{esc(s)}</div></div>'
        for r, v, s in kpis
    )

    linhas = []
    for p in sorted(pesquisas, key=lambda x: (x["data"], x["pasta"]), reverse=True):
        rel = (f'<a href="{esc(p["pasta"])}/relatorio.md">relatório</a>'
               if p["tem_relatorio"] else '<span style="color:var(--muted)">em curso</span>')
        link = f'{rel} · <a href="{esc(p["pasta"])}/">pasta</a>'
        obj = f'<div class="obj">{esc(p["objetivo"])}</div>' if p["objetivo"] else ""
        marcas = []
        if p["fonte_unica"] is not None:
            marcas.append(f'{p["fonte_unica"]} de fonte única')
        if p["divergencias_abertas"]:
            marcas.append(f'{p["divergencias_abertas"]} em aberto')
        nota = f'<div class="obj">{esc(" · ".join(marcas))}</div>' if marcas else ""
        linhas.append(
            f"<tr><td class='num'>{esc(p['data'])}</td>"
            f"<td><div class='tema'>{esc(p['tema'])}</div>{obj}{nota}</td>"
            f"<td>{esc(p['modo'])}</td>"
            f"<td>{chips_agentes(p['agentes'])}</td>"
            f"<td class='num'>{p['urls']}</td>"
            f"<td class='num'>US$ {p['custo']:.2f}</td>"
            f"<td>{link}</td></tr>"
        )

    tabela = (
        '<div class="tabela-wrap"><table><thead><tr>'
        "<th>Data</th><th>Tema</th><th>Modo</th><th>Motores</th>"
        "<th class='num'>Fontes</th><th class='num'>Custo</th><th>Abrir</th>"
        "</tr></thead><tbody>" + "".join(linhas) + "</tbody></table></div>"
        '<p class="legenda">Modo define a profundidade de cada busca: '
        "<strong>rápida</strong> corta em 6 mil tokens e 5 resultados por motor, "
        "<strong>normal</strong> em 12 mil e 8, "
        "<strong>profunda</strong> em 20 mil e 12. Mais profundo custa mais e demora mais.</p>"
    ) if linhas else '<div class="vazio">Nenhuma pesquisa ainda. Rode /pesquisa para começar.</div>'

    # Desempenho agregado por modelo, não por slot: assim a troca de um motor por outro
    # aparece como duas linhas comparáveis em vez de sumir dentro do mesmo slot.
    motores = {}
    for p in pesquisas:
        for slot, a in p["agentes"].items():
            m = motores.setdefault(
                a["modelo"] or slot,
                {"rotulo": a["rotulo"], "pesquisas": 0, "urls": 0, "exclusivas": 0,
                 "falhas": 0, "custo": 0.0, "truncou": 0, "reprovadas": 0,
                 "afirmacoes": 0, "confirmadas": 0, "tem_contrib": False, "notas": []},
            )
            m["pesquisas"] += 1
            m["urls"] += a["urls"]
            m["exclusivas"] += a.get("exclusivas", 0)
            m["falhas"] += a["falhas"]
            m["custo"] += a["custo"]
            m["truncou"] += 1 if a["truncou"] else 0
            m["reprovadas"] += a.get("reprovadas", 0)
            c = a.get("contrib") or {}
            if c.get("afirmacoes") is not None and c.get("afirmacoes") != 0:
                m["tem_contrib"] = True
                m["afirmacoes"] += c.get("afirmacoes") or 0
                m["confirmadas"] += c.get("confirmadas") or 0
            if a.get("nota"):
                m["notas"].append(a["nota"])

    bloco_motores = ""
    if motores:
        max_exc = max((m["exclusivas"] for m in motores.values()), default=0) or 1
        # As colunas de contribuição só aparecem quando há pesquisa que as gravou.
        tem_contrib = any(m["tem_contrib"] for m in motores.values())
        tem_nota = any(m["notas"] for m in motores.values())
        linhas_m = []
        for modelo, m in sorted(motores.items(), key=lambda kv: -kv[1]["exclusivas"]):
            pct = (m["exclusivas"] / m["urls"] * 100) if m["urls"] else 0
            por_exc = (m["custo"] / m["exclusivas"]) if m["exclusivas"] else None
            alerta = []
            if m["falhas"]:
                alerta.append(f'{m["falhas"]} falha' + ("s" if m["falhas"] > 1 else ""))
            if m["truncou"]:
                alerta.append(f'{m["truncou"]} truncada' + ("s" if m["truncou"] > 1 else ""))
            if m["reprovadas"]:
                alerta.append(f'{m["reprovadas"]} URLs reprovadas')
            nota_txt = (
                f'<div class="obj bad">{esc(" · ".join(alerta))}</div>' if alerta else ""
            )

            extra = ""
            if tem_contrib:
                por_conf = (m["custo"] / m["confirmadas"]) if m["confirmadas"] else None
                extra = (
                    f"<td class='num'>{m['afirmacoes'] or '—'}</td>"
                    f"<td class='num'>{m['confirmadas'] or '—'}</td>"
                    f"<td class='num'>{'US$ %.2f' % por_conf if por_conf else '—'}</td>"
                )
            if tem_nota:
                media = sum(m["notas"]) / len(m["notas"]) if m["notas"] else None
                extra += f"<td class='num'>{'%.1f' % media if media else '—'}</td>"

            linhas_m.append(
                f"<tr><td><div class='tema'>{esc(nome_curto(m['rotulo']))}</div>"
                f"<div class='obj'>{esc(modelo)}</div>{nota_txt}</td>"
                f"<td class='num'>{m['pesquisas']}</td>"
                f"<td class='num'>{m['urls']}</td>"
                f"<td><div class='linha'><div class='trilho'>"
                f"<div class='barra' style='width:{m['exclusivas'] / max_exc * 100:.1f}%'></div>"
                f"</div><div class='qtd'>{m['exclusivas']}</div></div></td>"
                f"<td class='num'>{pct:.0f}%</td>"
                f"<td class='num'>US$ {m['custo']:.2f}</td>"
                f"<td class='num'>{'US$ %.2f' % por_exc if por_exc is not None else '—'}</td>"
                f"{extra}</tr>"
            )

        cab_extra = (
            "<th class='num'>Afirmações</th><th class='num'>Confirmadas</th>"
            "<th class='num'>Por confirmada</th>" if tem_contrib else ""
        )
        if tem_nota:
            cab_extra += "<th class='num'>Nota</th>"

        legenda_contrib = (
            " <strong>Afirmações</strong> é quanto daquele motor entrou no relatório final e "
            "<strong>confirmadas</strong> é quanto disso outro motor também sustentou. "
            "Custo por confirmada é a medida final: quanto custou cada informação confiável."
            if tem_contrib else
            " As colunas de afirmações aparecem a partir da próxima pesquisa, quando a skill "
            "passar a gravar quanto de cada motor entrou no relatório."
        )

        bloco_motores = (
            "<h2>Desempenho por motor</h2>"
            '<div class="tabela-wrap"><table><thead><tr>'
            "<th>Motor</th><th class='num'>Pesquisas</th><th class='num'>Fontes</th>"
            "<th>Exclusivas</th><th class='num'>% exclusivo</th>"
            "<th class='num'>Custo</th><th class='num'>Por exclusiva</th>"
            f"{cab_extra}</tr></thead><tbody>" + "".join(linhas_m) + "</tbody></table></div>"
            '<p class="legenda">Fonte <strong>exclusiva</strong> é a URL que só aquele motor '
            "alcançou. Mede alcance, não utilidade: uma página que ninguém mais viu pode não ter "
            f"acrescentado nenhuma informação nova.{legenda_contrib}</p>"
        )

    # Só vale desenhar barras quando há repetição suficiente para revelar padrão.
    bloco_dominios = ""
    top = [(d, n) for d, n in dominios.most_common(12) if n > 1]
    if len(top) >= 3:
        maximo = top[0][1]
        linhas_d = "".join(
            f'<div><div class="rotulo">{esc(d)}</div>'
            f'<div class="linha"><div class="trilho">'
            f'<div class="barra" style="width:{n / maximo * 100:.1f}%"></div></div>'
            f'<div class="qtd">{n}</div></div></div>'
            for d, n in top
        )
        bloco_dominios = (
            "<h2>Fontes mais recorrentes</h2>"
            f'<div class="barras">{linhas_d}</div>'
        )

    agora = datetime.now()
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pesquisas — painel</title>
<style>{CSS}</style></head>
<body class="viz-root"><div class="wrap">
<header>
  <h1>Pesquisas orquestradas</h1>
  <p>Validação cruzada entre motores independentes · {esc(raiz)}</p>
</header>
<div class="kpis">{html_kpis}</div>
<h2>Histórico</h2>
{tabela}
{bloco_motores}
{bloco_dominios}
<footer>Gerado em {agora:%d/%m/%Y às %H:%M} · atualizado a cada nova pesquisa</footer>
</div></body></html>"""


# ---------------------------------------------------------------- fluxo

def main():
    p = argparse.ArgumentParser(description="Compila as pesquisas num painel HTML.")
    p.add_argument("--raiz", default=None, help="Pasta de outputs. Padrão: a do config.json.")
    p.add_argument("--saida", default=None, help="Caminho do HTML. Padrão: <raiz>/dashboard.html")
    args = p.parse_args()

    if args.raiz:
        raiz = Path(args.raiz).expanduser().resolve()
    else:
        cfg = json.loads((RAIZ_SKILL / "config.json").read_text(encoding="utf-8"))
        configurada = (cfg.get("saida_padrao") or "").strip()
        # Vazio resolve para outputs/ ao lado da skill, o que mantém o repositório portável.
        raiz = (Path(configurada).expanduser().resolve() if configurada
                else RAIZ_SKILL.parent / "outputs")

    if not raiz.exists():
        raise SystemExit(f"ERRO: pasta não encontrada: {raiz}")

    log("VARRER", f"lendo {raiz}")
    pesquisas = []
    for pasta in sorted(raiz.iterdir()):
        if not pasta.is_dir():
            continue
        dados = coletar(pasta)
        if dados:
            pesquisas.append(dados)
            log("VARRER", f"{pasta.name}: {dados['urls']} fontes · US$ {dados['custo']:.2f}")
        else:
            log("VARRER", f"{pasta.name}: sem JSON de rodada, ignorada")

    saida = Path(args.saida).expanduser().resolve() if args.saida else raiz / "dashboard.html"
    saida.write_text(montar_html(pesquisas, str(raiz)), encoding="utf-8")

    log("FIM", f"{len(pesquisas)} pesquisas no painel")
    log("FIM", f"arquivo: {saida}")
    print(f"\nAbra com duplo clique: {saida}")


if __name__ == "__main__":
    main()
