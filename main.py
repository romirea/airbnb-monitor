"""
🏖️ Airbnb Aruba Monitor - Alertas por Telegram
===============================================
Monitorea Airbnb cada X minutos y te avisa por Telegram
cuando aparecen listings nuevos o con buen precio.

SETUP:
1. pip install requests python-dotenv
2. Crear bot en Telegram con @BotFather → copiar token
3. Enviar un mensaje a tu bot, luego obtener tu chat_id:
   https://api.telegram.org/bot<TOKEN>/getUpdates
4. Editar las variables de configuración abajo
5. python airbnb_monitor.py
"""

import requests
import json
import time
import os
from datetime import datetime

# ══════════════════════════════════════════
#  ⚙️  CONFIGURACIÓN — edita esto
# ══════════════════════════════════════════

TELEGRAM_TOKEN = "TU_TOKEN_AQUI"          # De @BotFather
TELEGRAM_CHAT_ID = "TU_CHAT_ID_AQUI"      # Tu chat_id personal

CHECK_INTERVAL_MINUTES = 30               # Cada cuántos minutos revisar
MAX_PRICE_PER_NIGHT = 200                 # Precio máximo por noche (USD)
MIN_BEDS = 1                              # Mínimo de camas
ENTIRE_HOME_ONLY = True                   # Solo casa/depto entero (sin habitaciones compartidas)
CHECK_IN = "2025-03-15"
CHECK_OUT = "2025-03-25"
ADULTS = 2
CURRENCY = "USD"

# ══════════════════════════════════════════
#  📡  AIRBNB API (no oficial)
# ══════════════════════════════════════════

AIRBNB_API_URL = "https://www.airbnb.com/api/v3/ExploreSearch"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-419",
    "X-Airbnb-API-Key": "d306zoyjsyarp7ifhu67rjxn52tv0t20",  # clave pública de la app web
    "Referer": "https://www.airbnb.com/",
}

def search_listings():
    """Busca listings en Airbnb para Aruba en las fechas indicadas."""
    
    params = {
        "operationName": "ExploreSearch",
        "locale": "es",
        "currency": CURRENCY,
    }
    
    variables = {
        "isTypeaheadSearch": False,
        "cdnCacheSafe": False,
        "source": "EXPLORE",
        "exploreRequest": {
            "metadataOnly": False,
            "version": "1.8.3",
            "itemsPerGrid": 50,
            "tabId": "home_tab",
            "refinementPaths": ["/homes"],
            "datePickerType": "calendar",
            "checkin": CHECK_IN,
            "checkout": CHECK_OUT,
            "adults": str(ADULTS),
            "query": "Aruba",
            "searchType": "PAGINATION",
            "federatedSearchSessionId": "abc123",
        }
    }
    
    # Fallback: usar la API de búsqueda alternativa más estable
    search_url = "https://www.airbnb.com/api/v2/search_results"
    search_params = {
        "key": "d306zoyjsyarp7ifhu67rjxn52tv0t20",
        "locale": "es",
        "currency": CURRENCY,
        "location": "Aruba",
        "checkin": CHECK_IN,
        "checkout": CHECK_OUT,
        "adults": ADULTS,
        "room_types[]": "Entire home/apt",  # Solo casa/depto entero
        "items_per_grid": 50,
        "section_offset": 0,
        "_format": "for_explore_search_web",
        "refinement_paths[]": "/homes",
        "selected_tab_id": "home_tab",
        "source": "EXPLORE",
        "search_type": "AUTOSUGGEST",
        "federated_search_id": "abc",
    }
    
    try:
        resp = requests.get(search_url, headers=HEADERS, params=search_params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        listings = []
        # Navegar la estructura de respuesta de Airbnb
        explore_tabs = data.get("explore_tabs", [])
        for tab in explore_tabs:
            sections = tab.get("sections", [])
            for section in sections:
                for listing_data in section.get("listings", []):
                    listing = listing_data.get("listing", {})
                    pricing = listing_data.get("pricing_quote", {})
                    
                    if not listing:
                        continue
                    
                    price_info = pricing.get("price", {})
                    price_str = price_info.get("total", {}).get("amount", 0) if isinstance(price_info, dict) else 0
                    
                    # Precio por noche
                    rate = pricing.get("rate", {})
                    price_per_night = rate.get("amount", 0) if rate else 0
                    
                    listings.append({
                        "id": listing.get("id"),
                        "name": listing.get("name", "Sin nombre"),
                        "room_type": listing.get("room_type_category", ""),
                        "price_per_night": float(price_per_night),
                        "price_total": float(price_str),
                        "beds": listing.get("beds", 0),
                        "bedrooms": listing.get("bedrooms", 0),
                        "rating": listing.get("avg_rating", 0),
                        "reviews": listing.get("reviews_count", 0),
                        "url": f"https://www.airbnb.com/rooms/{listing.get('id')}?checkin={CHECK_IN}&checkout={CHECK_OUT}&adults={ADULTS}",
                        "city": listing.get("city", "Aruba"),
                        "picture": listing.get("picture_url", ""),
                    })
        
        return listings
    
    except Exception as e:
        print(f"[{now()}] ⚠️  Error al buscar: {e}")
        return []

# ══════════════════════════════════════════
#  📱  TELEGRAM
# ══════════════════════════════════════════

def send_telegram(message):
    """Envía un mensaje por Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[{now()}] ❌ Error Telegram: {e}")
        return False

def format_listing_message(listing, tag="🆕 NUEVO"):
    """Formatea un listing para el mensaje de Telegram."""
    stars = "⭐" * round(listing["rating"]) if listing["rating"] else "Sin calificación"
    nights = 10  # 15 al 25 marzo = 10 noches
    
    room_label = "🏠 Casa/Depto entero"
    
    msg = f"""
{tag} <b>{listing['name']}</b>

{room_label}
💰 <b>${listing['price_per_night']:.0f}/noche</b> (~${listing['price_per_night'] * nights:.0f} total)
🛏️ {listing['beds']} camas · {listing['bedrooms']} habitaciones
{stars} {listing['rating']} ({listing['reviews']} reseñas)
📅 {CHECK_IN} → {CHECK_OUT}

🔗 <a href="{listing['url']}">Ver en Airbnb</a>
""".strip()
    return msg

# ══════════════════════════════════════════
#  🔄  LÓGICA PRINCIPAL
# ══════════════════════════════════════════

def now():
    return datetime.now().strftime("%H:%M:%S")

def filter_good_listings(listings):
    """Filtra listings que cumplen los criterios."""
    good = []
    for l in listings:
        if l["price_per_night"] <= 0:
            continue
        if l["price_per_night"] > MAX_PRICE_PER_NIGHT:
            continue
        if l["beds"] < MIN_BEDS:
            continue
        # Filtrar solo casa/depto entero
        if ENTIRE_HOME_ONLY:
            room_type = l.get("room_type", "").lower()
            # Excluir habitaciones privadas o compartidas
            if any(x in room_type for x in ["private_room", "shared_room", "hotel_room"]):
                continue
        good.append(l)
    return good

def main():
    seen_ids = set()
    first_run = True
    
    print(f"""
🏖️  Airbnb Aruba Monitor iniciado
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 Fechas: {CHECK_IN} → {CHECK_OUT}
💰 Precio máx: ${MAX_PRICE_PER_NIGHT}/noche
⏰ Revisando cada {CHECK_INTERVAL_MINUTES} min
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
    
    send_telegram(
        f"🏖️ <b>Monitor de Airbnb Aruba activado</b>\n\n"
        f"📅 {CHECK_IN} → {CHECK_OUT}\n"
        f"🏠 Solo casas/deptos enteros\n"
        f"💰 Precio máx: ${MAX_PRICE_PER_NIGHT}/noche\n"
        f"⏰ Revisando cada {CHECK_INTERVAL_MINUTES} minutos\n\n"
        f"Te avisaré cuando encuentre algo bueno 🎯"
    )
    
    while True:
        print(f"[{now()}] 🔍 Buscando listings...")
        listings = search_listings()
        
        if not listings:
            print(f"[{now()}] 😶 No se encontraron listings (puede ser error de API)")
        else:
            good = filter_good_listings(listings)
            print(f"[{now()}] ✅ {len(listings)} encontrados, {len(good)} con buen precio")
            
            new_ones = []
            for l in good:
                if l["id"] not in seen_ids:
                    new_ones.append(l)
                    seen_ids.add(l["id"])
            
            if first_run:
                # Primera vez: mostrar resumen de lo que hay disponible
                if good:
                    summary = (
                        f"📊 <b>Primera búsqueda completada</b>\n"
                        f"Encontré {len(good)} opciones bajo ${MAX_PRICE_PER_NIGHT}/noche.\n\n"
                        f"Las más baratas:"
                    )
                    send_telegram(summary)
                    
                    # Enviar los 3 más baratos
                    cheapest = sorted(good, key=lambda x: x["price_per_night"])[:3]
                    for l in cheapest:
                        send_telegram(format_listing_message(l, "💡 DISPONIBLE"))
                        time.sleep(1)
                else:
                    send_telegram(f"😕 No encontré listings bajo ${MAX_PRICE_PER_NIGHT}/noche en este momento. Seguiré buscando...")
                
                first_run = False
            
            elif new_ones:
                # Nuevos listings que no habíamos visto
                send_telegram(f"🚨 <b>¡{len(new_ones)} listing(s) nuevo(s) en Aruba!</b>")
                for l in sorted(new_ones, key=lambda x: x["price_per_night"])[:5]:
                    send_telegram(format_listing_message(l, "🆕 NUEVO"))
                    time.sleep(1)
        
        print(f"[{now()}] 💤 Esperando {CHECK_INTERVAL_MINUTES} minutos...\n")
        time.sleep(CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
