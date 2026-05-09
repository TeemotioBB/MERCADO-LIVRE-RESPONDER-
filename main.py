from flask import Flask, jsonify
import scheduler
import agent
import config

app = Flask(__name__)

@app.route("/")
def index():
    total_spent = sum(
        c.get("metrics", {}).get("cost", 0)
        for c in []
    )
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

if __name__ == "__main__":
    scheduler.start()
    app.run(host="0.0.0.0", port=8080)
