import os
from dotenv import load_dotenv

load_dotenv()

# Credenciais Mercado Livre
ML_ACCESS_TOKEN = os.getenv("ML_ACCESS_TOKEN", "")
ML_ADVERTISER_ID = os.getenv("ML_ADVERTISER_ID", "")
ML_SITE_ID = os.getenv("ML_SITE_ID", "MLB")

# Limites de orçamento
DAILY_LIMIT = float(os.getenv("DAILY_LIMIT", "250.00"))
MONTHLY_LIMIT = float(os.getenv("MONTHLY_LIMIT", "5000.00"))
ALERT_THRESHOLD = float(os.getenv("ALERT_THRESHOLD", "0.80"))
MIN_ROAS = float(os.getenv("MIN_ROAS", "1.0"))

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Configurações do agente
AGENT_INTERVAL_MINUTES = 120  # roda a cada 2 horas
MAX_BID_INCREASE = 0.15       # máximo 15% de aumento de lance
MAX_BID_DECREASE = 0.20       # máximo 20% de redução de lance
