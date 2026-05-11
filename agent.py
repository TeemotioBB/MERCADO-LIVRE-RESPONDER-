import anthropic
import json
import uuid
from datetime import datetime
import ml_client
import memory
import config

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

LOG = []
BUDGET_MINIMO = 10.0

# Funções injetadas pelo main.py para desacoplar o ciclo
get_ai_mode = lambda: "auto"          # substituído em main.py
add_pending = lambda action: None     # substituído em main.py


def log(action, message):
    entry = {
        "time": datetime.now().strftime("%H:%M"),
        "action": action,
        "message": message
    }
    LOG.append(entry)
    print(f"[{entry['time']}] {action}: {message}")


def get_log():
    return LOG


def calcular_velocidade_gasto(total_spent):
    hora_atual = datetime.now().hour + datetime.now().minute / 60
    horas_passadas = max(hora_atual, 0.5)
    gasto_por_hora = total_spent / horas_passadas
    horas_restantes = max(24 - hora_atual, 0.1)
    projecao_fim_dia = total_spent + (gasto_por_hora * horas_restantes)
    percentual_projecao = projecao_fim_dia / config.DAILY_LIMIT
    return {
        "gasto_por_hora": round(gasto_por_hora, 2),
        "projecao_fim_dia": round(projecao_fim_dia, 2),
        "percentual_projecao": round(percentual_projecao * 100, 1),
        "alerta_velocidade": percentual_projecao > 1.1
    }


def verificar_pace(campaigns, total_spent):
    """
    Verifica o ritmo de gasto SEM chamar a IA — pura matemática.
    Retorna lista de alertas de pace por campanha.
    Horário comercial: 08h–22h (14 horas úteis).
    """
    agora = datetime.now()
    hora = agora.hour + agora.minute / 60

    # Fora do horário comercial: não alerta
    if hora < 8 or hora > 22:
        return []

    # Quantas horas do horário comercial já passaram
    horas_comerciais_passadas = max(hora - 8, 0.5)
    horas_comerciais_totais = 14.0  # 08h às 22h
    frac_dia_passada = horas_comerciais_passadas / horas_comerciais_totais

    alertas = []
    for c in campaigns:
        if c.get("status") != "active":
            continue

        budget = c.get("budget", 0)
        if budget <= 0:
            continue

        cost = c.get("metrics", {}).get("cost", 0)
        meta_ate_agora = budget * frac_dia_passada
        deficit = meta_ate_agora - cost
        deficit_pct = (deficit / meta_ate_agora * 100) if meta_ate_agora > 0 else 0

        # Alerta só se estiver mais de 40% abaixo do ritmo esperado
        if deficit_pct > 40:
            aumento_sugerido = round(min(deficit_pct / 100 * 30, 50))  # sugere até +50%
            alertas.append({
                "campaign_id": c["id"],
                "name": c.get("name", ""),
                "budget": round(budget, 2),
                "gasto_hoje": round(cost, 2),
                "meta_ate_agora": round(meta_ate_agora, 2),
                "deficit_pct": round(deficit_pct, 1),
                "aumento_lance_sugerido": aumento_sugerido,
            })

    return alertas


def run_agent():
    log("INÍCIO", f"Agente iniciado. Limite diário: R$ {config.DAILY_LIMIT}")
    mode = get_ai_mode()
    log("MODO", f"Modo atual: {mode}")

    try:
        campaigns = ml_client.get_campaigns()
    except Exception as e:
        log("ERRO", f"Falha ao buscar campanhas: {str(e)}")
        return

    if not campaigns:
        log("AVISO", "Nenhuma campanha encontrada.")
        return

    # Busca histórico dos últimos 30 dias
    try:
        history_30d = ml_client.get_campaigns_history(days=30)
        # Cria índice por campaign_id para lookup rápido
        hist_idx = {h["id"]: h for h in history_30d}
        log("DADOS", f"Histórico 30d carregado: {len(history_30d)} campanhas")
    except Exception as e:
        hist_idx = {}
        log("AVISO", f"Não foi possível carregar histórico 30d: {str(e)}")

    total_spent = sum(c.get("metrics", {}).get("cost", 0) for c in campaigns)
    pct_used = total_spent / config.DAILY_LIMIT if config.DAILY_LIMIT > 0 else 0
    velocidade = calcular_velocidade_gasto(total_spent)

    log("DADOS", f"Gasto hoje: R$ {round(total_spent, 2)} ({round(pct_used * 100)}% do limite)")

    # ── PACE CHECK (sem IA, custo zero) ──────────────────────────────────
    alertas_pace = verificar_pace(campaigns, total_spent)
    for alerta in alertas_pace:
        log("⚠️ RITMO BAIXO",
            f"'{alerta['name']}' gastou R${alerta['gasto_hoje']} de R${alerta['meta_ate_agora']} esperados "
            f"({alerta['deficit_pct']}% abaixo do ritmo). "
            f"👉 Aumente o lance ~{alerta['aumento_lance_sugerido']}% no Mercado Livre ADS."
        )
    # ─────────────────────────────────────────────────────────────────────

    if velocidade["alerta_velocidade"]:
        log("ALERTA VELOCIDADE", f"Ritmo atual vai estourar o limite! Projeção: R$ {velocidade['projecao_fim_dia']} ({velocidade['percentual_projecao']}%)")

    if pct_used >= 1.0:
        log("LIMITE ATINGIDO", f"100% do limite diário usado. Reduzindo todas as campanhas para o mínimo de R$ {BUDGET_MINIMO}.")
        for c in campaigns:
            if c.get("status") == "active":
                try:
                    ml_client.update_campaign_budget(c["id"], BUDGET_MINIMO)
                    log("BUDGET MÍNIMO", f"'{c['name']}' → R$ {BUDGET_MINIMO} — limite diário atingido.")
                    memory.add_entry(c["id"], c["name"], f"reduce_budget R${BUDGET_MINIMO}", "Limite diário 100% atingido", c.get("metrics", {}))
                except Exception as e:
                    log("ERRO", f"Falha ao reduzir '{c['name']}': {str(e)}")
        return

    if pct_used >= config.ALERT_THRESHOLD:
        log("ALERTA", f"{round(pct_used * 100)}% do limite atingido. Agente em modo conservador.")

    hora_atual = datetime.now().hour
    periodo = "manhã" if hora_atual < 12 else "tarde" if hora_atual < 18 else "noite"

    campaigns_summary = []
    for c in campaigns:
        m = c.get("metrics", {})
        try:
            ads = ml_client.get_ads_by_campaign(c["id"])
            ads_summary = []
            for ad in ads:
                am = ad.get("metrics", {})
                ads_summary.append({
                    "id": ad.get("id"),
                    "name": ad.get("name", "sem nome"),
                    "status": ad.get("status"),
                    "cost": round(am.get("cost", 0), 2),
                    "clicks": am.get("clicks", 0),
                    "roas": round(am.get("roas", 0), 2),
                    "ctr": round(am.get("ctr", 0), 4),
                    "cvr": round(am.get("cvr", 0), 4),
                    "cpc": round(am.get("cpc", 0), 2),
                })
        except Exception:
            ads_summary = []

        budget_atual = c.get("budget", BUDGET_MINIMO)
        campaigns_summary.append({
            "id": c["id"],
            "name": c["name"],
            "status": c["status"],
            "budget_atual": budget_atual,
            "budget_maximo_permitido": round(budget_atual * (1 + config.MAX_BID_INCREASE), 2),
            "budget_minimo_permitido": max(round(budget_atual * (1 - config.MAX_BID_DECREASE), 2), BUDGET_MINIMO),
            "cost": round(m.get("cost", 0), 2),
            "percentual_budget_usado": round((m.get("cost", 0) / max(budget_atual, 1)) * 100, 1),
            "clicks": m.get("clicks", 0),
            "prints": m.get("prints", 0),
            "roas": round(m.get("roas", 0), 2),
            "cpc": round(m.get("cpc", 0), 2),
            "ctr": round(m.get("ctr", 0), 4),
            "cvr": round(m.get("cvr", 0), 4),
            "direct_amount": round(m.get("direct_amount", 0), 2),
            "total_amount": round(m.get("total_amount", 0), 2),
            "anuncios": ads_summary
        })

    total_budget = sum(c.get("budget_atual", 0) for c in campaigns_summary)
    for cs in campaigns_summary:
        cs["percentual_orcamento_total"] = round((cs["budget_atual"] / total_budget * 100) if total_budget > 0 else 0, 1)

    historico = memory.format_history_for_prompt()

    # Dados compactos das campanhas com histórico 30d
    camps_compact = []
    for c in campaigns_summary:
        h = hist_idx.get(c["id"], {})
        camps_compact.append({
            "id": c["id"], "name": c["name"], "status": c["status"],
            "budget": c["budget_atual"], "bmax": c["budget_maximo_permitido"], "bmin": c["budget_minimo_permitido"],
            # Métricas de hoje
            "hoje": {"cost": c["cost"], "roas": c["roas"], "ctr": c["ctr"], "cvr": c["cvr"], "clicks": c["clicks"], "pct_budget": c["percentual_budget_usado"]},
            # Métricas dos últimos 30 dias
            "30d": {"roas": h.get("roas_30d", 0), "cost": h.get("cost_30d", 0), "clicks": h.get("clicks_30d", 0), "ctr": h.get("ctr_30d", 0), "cvr": h.get("cvr_30d", 0), "receita": h.get("receita_30d", 0)},
        })

    prompt = f"""Especialista ML ADS. Maximize ROAS respeitando limites.

REGRAS: limite_diario=R${config.DAILY_LIMIT}, gasto=R${round(total_spent,2)}({round(pct_used*100)}%), saldo=R${round(config.DAILY_LIMIT-total_spent,2)}, min_roas={config.MIN_ROAS}x, budget_min=R${BUDGET_MINIMO}, max_aumento={int(config.MAX_BID_INCREASE*100)}%, max_reducao={int(config.MAX_BID_DECREASE*100)}%
Hora:{datetime.now().strftime("%H:%M")}({periodo}) | Projecao:R${velocidade['projecao_fim_dia']}({velocidade['percentual_projecao']}%) | Alerta_velocidade:{"SIM" if velocidade['alerta_velocidade'] else "nao"}

DECISAO_POR_ROAS(use roas de HOJE se disponivel, senao use 30d):
ROAS=0+50cliques_sem_conv→pause | <{config.MIN_ROAS}x→budget_min | {config.MIN_ROAS}-2x→-20% | 2-3.5x→manter | 3.5-5x→+10% | >5x→+15%
NUNCA pause sem ROAS=0 E 50+cliques. Se hoje tem poucos dados, use historico 30d para decisao.
IMPORTANTE: campanha com roas_30d alto mas roas_hoje=0 e poucos cliques = MANTER (dia ruim pontual).
IMPORTANTE: campanha com roas_30d baixo E roas_hoje baixo = candidata a reducao.

HISTORICO_DECISOES_ANTERIORES:
{historico}

CAMPANHAS(hoje + ultimos 30 dias):
{json.dumps(camps_compact, ensure_ascii=False, separators=(',',':'))}

Responda APENAS JSON valido:
{{"actions":[{{"campaign_id":0,"campaign_name":"","action":"reduce_budget|increase_budget|keep|pause","new_budget":0.0,"reason":"motivo","ads_to_pause":[],"ads_to_activate":[]}}],"summary":"resumo","alerta":""}}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        decisions = json.loads(raw.strip())
    except Exception as e:
        log("ERRO", f"Falha na análise da IA: {str(e)}")
        return

    log("IA", decisions.get("summary", ""))

    if decisions.get("alerta"):
        log("ALERTA IA", decisions["alerta"])

    # Em modo MANUAL: apenas registra as sugestões no log, não executa nada
    if mode == "manual":
        for action in decisions.get("actions", []):
            log("SUGESTÃO", f"'{action['campaign_name']}': {action['action']} → R$ {action.get('new_budget', '?')} | {action.get('reason', '')}")
        log("FIM", "Ciclo concluído (modo manual — apenas sugestões, nada executado).")
        return

    # Em modo SEMI (supervisionado): enfileira pendências em vez de executar
    if mode == "semi":
        for action in decisions.get("actions", []):
            if action["action"] == "keep":
                log("MANTIDA", f"'{action['campaign_name']}' — {action.get('reason', '')}")
                continue
            pending_item = {
                "id": str(uuid.uuid4())[:8],
                "campaignId": action["campaign_id"],
                "name": action["campaign_name"],
                "action": action["action"],
                "currentBudget": next(
                    (c["budget_atual"] for c in campaigns_summary if c["id"] == action["campaign_id"]), 0
                ),
                "newBudget": action.get("new_budget"),
                "reason": action.get("reason", ""),
                "roas": next(
                    (c["roas"] for c in campaigns_summary if c["id"] == action["campaign_id"]), 0
                ),
                "urgency": _calc_urgency(action),
            }
            add_pending(pending_item)
            log("PENDENTE", f"'{action['campaign_name']}': {action['action']} aguarda aprovação do usuário")
        log("FIM", f"Ciclo concluído (modo supervisionado — {len([a for a in decisions.get('actions',[]) if a['action']!='keep'])} ações aguardam aprovação).")
        return

    # Modo AUTO: executa imediatamente
    for action in decisions.get("actions", []):
        campaign_id = action["campaign_id"]
        name = action["campaign_name"]
        act = action["action"]
        reason = action.get("reason", "")
        new_budget = action.get("new_budget")
        ads_to_pause = action.get("ads_to_pause", [])
        ads_to_activate = action.get("ads_to_activate", [])

        metrics_now = next(
            (c.get("metrics", {}) for c in campaigns if c["id"] == campaign_id), {}
        )

        try:
            if act == "pause":
                ml_client.pause_campaign(campaign_id)
                log("PAUSADA", f"'{name}' — {reason}")
                memory.add_entry(campaign_id, name, "pause", reason, metrics_now)

            elif act in ("reduce_budget", "increase_budget") and new_budget:
                safe_budget = max(min(new_budget, config.DAILY_LIMIT), BUDGET_MINIMO)
                ml_client.update_campaign_budget(campaign_id, safe_budget)
                emoji = "📉" if act == "reduce_budget" else "📈"
                log(act.upper(), f"{emoji} '{name}' → R$ {safe_budget} — {reason}")
                memory.add_entry(campaign_id, name, f"{act} R${safe_budget}", reason, metrics_now)

            else:
                log("MANTIDA", f"'{name}' — {reason}")

            for ad_id in ads_to_pause:
                try:
                    ml_client.update_campaign_budget(ad_id, BUDGET_MINIMO)
                    log("ANÚNCIO REDUZIDO", f"Anúncio {ad_id} dentro de '{name}' → R$ {BUDGET_MINIMO}")
                except Exception as e:
                    log("ERRO", f"Falha ao reduzir anúncio {ad_id}: {str(e)}")

            for ad_id in ads_to_activate:
                try:
                    ml_client.activate_campaign(ad_id)
                    log("ANÚNCIO REATIVADO", f"Anúncio {ad_id} dentro de '{name}'")
                except Exception as e:
                    log("ERRO", f"Falha ao reativar anúncio {ad_id}: {str(e)}")

        except Exception as e:
            log("ERRO", f"Falha ao executar ação em '{name}': {str(e)}")

    log("FIM", "Ciclo concluído.")


def _calc_urgency(action):
    roas = action.get("roas", 0) if isinstance(action, dict) else 0
    if action.get("action") in ("reduce_budget", "pause") and isinstance(roas, (int, float)) and roas < 1:
        return "critical"
    if action.get("action") == "increase_budget":
        return "high"
    return "medium"
