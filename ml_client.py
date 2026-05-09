import requests
from datetime import date
import config

BASE_URL = "https://api.mercadolibre.com"

HEADERS = {
    "Authorization": f"Bearer {config.ML_ACCESS_TOKEN}",
    "api-version": "2",
    "Content-Type": "application/json"
}

def get_campaigns():
    today = date.today().isoformat()
    url = f"{BASE_URL}/advertising/{config.ML_SITE_ID}/advertisers/{config.ML_ADVERTISER_ID}/product_ads/campaigns/search"
    params = {
        "date_from": today,
        "date_to": today,
        "metrics": "clicks,prints,cost,cpc,ctr,roas,cvr,direct_amount,indirect_amount,total_amount",
        "limit": 50,
        "offset": 0
    }
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json().get("results", [])

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
    # Nunca ultrapassa o limite diário configurado
    safe_budget = min(new_budget, config.DAILY_LIMIT)
    url = f"{BASE_URL}/marketplace/advertising/{config.ML_SITE_ID}/product_ads/campaigns/{campaign_id}"
    payload = {"budget": safe_budget}
    response = requests.put(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()
