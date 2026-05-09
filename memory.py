import json
import os
from datetime import datetime

HISTORY_FILE = "historico.json"
MAX_ENTRIES = 50  # guarda as últimas 50 decisões

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_history(history):
    try:
        # Mantém só as últimas MAX_ENTRIES entradas
        trimmed = history[-MAX_ENTRIES:]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar histórico: {e}")

def add_entry(campaign_id, campaign_name, action, reason, metrics_before):
    history = load_history()
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "action": action,
        "reason": reason,
        "metrics_before": metrics_before
    }
    history.append(entry)
    save_history(history)

def format_history_for_prompt():
    history = load_history()
    if not history:
        return "Nenhuma decisão anterior registrada. Este é o primeiro ciclo."

    lines = []
    for h in history[-20:]:  # manda só as últimas 20 pro prompt
        lines.append(
            f"- {h['timestamp']} → Campanha '{h['campaign_name']}': "
            f"{h['action']} | Motivo: {h['reason']} | "
            f"ROAS na época: {h['metrics_before'].get('roas', 'N/A')} | "
            f"Custo na época: R$ {h['metrics_before'].get('cost', 'N/A')}"
        )
    return "\n".join(lines)
