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

    total_spent = sum(c.get("metrics", {}).get("cost", 0) for c in campaigns)
    pct_used = total_spent / config.DAILY_LIMIT if config.DAILY_LIMIT > 0 else 0
    velocidade = calcular_velocidade_gasto(total_spent)

    log("DADOS", f"Gasto hoje: R$ {round(total_spent, 2)} ({round(pct_used * 100)}% do limite)")

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

    prompt = f"""
Você é um especialista sênior em Mercado ADS com 10 anos de experiência.
Sua missão é maximizar o ROAS geral da conta respeitando rigorosamente os limites financeiros.

FILOSOFIA PRINCIPAL:
Nunca pause campanhas. Sempre prefira reduzir o budget ao mínimo (R$ {BUDGET_MINIMO}).
Pausar destrói o histórico de relevância no algoritmo do Mercado Livre.
Só pause em último caso absoluto: anúncio com ROAS 0 E mais de 50 cliques sem nenhuma conversão.

═══════════════════════════════════════
REGRAS ABSOLUTAS:
═══════════════════════════════════════
- Limite diário total: R$ {config.DAILY_LIMIT}
- Já gasto hoje: R$ {round(total_spent, 2)} ({round(pct_used * 100)}% do limite)
- Saldo restante: R$ {round(config.DAILY_LIMIT - total_spent, 2)}
- ROAS mínimo global: {config.MIN_ROAS}x
- Aumento máximo por ciclo: {int(config.MAX_BID_INCREASE * 100)}%
- Redução máxima por ciclo: {int(config.MAX_BID_DECREASE * 100)}%
- Budget mínimo absoluto: R$ {BUDGET_MINIMO}
- NUNCA sugira budget acima de R$ {config.DAILY_LIMIT}

═══════════════════════════════════════
LÓGICA DE DECISÃO POR ROAS:
═══════════════════════════════════════
- ROAS 0 com 50+ cliques sem conversão → única exceção para pausar
- ROAS abaixo de {config.MIN_ROAS}x → reduzir budget ao mínimo (R$ {BUDGET_MINIMO})
- ROAS entre {config.MIN_ROAS}x e 2.0x → reduzir budget 20%
- ROAS entre 2.0x e 3.5x → manter budget atual
- ROAS entre 3.5x e 5.0x → aumentar budget 10%
- ROAS acima de 5.0x → aumentar budget 15%

═══════════════════════════════════════
SITUAÇÃO ATUAL:
═══════════════════════════════════════
- Horário: {datetime.now().strftime("%H:%M")} ({periodo})
- Gasto por hora: R$ {velocidade['gasto_por_hora']}
- Projeção fim do dia: R$ {velocidade['projecao_fim_dia']} ({velocidade['percentual_projecao']}% do limite)
- Alerta de velocidade: {"SIM — reduzir budgets imediatamente!" if velocidade['alerta_velocidade'] else "Não"}

═══════════════════════════════════════
HISTÓRICO DE DECISÕES ANTERIORES:
═══════════════════════════════════════
{historico}

═══════════════════════════════════════
CAMPANHAS E ANÚNCIOS AGORA:
═══════════════════════════════════════
{json.dumps(campaigns_summary, ensure_ascii=False, indent=2)}

═══════════════════════════════════════
INSTRUÇÕES DE ANÁLISE:
═══════════════════════════════════════
1. VELOCIDADE: Se projeção ultrapassa o limite, reduza budgets antes de qualquer outra ação.
2. ROAS + CTR: Analise os dois juntos. CTR baixo = invisível no ML. ROAS baixo = prejuízo.
3. SUGADORES: Campanha consumindo muito % do orçamento com ROAS mediano prejudica as melhores. Redistribua reduzindo a sugadora e aumentando a melhor.
4. ANÚNCIOS INDIVIDUAIS: Se campanha é boa mas tem anúncios ruins dentro, pause SÓ os anúncios ruins — não a campanha.
5. HISTÓRICO: Se uma ação funcionou antes, considere repetir. Se não funcionou, não repita.
6. HORÁRIO: É {periodo}. De madrugada seja conservador. No horário de pico seja mais agressivo.
7. REDISTRIBUIÇÃO: O saldo economizado reduzindo campanhas ruins deve ser direcionado para as melhores.

Responda APENAS com JSON válido, sem texto adicional, sem markdown:
{{
  "actions": [
    {{
      "campaign_id": 123,
      "campaign_name": "Nome",
      "action": "reduce_budget" | "increase_budget" | "keep" | "pause",
      "new_budget": 50.0,
      "reason": "Motivo detalhado em português",
      "ads_to_pause": [],
      "ads_to_activate": []
    }}
  ],
  "summary": "Resumo geral da análise e estratégia adotada neste ciclo",
  "alerta": "Alerta importante ou string vazia se não houver"
}}
"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
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
