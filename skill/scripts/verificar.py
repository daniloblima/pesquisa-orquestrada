#!/usr/bin/env python3
"""
verificar.py — roda a verificação sobre uma rodada já coletada.

Não gasta crédito nenhum. Lê o JSON que o buscar.py gravou, confere as fontes, mede
coerência e independência, e escreve o veredito ao lado:

    r1_verificacao.json   estado de cada URL, afirmações a revalidar, medidas do conjunto
    r1_decisoes.md        no máximo dez itens que precisam do Danilo, em linguagem direta

Pode rodar quantas vezes quiser, inclusive sobre pesquisa antiga, o que é o ponto:
melhorar a régua deixou de exigir comprar uma pesquisa nova a cada tentativa.

Uso:
    python3 verificar.py <pasta-da-pesquisa> --rodada 1 --termos "termo1,termo2"
    python3 verificar.py <pasta-da-pesquisa> --rodada 1 --criticidade alta
    python3 verificar.py <pasta> --todas          # r1 e r2, o que existir
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verificacao as V  # noqa: E402

# Quantas origens independentes o consenso precisa, por criticidade. Criticidade é eixo
# separado de profundidade: corroborar um dado é rápido e crítico; levantar exemplos é
# profundo e pouco crítico. Ver DESENHO_v2.md, decisão 4.
ORIGENS_EXIGIDAS = {"baixa": 1, "media": 2, "alta": 2}

# Em criticidade alta, afirmação sustentada por origem única para o fluxo e vira pergunta.
PARA_O_FLUXO = {"baixa": False, "media": False, "alta": True}

TETO_DECISOES = 10


def log(etapa, mensagem):
    print(f"[{datetime.now():%H:%M:%S}] [{etapa}] {mensagem}", flush=True)


V.log = log


def dominio(url):
    """Domínio registrável, aproximado: o que separa origem de origem."""
    try:
        host = (urlparse(url).netloc or "").lower().removeprefix("www.")
    except Exception:
        return ""
    partes = host.split(".")
    if len(partes) >= 3 and partes[-2] in ("com", "gov", "org", "edu", "net", "co"):
        return ".".join(partes[-3:])
    return ".".join(partes[-2:]) if len(partes) >= 2 else host


# ---------------------------------------------------------------- coerência

UNIDADES = (r"%|pontos percentuais|p\.p\.|GJ|MJ|kWh|MWh|GWh|TWh|kW|MW|GW|US\$|R\$|"
            r"anos|meses|hp|CV|km|m²|hab|habitantes")
NUMERO = r"(?<![\w.,])(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
PADRAO_MEDIDA = re.compile(rf"{NUMERO}\s*({UNIDADES})", re.I)

# Palavra que ancora a medida a um assunto. Nome próprio e termo técnico servem; artigo,
# preposição e verbo comum não separam nada.
PARADAS = set("""a o e de da do das dos em no na nos nas um uma uns umas para por com que
se the of and in to for on is are was were este esta isso esse essa como mais menos entre
sobre até ser foi são não sim seu sua seus suas ao aos à às pelo pela""".split())


def _ancoras(texto):
    return {p.lower() for p in re.findall(r"\b[A-Za-zÀ-ÿ][\wÀ-ÿ\-]{4,}\b", texto)
            if p.lower() not in PARADAS}


def medidas_do_texto(texto, janela=90):
    """Extrai (valor, unidade, âncoras ao redor) de cada medida citada no texto."""
    saida = []
    for m in PADRAO_MEDIDA.finditer(texto or ""):
        bruto, unidade = m.group(1), m.group(2)
        try:
            valor = float(bruto.replace(" ", "").replace(".", "").replace(",", ".")) \
                if bruto.count(",") == 1 and "." in bruto \
                else float(bruto.replace(" ", "").replace(",", "."))
        except ValueError:
            continue
        ini = max(0, m.start() - janela)
        contexto = re.sub(r"\s+", " ", texto[ini:m.end() + 20]).strip()
        saida.append({"valor": valor, "unidade": unidade.lower(),
                      "ancoras": _ancoras(texto[ini:m.start()]), "trecho": contexto})
    return saida


def divergencias_numericas(resultados, minimo_ancoras=2):
    """Mesma grandeza, mesmo assunto, valores diferentes entre motores.

    É o sinal de erro mais barato que existe e não exige ser especialista: quando um motor
    diz 9 pontos percentuais e outro diz 13,5 sobre o mesmo estudo, alguém leu a versão
    errada do paper. Foi o caso de Dinkelman em 12/08/2026, que passou por toda a
    verificação de fonte sem uma queixa.
    """
    por_motor = {}
    for r in resultados:
        if r.get("erro"):
            continue
        por_motor[r["slot"]] = medidas_do_texto(r.get("conteudo") or "")

    # Palavra que aparece em quase toda janela de medida é vocabulário do tema e não
    # identifica assunto nenhum: "pessoa" e "probabilidade" casariam duas medidas que não
    # têm nada a ver. O que ancora é o termo raro — nome de autor, de estudo, de lugar.
    todas = [m for ms in por_motor.values() for m in ms]
    freq = defaultdict(int)
    for m in todas:
        for a in m["ancoras"]:
            freq[a] += 1
    teto = max(2, int(len(todas) * 0.2)) if todas else 2
    raras = {a for a, n in freq.items() if n <= teto}

    achados, vistos = [], set()
    slots = list(por_motor)
    for i, a in enumerate(slots):
        for b in slots[i + 1:]:
            for ma in por_motor[a]:
                for mb in por_motor[b]:
                    if ma["unidade"] != mb["unidade"]:
                        continue
                    comuns = ma["ancoras"] & mb["ancoras"]
                    if len(comuns) < minimo_ancoras or not (comuns & raras):
                        continue
                    # Série histórica não diverge de si mesma: 46% da tonelagem em 1890 e
                    # quase 100% no século XVIII são a mesma frase, não uma contradição.
                    # Quando as duas janelas citam anos e os anos não coincidem, a
                    # comparação não tem o que dizer.
                    anos_a = set(re.findall(r"\b(1[5-9]\d{2}|20\d{2})\b", ma["trecho"]))
                    anos_b = set(re.findall(r"\b(1[5-9]\d{2}|20\d{2})\b", mb["trecho"]))
                    if anos_a and anos_b and not (anos_a & anos_b):
                        continue
                    if abs(ma["valor"] - mb["valor"]) < 1e-9:
                        continue
                    maior = max(ma["valor"], mb["valor"]) or 1
                    if abs(ma["valor"] - mb["valor"]) / maior < 0.02:
                        continue  # arredondamento
                    chave = (a, b, ma["unidade"], ma["valor"], mb["valor"],
                             tuple(sorted(comuns))[:3])
                    if chave in vistos:
                        continue
                    vistos.add(chave)
                    achados.append({
                        "tipo": "divergência numérica",
                        "assunto": ", ".join(sorted(comuns)[:3]),
                        "unidade": ma["unidade"],
                        "motores": {a: ma["valor"], b: mb["valor"]},
                        "trechos": {a: ma["trecho"], b: mb["trecho"]},
                        "_forca": len(comuns) + 2 * len(comuns & raras),
                    })

    # Mais âncoras em comum, e âncoras mais raras, indicam que os dois trechos falam mesmo
    # da mesma coisa. Sem esse corte, uma pesquisa de regulação produziu 43 pares, quase
    # todos comparando grandezas diferentes que dividiam vocabulário técnico.
    achados.sort(key=lambda x: -x["_forca"])
    for a in achados:
        a.pop("_forca", None)
    return achados[:8]


def unidades_trocadas(resultados):
    """Mesmo assunto medido em unidades incompatíveis por motores diferentes.

    O efeito do ensaio do Quênia sobre renda entrou como percentual num motor e como valor
    absoluto em outro, em 12/08/2026. Não é divergência de número, é divergência de
    natureza, e some quando se compara só o valor.
    """
    incompativeis = [({"%", "pontos percentuais", "p.p."}, {"us$", "r$"})]
    por_motor = {r["slot"]: medidas_do_texto(r.get("conteudo") or "")
                 for r in resultados if not r.get("erro")}
    achados = []
    slots = list(por_motor)
    for i, a in enumerate(slots):
        for b in slots[i + 1:]:
            for ma in por_motor[a]:
                for mb in por_motor[b]:
                    comuns = ma["ancoras"] & mb["ancoras"]
                    if len(comuns) < 3:
                        continue
                    for g1, g2 in incompativeis:
                        if ({ma["unidade"], mb["unidade"]} & g1) and ({ma["unidade"], mb["unidade"]} & g2):
                            achados.append({
                                "tipo": "unidade incompatível",
                                "assunto": ", ".join(sorted(comuns)[:3]),
                                "motores": {a: f"{ma['valor']} {ma['unidade']}",
                                            b: f"{mb['valor']} {mb['unidade']}"},
                                "trechos": {a: ma["trecho"], b: mb["trecho"]},
                            })
    return achados[:5]


# ---------------------------------------------------------------- independência

def origens(resultados, verif):
    """Quantas origens distintas cada domínio e cada motor trazem.

    Consenso conta motores, e deveria contar origens: três motores citando o mesmo domínio
    são uma fonte, não três. É a diferença entre validação cruzada e eco.
    """
    por_motor, dominios_de = {}, defaultdict(set)
    for r in resultados:
        if r.get("erro"):
            continue
        reprovadas = {u for u, x in (verif.get(r["slot"], {}) or {}).items()
                      if x.get("estado") in V.FALHAS_DURAS}
        doms = {dominio(u) for u in (r.get("urls") or []) if u not in reprovadas}
        doms.discard("")
        por_motor[r["slot"]] = doms
        for d in doms:
            dominios_de[d].add(r["slot"])

    compartilhados = {d: sorted(ms) for d, ms in dominios_de.items() if len(ms) > 1}
    exclusivos = {s: sorted(d for d in doms if len(dominios_de[d]) == 1)
                  for s, doms in por_motor.items()}
    total = len(dominios_de)
    return {
        "dominios_distintos": total,
        "dominios_por_motor": {s: len(d) for s, d in por_motor.items()},
        "dominios_compartilhados": compartilhados,
        "dominios_exclusivos_por_motor": {s: len(d) for s, d in exclusivos.items()},
        "sobreposicao": round(len(compartilhados) / total, 3) if total else None,
    }


# ---------------------------------------------------------------- verificação

def verificar_rodada(pasta, rodada, termos, criticidade, sem_rede=False):
    arq = pasta / f"r{rodada}.json"
    if not arq.exists():
        return None
    dados = json.loads(arq.read_text(encoding="utf-8"))
    resultados = dados.get("resultados") or []
    log("VERIFICAR", f"{arq.name}: {len(resultados)} motores · criticidade {criticidade}")

    saida_agentes, decisoes = {}, []
    for r in resultados:
        slot = r.get("slot")
        if r.get("erro"):
            continue
        urls = r.get("urls") or []
        conteudo = r.get("conteudo") or ""
        if not urls:
            decisoes.append({"gatilho": "motor sem fonte", "motor": slot,
                             "pergunta": f"O motor {slot} respondeu sem nenhuma URL. "
                                         "Descarto a contribuição dele?"})
            continue

        problemas = V.verificar_urls(urls, conteudo, slot, not sem_rede)
        if termos and not sem_rede:
            V.verificar_tema(problemas, urls, termos, slot)
        problemas = {u: x for u, x in problemas.items() if x["estado"] != "ok"}

        citacoes = r.get("citacoes") or []
        for u, reg in problemas.items():
            reg["contexto"] = V.contexto_da_url(u, conteudo, citacoes=citacoes)
            lote = V.citacoes_no_trecho(reg["contexto"])
            if lote > 2:
                reg["citacoes_no_trecho"] = lote

        graves = V.duras(problemas)
        sem_rastro = [u for u, x in graves.items() if not x.get("contexto")]
        saida_agentes[slot] = problemas

        log("VERIFICAR", f"  {slot}: {len(urls)} URLs · {len(graves)} falhas duras · "
                         f"{len(problemas) - len(graves)} sinais fracos · "
                         f"{len(graves) - len(sem_rastro)} duras com trecho")

        for u, x in graves.items():
            if x["estado"] in ("inventada", "suspeita") and x.get("contexto"):
                decisoes.append({
                    "gatilho": "fonte provavelmente construída", "motor": slot, "url": u,
                    "pergunta": "Esta afirmação se apoiava numa URL que não existe. "
                                "Mantenho na rodada 2 ou descarto?",
                    "trecho": x["contexto"][:280]})

    # medidas do conjunto
    coerencia = divergencias_numericas(resultados) + unidades_trocadas(resultados)
    ind = origens(resultados, saida_agentes)

    for c in coerencia[:5]:
        decisoes.append({
            "gatilho": c["tipo"], "assunto": c.get("assunto"),
            "pergunta": "Os motores discordam do mesmo número. Qual vale?",
            "valores": c.get("motores"), "trechos": c.get("trechos")})

    exigidas = ORIGENS_EXIGIDAS.get(criticidade, 2)
    if ind["dominios_distintos"] and ind["sobreposicao"] is not None:
        if len(ind["dominios_compartilhados"]) == 0 and len(resultados) > 1:
            decisoes.append({
                "gatilho": "sem origem comum",
                "pergunta": "Nenhum domínio foi citado por mais de um motor. Não há "
                            "consenso por origem nesta rodada; sigo assim mesmo?"})

    pacote = {
        "rodada": rodada,
        "quando": datetime.now().isoformat(timespec="seconds"),
        "criticidade": criticidade,
        "origens_exigidas_para_consenso": exigidas,
        "para_o_fluxo": PARA_O_FLUXO.get(criticidade, False),
        "termos": termos,
        "por_motor": saida_agentes,
        "coerencia": coerencia,
        "independencia": ind,
        "decisoes": decisoes[:TETO_DECISOES],
        "decisoes_omitidas": max(0, len(decisoes) - TETO_DECISOES),
    }
    destino = pasta / f"r{rodada}_verificacao.json"
    destino.write_text(json.dumps(pacote, ensure_ascii=False, indent=2), encoding="utf-8")

    escrever_decisoes(pasta, rodada, pacote)
    log("VERIFICAR", f"gravado: {destino.name} e r{rodada}_decisoes.md · "
                     f"{len(pacote['decisoes'])} itens para o Danilo")
    return pacote


def escrever_decisoes(pasta, rodada, pacote):
    """O documento que o Danilo lê. Dez itens, uma pergunta fechada cada."""
    linhas = [f"# Decisões — rodada {rodada}", ""]
    linhas.append(f"Criticidade: {pacote['criticidade']} · consenso exige "
                  f"{pacote['origens_exigidas_para_consenso']} origem(ns) independente(s).")
    if pacote["para_o_fluxo"]:
        linhas.append("Em criticidade alta o fluxo para aqui: nada segue para a rodada 2 "
                      "ou para a redação antes destas respostas.")
    linhas.append("")

    if not pacote["decisoes"]:
        linhas.append("Nada precisa de você nesta rodada. Nenhum gatilho disparou.")
    for i, d in enumerate(pacote["decisoes"], 1):
        linhas.append(f"## {i}. {d['gatilho']}")
        if d.get("motor"):
            linhas.append(f"Motor: {d['motor']}")
        if d.get("url"):
            linhas.append(f"Fonte: {d['url']}")
        if d.get("assunto"):
            linhas.append(f"Assunto: {d['assunto']}")
        if d.get("valores"):
            linhas.append("Valores: " + " · ".join(f"{k}: {v}" for k, v in d["valores"].items()))
        if d.get("trecho"):
            linhas.append(f"\n> {d['trecho']}")
        if d.get("trechos"):
            for k, v in d["trechos"].items():
                linhas.append(f"\n> [{k}] {v}")
        linhas.append(f"\n**{d['pergunta']}**\n")

    if pacote["decisoes_omitidas"]:
        linhas.append(f"\n_Mais {pacote['decisoes_omitidas']} itens ficaram de fora deste "
                      "documento para caber em dez. Estão no JSON da verificação._")

    ind = pacote["independencia"]
    linhas += ["", "---", "", "## Panorama de origens", "",
               f"- domínios distintos: {ind['dominios_distintos']}",
               f"- citados por mais de um motor: {len(ind['dominios_compartilhados'])}",
               f"- sobreposição: {ind['sobreposicao']}"]
    (pasta / f"r{rodada}_decisoes.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description="Verifica uma rodada já coletada. Não gasta crédito.")
    p.add_argument("pasta", help="Pasta da pesquisa, onde estão r1.json e r2.json")
    p.add_argument("--rodada", type=int, choices=[1, 2], default=None)
    p.add_argument("--todas", action="store_true", help="Verifica todas as rodadas que existirem")
    p.add_argument("--termos", default=None, help="Termos centrais do tema, separados por vírgula")
    p.add_argument("--criticidade", choices=["baixa", "media", "alta"], default="media")
    p.add_argument("--sem-rede", action="store_true",
                   help="Não visita páginas. Só analisa o texto já coletado.")
    args = p.parse_args()

    pasta = Path(args.pasta).expanduser().resolve()
    if not pasta.is_dir():
        raise SystemExit(f"ERRO: pasta não encontrada: {pasta}")

    termos = [t.strip() for t in (args.termos or "").split(",") if t.strip()]
    if not termos:
        log("VERIFICAR", "sem --termos: a conferência de assunto não roda nesta execução")

    rodadas = [1, 2] if (args.todas or args.rodada is None) else [args.rodada]
    feitas = 0
    for n in rodadas:
        if verificar_rodada(pasta, n, termos, args.criticidade, args.sem_rede):
            feitas += 1
    if not feitas:
        raise SystemExit(f"ERRO: nenhuma rodada encontrada em {pasta}")


if __name__ == "__main__":
    main()
