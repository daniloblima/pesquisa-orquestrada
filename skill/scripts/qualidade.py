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
import sys
from datetime import date
from pathlib import Path

RAIZ_SKILL = Path(__file__).resolve().parent.parent
DESTINO = RAIZ_SKILL / "qualidade-motores.json"

# A nota que viaja com a skill. É o único artefato de medição que vai ao repositório
# público: agregado por motor, sem tema, sem URL e sem nome de pesquisa. O
# `qualidade-motores.json` fica de fora porque o histórico dele cita o tema de cada
# pesquisa feita, que é dado de uso.
#
# Ela é semente, não verdade. Quem instala parte desta nota e, assim que a série local
# tiver massa, passa a medir os próprios motores — os usos são outros, e o que cada um
# pesa é outro. As duas divergem de propósito, e o resumo mostra qual está valendo.
NOTA_PUBLICA = RAIZ_SKILL / "notas-motores.json"

# O que da foto interna pode ser publicado. `custo` absoluto fica de fora: é quanto o dono
# da série gastou, ou seja, volume de uso.
CAMPOS_PUBLICOS = ("rotulo", "pesquisas", "reprovadas", "sinais_fracos",
                   "precisao_fonte", "taxa_confirmacao", "confiabilidade",
                   "indice", "indice_recente", "precisao_recente", "delta_recente",
                   "amostra_suficiente", "faixa_precisao", "faixa_geral", "papel")

# A gravidade de cada estado é definida num lugar só, em buscar.py, porque a régua e o
# medidor precisam concordar. Duplicar a lista aqui seria criar duas verdades.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verificacao import FALHAS_DURAS, SINAIS_FRACOS, problemas_gravados  # noqa: E402

# Data em que a régua mudou. Nota medida antes disto somava falso positivo de tema e
# falha de rede do verificador na conta de erro de citação, então número anterior e
# número posterior medem coisas diferentes e não se comparam. Sem esta marca, a correção
# apareceria no painel como se todos os motores tivessem melhorado sozinhos no mesmo dia.
QUEBRA_DE_SERIE = "2026-08-12"


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
                    "sinais_fracos": 0,
                    "custo": 0.0, "execucoes": 0, "incidentes": 0, "slots": set(),
                    "erros": [], "reprovadas_detalhe": {}})
                a["slots"].add(r.get("slot"))
                a["urls"] += len(r.get("urls") or [])
                # Só falha dura pesa contra o motor. "Fora do tema" e "inconclusiva"
                # medem a conferência, e não a citação: das 161 reprovações acumuladas até
                # 12/08/2026, 103 eram desses dois estados, com falso positivo comprovado
                # num e falha de rede do próprio verificador no outro. Contá-las derrubava
                # a precisão de todos os motores e virou base de decisão sobre composição.
                probs = problemas_gravados(pasta, arq.name, r.get("slot"), r)
                a["reprovadas"] += sum(1 for reg in probs.values()
                                       if reg.get("estado") in FALHAS_DURAS)
                a["sinais_fracos"] += sum(1 for reg in probs.values()
                                          if reg.get("estado") in SINAIS_FRACOS)
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
                    n = r.get("falhas_duras_sem_rastro")
                    n = n if n is not None else "número não registrado nesta rodada:"
                    a["erros"].append({"rodada": arq.name, "tipo": "falha dura sem rastro",
                                       "detalhe": f"{n} fonte(s) com falha dura sem trecho localizável — "
                                                  "quarentena da afirmação, não do agente"})
                # Por que cada URL caiu: é o que permite ver se o motor melhora ou piora.
                for _, reg in probs.items():
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
                # Tema vem do meta.json escrito pela skill. Sem ele, o nome da pasta serve
                # de aproximação: um motor pode ser bom em regulação e ruim em literatura
                # acadêmica, e a régua global mistura os dois.
                "tema": (meta.get("tema_curto") or meta.get("area") or "").strip().lower(),
                "modelo": modelo,
                "rotulo": a["rotulo"],
                "urls": a["urls"],
                "reprovadas": a["reprovadas"],
                "sinais_fracos": a["sinais_fracos"],
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


def peso_por_idade(data, hoje, meia_vida):
    """Quanto uma medição daquele dia ainda pesa hoje.

    Sem `meia_vida`, tudo pesa 1 e a nota é o acumulado puro. Com ela, o peso cai pela
    metade a cada `meia_vida` dias: uma medição de três meses atrás com meia-vida de 30
    dias vale 0,125 de uma de hoje.

    Isso existe porque as duas leituras extremas erram. Só a última rodada é volátil demais
    para decidir composição. O acumulado puro é o oposto: carrega defeito de passado
    longínquo como se fosse de agora, e penaliza o motor que melhorou. O decaimento dá
    inércia sem congelar — e por ser contínuo, não tem o degrau de uma janela fixa, onde a
    medição de ontem vale tudo e a de anteontem vale zero.
    """
    if not meia_vida:
        return 1.0
    try:
        idade = (date.fromisoformat(str(hoje)) - date.fromisoformat(str(data))).days
    except Exception:
        return 1.0
    return 0.5 ** (max(idade, 0) / meia_vida)


def agregar(linhas, lim, hoje=None, meia_vida=None):
    """Consolida a série por motor. Com `meia_vida`, pondera cada medição pela idade."""
    motores = {}
    for l in linhas:
        m = motores.setdefault(l["modelo"], {
            "rotulo": l["rotulo"], "pesquisas": set(), "urls": 0, "reprovadas": 0,
            "sinais_fracos": 0,
            "custo": 0.0, "execucoes": 0, "incidentes": 0, "afirmacoes": 0,
            "confirmadas": 0, "tem_contrib": False})
        w = peso_por_idade(l.get("data"), hoje, meia_vida)
        m["pesquisas"].add(l["pesquisa"])
        for k in ("urls", "reprovadas", "sinais_fracos", "execucoes", "incidentes"):
            m[k] += (l.get(k, 0) or 0) * w
        m["custo"] += l["custo"] * w
        if l["afirmacoes"]:
            m["tem_contrib"] = True
            m["afirmacoes"] += l["afirmacoes"] * w
            m["confirmadas"] += (l["confirmadas"] or 0) * w

    brutas = {}
    for l in linhas:
        brutas[l["modelo"]] = brutas.get(l["modelo"], 0) + (l.get("urls", 0) or 0)

    pesos = lim["pesos_indice"]
    for modelo, m in motores.items():
        m["pesquisas"] = len(m["pesquisas"])
        m["urls_brutas"] = brutas.get(modelo, 0)
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
        # `urls_brutas` e não a ponderada: com decaimento, um motor de série longa cairia
        # abaixo do mínimo só por o tempo ter passado, e perderia a classificação sem ter
        # feito nada.
        suficiente = (m["urls_brutas"] >= lim["minimo_urls_para_avaliar"]
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


def publicar_nota(motores, lim, hoje, silencioso=False):
    """Grava a nota que viaja com a skill: agregado por motor, sem rastro de pesquisa.

    **Só substitui o que a medição local sustenta.** Motor sem massa aqui mantém a nota que
    veio junto. Sem essa guarda, a primeira execução numa instalação nova publicaria uma
    nota vazia por cima da semente e apagaria a curadoria antes mesmo de ela ser lida —
    medido em 21/08/2026, com `outputs/` vazio.
    """
    publico = dict((ler(NOTA_PUBLICA) or {}).get("motores") or {})
    for modelo, m in motores.items():
        if not m.get("amostra_suficiente"):
            continue
        d = {k: m[k] for k in CAMPOS_PUBLICOS if k in m}
        # Contagens saem inteiras: com decaimento elas viram float, e "urls: 500.9999"
        # numa nota publicada parece defeito.
        d["urls"] = int(round(m.get("urls_brutas") or m["urls"]))
        d["reprovadas"] = int(round(d.get("reprovadas") or 0))
        d["sinais_fracos"] = int(round(d.get("sinais_fracos") or 0))
        d["execucoes"] = int(round(m.get("execucoes") or 0))
        for k in ("precisao_fonte", "taxa_confirmacao", "confiabilidade", "precisao_recente"):
            if d.get(k) is not None:
                d[k] = round(d[k], 4)
        # Custo por rodada, e não o acumulado: serve para escolher motor sem dizer quanto
        # o dono da série gastou.
        if m.get("execucoes"):
            d["custo_medio_rodada_usd"] = round(m["custo"] / m["execucoes"], 4)
        d["medida_em"] = hoje
        publico[modelo] = d

    if not publico:
        return

    NOTA_PUBLICA.write_text(json.dumps({
        "atualizado_em": hoje,
        "_leia": ("Nota inicial dos motores, medida em uso real. Serve de ponto de partida: "
                  "assim que a sua série local tiver massa (ver limiares), ela passa a valer "
                  "e esta fica só como referência. As duas divergem de propósito, porque os "
                  "usos são outros. Nada aqui é escrito à mão — sai de qualidade.py sobre as "
                  "pesquisas feitas."),
        "_como_se_calcula": ("índice = média ponderada de precisão de fonte (peso 3), taxa de "
                             "confirmação (peso 2) e confiabilidade (peso 1), em base 100. "
                             "Precisão conta só falha dura. Confiabilidade desconta falha "
                             "total (1,0) e truncamento (0,5) por execução."),
        "_indice_recente": ("A mesma série com as medições antigas pesando menos: metade a "
                            "cada `meia_vida_dias` do config. `delta_recente` é a distância "
                            "entre as duas notas — positivo, o motor melhorou depois do que "
                            "a média longa registra; negativo, piorou. Nenhuma das duas "
                            "manda sozinha: a longa é volátil de menos e a curta de mais, e "
                            "onde elas divergem é onde o motor mudou."),
        "limiares_usados": lim,
        "motores": publico,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if silencioso:
        return
    novos = sum(1 for m in motores.values() if m.get("amostra_suficiente"))
    log(f"nota publicável: {len(publico)} motores em {NOTA_PUBLICA.name} "
        f"({novos} medidos aqui, {len(publico) - novos} preservados)")


def tabela_de_escolha(cfg, em_uso, linhas, heranca_em):
    """Uma linha por motor, com tudo que a escolha precisa saber antes de gastar.

    Existe porque a régua rodava tarde demais. O `qualidade.py --resumo` é chamado no passo
    3b, **depois** da rodada 1, quando o dinheiro já foi gasto; a escolha acontece no passo
    1. O diferencial do projeto existia, funcionava e não chegava na hora de decidir.

    Sai daqui pronta para virar aba, também para tirar a montagem da mão de quem lê o
    SKILL.md. Em 21/08/2026 o Danilo relatou que a aba vinha com combinações prontas em
    escolha única, quando o documento manda `multiSelect` com um item por motor — e sem
    custo à vista, embora `custo_tipico_usd` já estivesse no `config.json`. Dois desvios do
    mesmo documento, na mesma tela.
    """
    por_modelo = {mo: (m, f) for mo, m, f in em_uso}
    truncou, rodadas = {}, {}
    for l in linhas:
        rodadas[l["modelo"]] = rodadas.get(l["modelo"], 0) + (l.get("execucoes") or 0)
        truncou[l["modelo"]] = truncou.get(l["modelo"], 0) + sum(
            1 for e in (l.get("erros") or []) if e.get("tipo") == "truncado")

    log("\nMOTORES DISPONÍVEIS — monte a aba com multiSelect, um item por linha\n")
    log(f"  {'id':11}{'rótulo':26} {'índice':11} {'US$/rod':>8} {'nota':>6} {'recente':>8} "
        f"{'trunca':>7}  papel")
    log("-" * 110)
    for mo in cfg.get("motores") or []:
        m, fonte = por_modelo.get(mo["modelo"], ({}, None))
        n = rodadas.get(mo["modelo"], 0)
        t = truncou.get(mo["modelo"], 0)
        indice = m.get("indice")
        rec = m.get("indice_recente")
        marca = "*" if mo.get("padrao") else " "
        log(f"{marca} {mo['id']:11}{mo['rotulo'][:25]:26} {mo.get('indice', '—')[:11]:11} "
            f"{mo.get('custo_tipico_usd', 0):>8.2f} {str(indice or '—'):>6} "
            f"{str(rec or '—'):>8} {(f'{t}/{n}' if n else '—'):>7}  "
            f"{m.get('papel', 'sem medição')}"
            + (f"  [herdada]" if fonte == "herdada" else ""))
    log("\n  * sugestão de partida (padrao no config.json). Não é teto nem mínimo.")
    log("  US$/rod é custo típico por rodada, e a pesquisa tem duas.")
    log("  nota é a série inteira; recente é a mesma série com o antigo pesando menos.")
    log("  trunca é quantas rodadas o motor cortou no limite de tokens, do total medido.")
    log("\n  Um índice por família: dois motores do mesmo índice leem as mesmas páginas,")
    log("  e a concordância entre eles não valida nada.")


def herdada():
    """A nota que veio com a skill, se existir. Vazia numa série já madura não faz falta."""
    d = ler(NOTA_PUBLICA) or {}
    return d.get("motores") or {}, d.get("atualizado_em")


def main():
    p = argparse.ArgumentParser(description="Mede a qualidade dos motores pelas pesquisas feitas.")
    p.add_argument("--resumo", action="store_true", help="Só o que a skill precisa saber.")
    p.add_argument("--escolha", action="store_true",
                   help="A tabela da aba de escolha de motores, pronta para copiar.")
    args = p.parse_args()

    cfg, lim = carregar_cfg()
    raiz = raiz_outputs(cfg)
    if not raiz.exists():
        raise SystemExit(f"ERRO: pasta de pesquisas não encontrada: {raiz}")

    linhas = coletar(raiz)
    hoje_d = str(date.today())
    motores = agregar(linhas, lim, hoje_d)

    # A segunda leitura da mesma série, com as medições antigas valendo menos. Nenhuma das
    # duas manda sozinha: onde elas divergem é onde o motor mudou, e é isso que interessa
    # na hora de escolher.
    meia_vida = lim.get("meia_vida_dias")
    recentes = agregar(linhas, lim, hoje_d, meia_vida) if meia_vida else {}
    for modelo, m in motores.items():
        r = recentes.get(modelo) or {}
        m["indice_recente"] = r.get("indice")
        m["precisao_recente"] = r.get("precisao_fonte")
        if m.get("indice") is not None and r.get("indice") is not None:
            m["delta_recente"] = round(r["indice"] - m["indice"], 1)

    # A foto atual é sobrescrita a cada execução; a série de notas nunca. Sem ela não há
    # como saber se um motor melhorou ou piorou, que é o ponto de acompanhar.
    anterior = ler(DESTINO) or {}
    serie = anterior.get("serie_notas") or []
    hoje = str(date.today())

    for modelo, m in motores.items():
        registro = {
            "data": hoje, "modelo": modelo, "rotulo": m["rotulo"],
            "pesquisas": m["pesquisas"], "urls": m["urls"], "reprovadas": m["reprovadas"],
            "sinais_fracos": m["sinais_fracos"],
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
        "_reprovadas": ("'reprovadas' conta só falha dura: URL inexistente, inventada, "
                        "suspeita ou removida. 'sinais_fracos' conta fora do tema, "
                        "inconclusiva e citação imprecisa, que medem a conferência e não a "
                        "citação, e por isso não entram na precisão. Separação feita em "
                        "12/08/2026; séries anteriores a essa data somavam os dois e "
                        "subestimam a precisão. Domínio raiz saiu de dura para fraca em "
                        "21/08/2026, e séries anteriores contam essa citação como erro."),
        "limiares_usados": lim,
        "motores": {k: {x: y for x, y in v.items()} for k, v in motores.items()},
        "serie_notas": serie,
        "historico": linhas,
    }
    DESTINO.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    publicar_nota(motores, lim, hoje, silencioso=args.escolha)

    ordem = sorted(motores.items(), key=lambda kv: -(kv[1]["indice"] or 0))

    # Por tema, e só com massa. Reportar tema com uma pesquisa só trocaria uma régua
    # imprecisa por várias.
    por_tema = {}
    for l in linhas:
        if not l.get("tema"):
            continue
        d = por_tema.setdefault(l["tema"], {})
        m = d.setdefault(l["modelo"], {"rotulo": l["rotulo"], "urls": 0, "reprovadas": 0,
                                       "pesquisas": set()})
        m["urls"] += l["urls"]
        m["reprovadas"] += l["reprovadas"]
        m["pesquisas"].add(l["pesquisa"])
    MASSA_MINIMA = 3

    if not args.resumo and not args.escolha:
        log(f"\n{len(linhas)} medições em {len({l['pesquisa'] for l in linhas})} pesquisas\n")
        log(f"{'MOTOR':30} {'PESQ':>4} {'URLs':>5} {'PRECISÃO':>9} {'CONFIRM':>8} {'CONFIAB':>8} {'ÍNDICE':>7} {'RECENTE':>8}  FAIXA")
        log("-" * 96)
        for modelo, m in ordem:
            def pct(v):
                return f"{v * 100:.0f}%" if v is not None else "—"
            rec = m.get("indice_recente")
            d = m.get("delta_recente")
            col = "—" if rec is None else (f"{rec}" if d is None or abs(d) < 1
                                           else f"{rec} {'↑' if d > 0 else '↓'}")
            log(f"{m['rotulo'][:30]:30} {m['pesquisas']:>4} {int(m['urls_brutas']):>5} "
                f"{pct(m['precisao_fonte']):>9} {pct(m['taxa_confirmacao']):>8} "
                f"{pct(m['confiabilidade']):>8} {str(m['indice'] or '—'):>7} {col:>8}  {m['faixa_geral']}")

        maduros = {tema: d for tema, d in por_tema.items()
                   if max((len(m["pesquisas"]) for m in d.values()), default=0) >= MASSA_MINIMA}
        if maduros:
            log("\nPOR TEMA (só temas com 3+ pesquisas)")
            for tema, d in sorted(maduros.items()):
                log(f"  {tema}")
                for modelo, m in sorted(d.items(), key=lambda kv: -kv[1]["urls"]):
                    prec = (m["urls"] - m["reprovadas"]) / m["urls"] if m["urls"] else None
                    log(f"    {m['rotulo'][:28]:28} {len(m['pesquisas'])} pesq · "
                        f"{m['urls']:>4} URLs · precisão {prec:.0%}" if prec is not None else
                        f"    {m['rotulo'][:28]:28} sem URLs")
        elif por_tema:
            faltam = sorted(por_tema)
            log(f"\nPOR TEMA: ainda sem massa. Temas registrados: {', '.join(faltam)} "
                f"(mínimo {MASSA_MINIMA} pesquisas por tema)")

        c = lim["precisao_fonte"]
        log(f"\nRéguas atuais (config.json, não mexem em motor nenhum):")
        log(f"  precisão de fonte: confiável >= {c['confiavel']:.0%} · atenção >= {c['atencao']:.0%}")
        g = lim["indice_geral"]
        log(f"  índice geral: confiável >= {g['confiavel']} · atenção >= {g['atencao']}")
        log(f"  só classifica com {lim['minimo_urls_para_avaliar']}+ URLs e "
            f"{lim['minimo_pesquisas_para_avaliar']}+ pesquisas")
        if meia_vida:
            log(f"\n  ÍNDICE é a série inteira, cada medição valendo o mesmo. RECENTE é a "
                f"mesma série com\n  as medições antigas pesando menos — metade a cada "
                f"{meia_vida} dias. Seta quando divergem\n  em mais de um ponto: ↑ o motor "
                "melhorou depois do que a média longa registra, ↓ piorou.")

    if not args.resumo and not args.escolha:
        # Variação desde a última data medida antes de hoje.
        datas = sorted({x["data"] for x in serie if x["data"] < hoje})
        if datas:
            ant = {x["modelo"]: x for x in serie if x["data"] == datas[-1]}
            log(f"\nVARIAÇÃO DO ÍNDICE desde {datas[-1]}")
            if datas[-1] < QUEBRA_DE_SERIE:
                log(f"  A régua mudou em {QUEBRA_DE_SERIE}: 'fora do tema' e 'inconclusiva' deixaram")
                log("  de contar como erro de citação. A diferença abaixo mede a régua, e não o")
                log("  motor. Comparação de desempenho só a partir da próxima medição.")
            for modelo, m in ordem:
                a = ant.get(modelo)
                if a and a.get("indice") is not None and m["indice"] is not None:
                    d = m["indice"] - a["indice"]
                    seta = "subiu" if d > 0.05 else "caiu" if d < -0.05 else "estável"
                    if datas[-1] < QUEBRA_DE_SERIE:
                        seta = "régua mudou"
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

    # A nota que veio com a skill cobre o motor que a série local ainda não sustenta. É
    # semente: assim que a medição local tem massa, ela manda, porque os usos são outros e
    # o que cada um pesa é outro. As duas divergem de propósito.
    heranca, heranca_em = herdada()
    em_uso = []
    for modelo, m in ordem:
        em_uso.append((modelo, m, "local"))
    medidos = {modelo for modelo, _ in ordem if _.get("amostra_suficiente")}
    for modelo, h in heranca.items():
        if modelo in medidos:
            continue
        ja = next((i for i, (mo, _, _) in enumerate(em_uso) if mo == modelo), None)
        if ja is None:
            em_uso.append((modelo, h, "herdada"))
        else:
            em_uso[ja] = (modelo, h, "herdada")
    em_uso.sort(key=lambda t: -(t[1].get("indice") or 0))

    if not em_uso:
        log("\nNENHUMA PESQUISA MEDIDA AINDA, E NENHUMA NOTA HERDADA\n")
        log("  Até haver "
            f"{lim['minimo_pesquisas_para_avaliar']} pesquisas e "
            f"{lim['minimo_urls_para_avaliar']} URLs por motor,")
        log("  trate todos como 'confirmação com ressalva'.")
        log(f"\n  arquivo: {DESTINO}")
        return

    if args.escolha:
        tabela_de_escolha(cfg, em_uso, linhas, heranca_em)
        return

    log("\nCOMO TRATAR CADA MOTOR NESTA PESQUISA\n")
    for modelo, m, fonte in em_uso:
        quando = m.get("medida_em") or heranca_em
        marca = "" if fonte == "local" else f"  [nota herdada de {quando}, não medida aqui]"
        log(f"  {m['rotulo']} — {m['papel']}{marca}")
        log(f"      {PAPEL_EXPLICADO[m['papel']]}")

    if any(f == "herdada" for _, _, f in em_uso):
        log(f"\n  Nota herdada é ponto de partida, medida em outro uso. Ela vale até a sua")
        log(f"  série ter {lim['minimo_pesquisas_para_avaliar']} pesquisas e "
            f"{lim['minimo_urls_para_avaliar']} URLs para aquele motor; daí a sua medição")
        log("  passa a valer e as duas divergem, porque os usos são outros.")
    log(f"\n  arquivo: {DESTINO}")


if __name__ == "__main__":
    main()
