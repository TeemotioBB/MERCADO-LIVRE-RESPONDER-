from apscheduler.schedulers.background import BackgroundScheduler
import agent
import config

scheduler = BackgroundScheduler()

def start():
    # Roda o agente assim que o sistema iniciar
    agent.run_agent()

    # Depois roda automaticamente a cada X minutos (padrão: 120 = 2 horas)
    scheduler.add_job(
        agent.run_agent,
        "interval",
        minutes=config.AGENT_INTERVAL_MINUTES,
        id="ml_ads_agent"
    )
    scheduler.start()
    print(f"Agente agendado para rodar a cada {config.AGENT_INTERVAL_MINUTES} minutos.")

def stop():
    scheduler.shutdown()
    print("Agente parado.")
