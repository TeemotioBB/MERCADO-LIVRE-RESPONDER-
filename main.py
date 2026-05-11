import os
import requests as http_requests
from flask import Flask, jsonify, request
import scheduler
import agent
import config

app = Flask(__name__)


@app.route("/")
def index():
    return jsonify({
        "status": "Agente ML ADS rodando",
        "limite_diario": config.DAILY_LIMIT,
        "limite_mensal": config.MONTHLY_LIMIT,
        "min_roas": config.MIN_ROAS,
        "intervalo_minutos": config.AGENT_INTERVAL_MINUTES
    })


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
        return jsonify({
            "gasto_hoje": round(total_spent, 2),
            "limite_diario": config.DAILY_LIMIT,
            "percentual_usado": pct,
            "campanhas": len(campaigns)
        })
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/oauth/callback")
def oauth_callback():
    code = request.args.get("code")
    if not code:
        return jsonify({"erro": "code não encontrado na URL"}), 400

    resp = http_requests.post("https://api.mercadolibre.com/oauth/token", data={
        "grant_type": "authorization_code",
        "client_id": os.getenv("ML_APP_ID"),
        "client_secret": os.getenv("ML_CLIENT_SECRET"),
        "code": code,
        "redirect_uri": os.getenv("ML_REDIRECT_URI")
    })
    data = resp.json()

    access_token = data.get("access_token")
    user_id = data.get("user_id")

    if not access_token:
        return jsonify({"erro": "Falha ao obter token", "detalhes": data}), 400

    return jsonify({
        "✅ ML_ACCESS_TOKEN": access_token,
        "✅ ML_ADVERTISER_ID": user_id,
        "expires_in_segundos": data.get("expires_in"),
        "instrucao": "Copie os dois valores acima e cole nas variáveis do Railway"
    })


if __name__ == "__main__":
    scheduler.start()
    app.run(host="0.0.0.0", port=8080)
