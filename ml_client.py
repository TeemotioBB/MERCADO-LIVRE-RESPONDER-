import requests
from datetime import date, timedelta
import config

BASE_URL = "https://api.mercadolibre.com"

HEADERS = {
    "Authorization": f"Bearer {config.ML_ACCESS_TOKEN}",
    "api-version": "2",
    "Content-Type": "application/json"
}

def get_campaigns(date_from=None, date_to=None):
    """Busca campanhas. Padrão: hoje. Passa date_from/date_to para histórico."""
    today = date.today().isoformat()
    url = f"{BASE_URL}/advertising/{config.ML_SITE_ID}/advertisers/{config.ML_ADVERTISER_ID}/product_ads/campaigns/search"
    params = {
        "date_from": date_from or today,
        "date_to": date_to or today,
        "metrics": "clicks,prints,cost,cpc,ctr,roas,cvr,direct_amount,indirect_amount,total_amount",
        "limit": 50,
        "offset": 0
    }
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json().get("results", [])

def get_campaigns_history(days=30):
    """Retorna métricas agregadas dos últimos N dias por campanha."""
    today = date.today()
    date_from = (today - timedelta(days=days)).isoformat()
    date_to = today.isoformat()
    campaigns = get_campaigns(date_from=date_from, date_to=date_to)
    # Retorna resumo compacto por campanha
    history = []
    for c in campaigns:
        m = c.get("metrics", {})
        history.append({
            "id": c["id"],
            "name": c.get("name", ""),
            "roas_30d": round(m.get("roas", 0), 2),
            "cost_30d": round(m.get("cost", 0), 2),
            "clicks_30d": m.get("clicks", 0),
            "ctr_30d": round(m.get("ctr", 0), 4),
            "cvr_30d": round(m.get("cvr", 0), 4),
            "receita_30d": round(m.get("total_amount", 0), 2),
        })
    return history

def get_ads_by_campaign(campaign_id):
    today = date.today().isoformat()
    url = f"{BASE_URL}/advertising/{config.ML_SITE_ID}/advertisers/{config.ML_ADVERTISER_ID}/product_ads/ad_groups/search"
    params = {
        "date_from": today,
        "date_to": today,
        "filters[campaigns]": campaign_id,
        "metrics": "clicks,prints,cost,cpc,ctr,roas,cvr,direct_amount,indirect_amount,total_amount",
        "limit": 50,
        "offset": 0
    }
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json().get("results", [])

def get_total_spent_today():
    campaigns = get_campaigns()
    total = sum(c.get("metrics", {}).get("cost", 0) for c in campaigns)
    return round(total, 2)

def pause_campaign(campaign_id):
    url = f"{BASE_URL}/marketplace/advertising/{config.ML_SITE_ID}/product_ads/campaigns/{campaign_id}"
    payload = {"status": "paused"}
    response = requests.put(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()

def activate_campaign(campaign_id):
    url = f"{BASE_URL}/marketplace/advertising/{config.ML_SITE_ID}/product_ads/campaigns/{campaign_id}"
    payload = {"status": "active"}
    response = requests.put(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()

def update_campaign_budget(campaign_id, new_budget):
    safe_budget = min(new_budget, config.DAILY_LIMIT)
    url = f"{BASE_URL}/marketplace/advertising/{config.ML_SITE_ID}/product_ads/campaigns/{campaign_id}"
    payload = {"budget": safe_budget}
    response = requests.put(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()
