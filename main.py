import os
import json
import urllib.parse
import requests as http_requests
from flask import Flask, jsonify, request, redirect, send_from_directory
from flask_cors import CORS
import scheduler
import agent
import config
import memory

app = Flask(__name__, static_folder=".")
CORS(app)

# ─────────────────────────────────────────────
# DASHBOARD — serve o HTML
# ─────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    return send_from_directory(".", "ml-ads-dashboard.html")


# ─────────────────────────────────────────────
# STATUS GERAL
# ─────────────────────────────────────────────
@app.route("/")
def index():
    return jsonify({
        "status": "Agente ML ADS rodando",
        "limite_diario": config.DAILY_LIMIT,
        "limite_mensal": config.MONTHLY_LIMIT,
        "min_roas": config.MIN_ROAS,
        "intervalo_minutos": config.AGENT_INTERVAL_MINUTES
    })


# ─────────────────────────────────────────────
# API: LOG em tempo real
# ─────────────────────────────────────────────
@app.route("/api/log")
def api_log():
    return jsonify(agent.get_log())


# ─────────────────────────────────────────────
# API: RODAR AGENTE MANUALMENTE
# ─────────────────────────────────────────────
@app.route("/api/rodar-agora", methods=["POST", "GET"])
def api_rodar_agora():
    agent.run_agent()
    return jsonify({"status": "ok", "log": agent.get_log()})


# ─────────────────────────────────────────────
# API: STATUS / KPIs GERAIS
# ─────────────────────────────────────────────
@app.route("/api/status")
def api_status():
    try:
        import ml_client
        from datetime import datetime

        campaigns = ml_client.get_campaigns()
        total_spent = sum(c.get("metrics", {}).get("cost", 0) for c in campaigns)
        total_clicks = sum(c.get("metrics", {}).get("clicks", 0) for c in campaigns)
        total_revenue = sum(c.get("metrics", {}).get("total_amount", 0) for c in campaigns)

        active = [c for c in campaigns if c.get("status") == "active"]
        roas_list = [c.get("metrics", {}).get("roas", 0) for c in active if c.get("metrics", {}).get("roas", 0) > 0]
        avg_roas = round(sum(roas_list) / len(roas_list), 2) if roas_list else 0

        pct = round((total_spent / config.DAILY_LIMIT) * 100, 1) if config.DAILY_LIMIT > 0 else 0

        hora_atual = datetime.now().hour + datetime.now().minute / 60
        horas_passadas = max(hora_atual, 0.5)
        gasto_por_hora = total_spent / horas_passadas
        horas_restantes = max(24 - hora_atual, 0.1)
        projecao = round(total_spent + gasto_por_hora * horas_restantes, 2)

        return jsonify({
            "gasto_hoje": round(total_spent, 2),
            "limite_diario": config.DAILY_LIMIT,
            "limite_mensal": config.MONTHLY_LIMIT,
            "percentual_usado": pct,
            "saldo_restante": round(config.DAILY_LIMIT - total_spent, 2),
            "projecao_fim_dia": projecao,
            "percentual_projecao": round((projecao / config.DAILY_LIMIT) * 100, 1),
            "alerta_velocidade": projecao > config.DAILY_LIMIT * 1.05,
            "roas_medio": avg_roas,
            "total_clicks": total_clicks,
            "total_receita": round(total_revenue, 2),
            "total_campanhas": len(campaigns),
            "campanhas_ativas": len(active),
            "campanhas_pausadas": len(campaigns) - len(active),
            "intervalo_minutos": config.AGENT_INTERVAL_MINUTES,
            "min_roas": config.MIN_ROAS,
        })
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


# ─────────────────────────────────────────────
# API: CAMPANHAS COMPLETAS COM MÉTRICAS
# ─────────────────────────────────────────────
@app.route("/api/campaigns")
def api_campaigns():
    try:
        import ml_client
        campaigns = ml_client.get_campaigns()
        result = []
        for c in campaigns:
            m = c.get("metrics", {})
            try:
                ads = ml_client.get_ads_by_campaign(c["id"])
            except Exception:
                ads = []
            result.append({
                "id": c["id"],
                "name": c.get("name", ""),
                "status": c.get("status", ""),
                "budget": c.get("budget", 0),
                "cost": round(m.get("cost", 0), 2),
                "roas": round(m.get("roas", 0), 2),
                "clicks": m.get("clicks", 0),
                "prints": m.get("prints", 0),
                "ctr": round(m.get("ctr", 0), 4),
                "cvr": round(m.get("cvr", 0), 4),
                "cpc": round(m.get("cpc", 0), 3),
                "direct_amount": round(m.get("direct_amount", 0), 2),
                "total_amount": round(m.get("total_amount", 0), 2),
                "lastAction": _get_last_action(c["id"]),
                "ads": [{
                    "id": a.get("id"),
                    "name": a.get("name", ""),
                    "status": a.get("status", ""),
                    "cost": round(a.get("metrics", {}).get("cost", 0), 2),
                    "roas": round(a.get("metrics", {}).get("roas", 0), 2),
                    "clicks": a.get("metrics", {}).get("clicks", 0),
                    "ctr": round(a.get("metrics", {}).get("ctr", 0), 4),
                } for a in ads]
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


def _get_last_action(campaign_id):
    hist = memory.load_history()
    for h in reversed(hist):
        if h.get("campaign_id") == campaign_id:
            action_str = h.get("action", "keep")
            if "reduce" in action_str:
                return "reduce_budget"
            if "increase" in action_str:
                return "increase_budget"
            if "pause" in action_str:
                return "pause"
            return "keep"
    return "keep"


# ─────────────────────────────────────────────
# API: APROVAÇÕES PENDENTES (modo supervisionado)
# ─────────────────────────────────────────────
_pending_actions = []

@app.route("/api/pending", methods=["GET"])
def api_pending():
    return jsonify(_pending_actions)


@app.route("/api/pending/approve/<action_id>", methods=["POST"])
def api_approve(action_id):
    global _pending_actions
    action = next((a for a in _pending_actions if a["id"] == action_id), None)
    if not action:
        return jsonify({"erro": "Ação não encontrada"}), 404
    try:
        import ml_client
        if action["action"] in ("increase_budget", "reduce_budget"):
            new_budget = action.get("newBudget", action.get("currentBudget"))
            safe = max(min(new_budget, config.DAILY_LIMIT), 10.0)
            ml_client.update_campaign_budget(action["campaignId"], safe)
            agent.log(action["action"].upper(), f"✅ '{action['name']}' → R$ {safe} (aprovado pelo usuário)")
            memory.add_entry(action["campaignId"], action["name"],
                             f"{action['action']} R${safe}", action["reason"],
                             {"roas": action.get("roas", 0)})
        elif action["action"] == "pause":
            ml_client.pause_campaign(action["campaignId"])
            agent.log("PAUSADA", f"✅ '{action['name']}' pausada pelo usuário")
        _pending_actions = [a for a in _pending_actions if a["id"] != action_id]
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/pending/reject/<action_id>", methods=["POST"])
def api_reject(action_id):
    global _pending_actions
    action = next((a for a in _pending_actions if a["id"] == action_id), None)
    if action:
        agent.log("REJEITADO", f"❌ Ação rejeitada pelo usuário: '{action['name']}'")
        _pending_actions = [a for a in _pending_actions if a["id"] != action_id]
    return jsonify({"status": "ok"})


@app.route("/api/pending/approve-all", methods=["POST"])
def api_approve_all():
    import ml_client
    errors = []
    for action in list(_pending_actions):
        try:
            if action["action"] in ("increase_budget", "reduce_budget"):
                safe = max(min(action.get("newBudget", action["currentBudget"]), config.DAILY_LIMIT), 10.0)
                ml_client.update_campaign_budget(action["campaignId"], safe)
            elif action["action"] == "pause":
                ml_client.pause_campaign(action["campaignId"])
        except Exception as e:
            errors.append(str(e))
    _pending_actions.clear()
    return jsonify({"status": "ok", "erros": errors})


@app.route("/api/pending/reject-all", methods=["POST"])
def api_reject_all():
    _pending_actions.clear()
    return jsonify({"status": "ok"})


# ─────────────────────────────────────────────
# API: HISTÓRICO DE DECISÕES
# ─────────────────────────────────────────────
@app.route("/api/pace")
def api_pace():
    """Verifica ritmo de gasto sem chamar a IA — custo zero."""
    try:
        import ml_client
        campaigns = ml_client.get_campaigns()
        total_spent = sum(c.get("metrics", {}).get("cost", 0) for c in campaigns)
        alertas = agent.verificar_pace(campaigns, total_spent)
        return jsonify({
            "total_spent": round(total_spent, 2),
            "alertas": alertas,
            "tem_alerta": len(alertas) > 0
        })
    except Exception as e:
        return jsonify({"erro": str(e)}), 500



    hist = memory.load_history()
    return jsonify(list(reversed(hist)))


# ─────────────────────────────────────────────
# API: CONFIGURAÇÕES — ler e salvar
# ─────────────────────────────────────────────
@app.route("/api/config", methods=["GET"])
def api_config_get():
    return jsonify({
        "DAILY_LIMIT": config.DAILY_LIMIT,
        "MONTHLY_LIMIT": config.MONTHLY_LIMIT,
        "ALERT_THRESHOLD": config.ALERT_THRESHOLD,
        "MIN_ROAS": config.MIN_ROAS,
        "AGENT_INTERVAL_MINUTES": config.AGENT_INTERVAL_MINUTES,
        "MAX_BID_INCREASE": config.MAX_BID_INCREASE,
        "MAX_BID_DECREASE": config.MAX_BID_DECREASE,
    })


@app.route("/api/config", methods=["POST"])
def api_config_save():
    data = request.get_json()
    try:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = f.readlines()

        keys_to_update = {
            "DAILY_LIMIT": data.get("DAILY_LIMIT"),
            "MONTHLY_LIMIT": data.get("MONTHLY_LIMIT"),
            "ALERT_THRESHOLD": data.get("ALERT_THRESHOLD"),
            "MIN_ROAS": data.get("MIN_ROAS"),
        }

        updated = set()
        new_lines = []
        for line in lines:
            written = False
            for k, v in keys_to_update.items():
                if line.startswith(k + "=") and v is not None:
                    new_lines.append(f"{k}={v}\n")
                    updated.add(k)
                    written = True
                    break
            if not written:
                new_lines.append(line)

        for k, v in keys_to_update.items():
            if k not in updated and v is not None:
                new_lines.append(f"{k}={v}\n")

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        if data.get("DAILY_LIMIT") is not None:
            config.DAILY_LIMIT = float(data["DAILY_LIMIT"])
        if data.get("MONTHLY_LIMIT") is not None:
            config.MONTHLY_LIMIT = float(data["MONTHLY_LIMIT"])
        if data.get("ALERT_THRESHOLD") is not None:
            config.ALERT_THRESHOLD = float(data["ALERT_THRESHOLD"])
        if data.get("MIN_ROAS") is not None:
            config.MIN_ROAS = float(data["MIN_ROAS"])

        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


# ─────────────────────────────────────────────
# API: AÇÃO MANUAL EM CAMPANHA
# ─────────────────────────────────────────────
@app.route("/api/campaign/<int:campaign_id>/action", methods=["POST"])
def api_campaign_action(campaign_id):
    data = request.get_json()
    action_type = data.get("action")
    try:
        import ml_client
        campaigns = ml_client.get_campaigns()
        camp = next((c for c in campaigns if c["id"] == campaign_id), None)
        if not camp:
            return jsonify({"erro": "Campanha não encontrada"}), 404

        current_budget = camp.get("budget", 10)

        if action_type == "increase":
            new_budget = round(min(current_budget * 1.15, config.DAILY_LIMIT), 2)
            ml_client.update_campaign_budget(campaign_id, new_budget)
            agent.log("AUMENTADO", f"📈 Manual: campanha #{campaign_id} → R$ {new_budget}")
            return jsonify({"status": "ok", "new_budget": new_budget})
        elif action_type == "decrease":
            new_budget = round(max(current_budget * 0.85, 10.0), 2)
            ml_client.update_campaign_budget(campaign_id, new_budget)
            agent.log("REDUZIDO", f"📉 Manual: campanha #{campaign_id} → R$ {new_budget}")
            return jsonify({"status": "ok", "new_budget": new_budget})
        elif action_type == "pause":
            ml_client.pause_campaign(campaign_id)
            agent.log("PAUSADA", f"Manual: campanha #{campaign_id} pausada")
            return jsonify({"status": "ok"})
        elif action_type == "activate":
            ml_client.activate_campaign(campaign_id)
            agent.log("ATIVADA", f"Manual: campanha #{campaign_id} ativada")
            return jsonify({"status": "ok"})

        return jsonify({"erro": "Ação inválida"}), 400
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


# ─────────────────────────────────────────────
# API: MODO DA IA
# ─────────────────────────────────────────────
_ai_mode = {"mode": "semi"}

@app.route("/api/mode", methods=["GET"])
def api_mode_get():
    return jsonify(_ai_mode)

@app.route("/api/mode", methods=["POST"])
def api_mode_set():
    data = request.get_json()
    mode = data.get("mode")
    if mode not in ("auto", "semi", "manual"):
        return jsonify({"erro": "Modo inválido"}), 400
    _ai_mode["mode"] = mode
    agent.log("MODO", f"Modo alterado para: {mode}")
    return jsonify({"status": "ok", "mode": mode})

# Expõe helpers para o agent.py
agent.get_ai_mode = lambda: _ai_mode["mode"]
agent.add_pending = lambda action: _pending_actions.append(action)


# ─────────────────────────────────────────────
# ROTAS LEGADAS
# ─────────────────────────────────────────────
@app.route("/log")
def log():
    return jsonify(agent.get_log())

@app.route("/rodar-agora")
def rodar_agora():
    agent.run_agent()
    return jsonify({"status": "Agente executado com sucesso", "log": agent.get_log()})

@app.route("/status")
def status():
    try:
        import ml_client
        campaigns = ml_client.get_campaigns()
        total_spent = sum(c.get("metrics", {}).get("cost", 0) for c in campaigns)
        pct = round((total_spent / config.DAILY_LIMIT) * 100, 1)
        return jsonify({"gasto_hoje": round(total_spent, 2), "limite_diario": config.DAILY_LIMIT,
                        "percentual_usado": pct, "campanhas": len(campaigns)})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route("/debug-ads")
def debug_ads():
    token = config.ML_ACCESS_TOKEN
    user_id = config.ML_ADVERTISER_ID
    site_id = config.ML_SITE_ID
    headers = {"Authorization": f"Bearer {token}", "api-version": "2", "Content-Type": "application/json"}
    r1 = http_requests.get("https://api.mercadolibre.com/users/me", headers={"Authorization": f"Bearer {token}"})
    from datetime import date
    hoje = date.today().isoformat()
    r2 = http_requests.get(
        f"https://api.mercadolibre.com/advertising/{site_id}/advertisers/{user_id}/product_ads/campaigns/search",
        headers=headers, params={"date_from": hoje, "date_to": hoje, "limit": 5}
    )
    return jsonify({"1_token_info": r1.json(), "2_campanhas": {"status": r2.status_code, "resposta": r2.json()}})

@app.route("/oauth/authorize")
def oauth_authorize():
    params = urllib.parse.urlencode({
        "response_type": "code", "client_id": os.getenv("ML_APP_ID"),
        "redirect_uri": os.getenv("ML_REDIRECT_URI"),
        "scope": "read_advertising write_advertising offline_access"
    })
    return redirect(f"https://auth.mercadolivre.com.br/authorization?{params}")

@app.route("/oauth/callback")
def oauth_callback():
    code = request.args.get("code")
    if not code:
        return jsonify({"erro": "code não encontrado na URL"}), 400
    resp = http_requests.post("https://api.mercadolibre.com/oauth/token", data={
        "grant_type": "authorization_code", "client_id": os.getenv("ML_APP_ID"),
        "client_secret": os.getenv("ML_CLIENT_SECRET"), "code": code,
        "redirect_uri": os.getenv("ML_REDIRECT_URI")
    })
    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        return jsonify({"erro": "Falha ao obter token", "detalhes": data}), 400
    return jsonify({"✅ ML_ACCESS_TOKEN": access_token, "✅ ML_ADVERTISER_ID": data.get("user_id"),
                    "expires_in_segundos": data.get("expires_in"), "scopes": data.get("scope"),
                    "instrucao": "Copie os dois valores acima e cole nas variáveis do Railway"})


if __name__ == "__main__":
    scheduler.start()
    app.run(host="0.0.0.0", port=8080)
