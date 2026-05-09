import anthropic
import json
from datetime import datetime
import ml_client
import config

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

LOG = []

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

def run_agent():
    log("INÍCIO", "Agente iniciado. Coletando dados das campanhas...")

    # Coleta dados
    try:
        campaigns = ml_client.get_campaigns()
    except Exception as e:
        log("ERRO", f"Falha ao buscar campanhas: {str(e)}")
        return

    total_spent = sum(c.get("metrics", {}).get("cost", 0) for c in campaigns)
    pct_used = total_spent / config.DAILY_LIMIT if config.DAILY_LIMIT > 0 else 0

    log("DADOS", f"Gasto hoje: R$ {round(total_spent, 2)} ({round(pct_used * 100)}% do limite diário de R$ {config.DAILY_LIMIT})")

    # Alerta se passou do threshold
    if pct_used >= 1.0:
        log("LIMITE ATINGIDO", "100% do limite diário usado. Pausando todas as campanhas.")
        for c in campaigns:
            if c.get("status") == "active":
                try:
                    ml_client.pause_campaign(c["id"])
                    log("PAUSADA", f"Campanha '{c['name']}' pausada — limite diário atingido.")
                except Exception as e:
                    log("ERRO", f"Falha ao pausar '{c['name']}': {str(e)}")
        return

    if pct_used >= config.ALERT_THRESHOLD:
        log("ALERTA", f"{round(pct_used * 100)}% do limite diário atingido. Agente em modo conservador.")

    # Monta resumo das campanhas para a IA analisar
    campaigns_summary = []
    for c in campaigns:
        m = c.get("metrics", {})
        campaigns_summary.append({
            "id": c["id"],
            "name": c["name"],
            "status": c["status"],
            "budget": c.get("budget", 0),
            "cost": round(m.get("cost", 0), 2),
            "clicks": m.get("clicks", 0),
            "roas": round(m.get("roas", 0), 2),
            "cpc": round(m.get("cpc", 0), 2),
            "cvr": round(m.get("cvr", 0), 2),
            "ctr": round(m.get("ctr", 0), 2),
        })

    # Pede análise e decisões para a IA
    prompt = f"""
Você é um especialista em Mercado ADS. Analise as campanhas abaixo e decida as ações necessárias.

REGRAS OBRIGATÓRIAS:
- O limite diário total é R$ {config.DAILY_LIMIT}. Nunca sugira gastar acima disso.
- Já foi gasto hoje: R$ {round(total_spent, 2)} ({round(pct_used * 100)}% do limite).
- Campanhas com ROAS abaixo de {config.MIN_ROAS} devem ser pausadas.
- Nunca aumente o budget de uma campanha individual acima de R$ {config.DAILY_LIMIT}.
- Aumento máximo de lance: {int(config.MAX_BID_INCREASE * 100)}%.
- Redução máxima de lance: {int(config.MAX_BID_DECREASE * 100)}%.

CAMPANHAS ATUAIS:
{json.dumps(campaigns_summary, ensure_ascii=False, indent=2)}

Responda APENAS com um JSON válido, sem texto adicional, no formato:
{{
  "actions": [
    {{
      "campaign_id": 123,
      "campaign_name": "Nome",
      "action": "pause" | "activate" | "reduce_budget" | "increase_budget" | "keep",
      "new_budget": 50.0,
      "reason": "Motivo da decisão em português"
    }}
  ],
  "summary": "Resumo geral da análise em português"
}}
"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        decisions = json.loads(raw)
    except Exception as e:
        log("ERRO", f"Falha na análise da IA: {str(e)}")
        return

    log("IA", decisions.get("summary", ""))

    # Executa as decisões
    for action in decisions.get("actions", []):
        campaign_id = action["campaign_id"]
        name = action["campaign_name"]
        act = action["action"]
        reason = action.get("reason", "")
        new_budget = action.get("new_budget")

        try:
            if act == "pause":
                ml_client.pause_campaign(campaign_id)
                log("PAUSADA", f"'{name}' — {reason}")

            elif act == "activate":
                ml_client.activate_campaign(campaign_id)
                log("ATIVADA", f"'{name}' — {reason}")

            elif act in ("reduce_budget", "increase_budget") and new_budget:
                ml_client.update_campaign_budget(campaign_id, new_budget)
                log(act.upper(), f"'{name}' → R$ {new_budget} — {reason}")

            else:
                log("MANTIDA", f"'{name}' — {reason}")

        except Exception as e:
            log("ERRO", f"Falha ao executar ação em '{name}': {str(e)}")

    log("FIM", "Ciclo do agente concluído.")
