"""
🏖️ Airbnb Aruba Monitor - Alertas por Telegram
Comandos: /buscar, /ayuda
"""

import requests
import time
import os
import threading
import json
import re
from datetime import datetime

# ══════════════════════════════════════════
#  ⚙️  CONFIGURACIÓN
# ══════════════════════════════════════════

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

CHECK_INTERVAL_MINUTES = 30
MAX_PRICE_PER_NIGHT    = 130
MIN_BEDS               = 1
ENTIRE_HOME_ONLY       = True
CHECK_IN               = "2025-03-15"
CHECK_OUT              = "2025-03-25"
NIGHTS                 = 10
ADULTS                 = 2
CURRENCY               = "USD"

HIGHLIGHT_MIN_RATING  = 4.0
HIGHLIGHT_MIN_REVIEWS = 15

# ══════════════════════════════════════════
#  📡  AIRBNB — búsqueda via scraping web
# ══════════════════════════════════════════

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
})

def get_api_key():
    """Obtiene la API key pública de Airbnb desde la página principal."""
    try:
        resp = SESSION.get("https://www.airbnb.com", timeout=10)
        match = re.search(r'"key"\s*:\s*"(d\w{30,})"', resp.text)
        if match:
            return match.group(1)
    except:
        pass
    return "d306zoyjsyarp7ifhu67rjxn52tv0t20"

def search_listings():
    api_key = get_api_key()

    # Intentar con la API v2 primero
    url = "https://www.airbnb.com/api/v2/search_results"
    params = {
        "key": api_key,
        "locale": "en",
        "currency": CURRENCY,
        "location": "Aruba",
        "checkin": CHECK_IN,
        "checkout": CHECK_OUT,
        "adults": ADULTS,
        "room_types[]": "Entire home/apt",
        "items_per_grid": 50,
        "section_offset": 0,
        "_format": "for_explore_search_web",
        "refinement_paths[]": "/homes",
        "selected_tab_id": "home_tab",
        "source": "EXPLORE",
        "search_type": "AUTOSUGGEST",
        "federated_search_id": "aruba-search-001",
        "price_max": MAX_PRICE_PER_NIGHT,
    }

    headers = {
        "X-Airbnb-API-Key": api_key,
        "Accept": "application/json",
        "Referer": f"https://www.airbnb.com/s/Aruba/homes?checkin={CHECK_IN}&checkout={CHECK_OUT}&adults={ADULTS}",
    }

    try:
        resp = SESSION.get(url, params=params, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            print(f"[{now()}] ⚠️  API v2 devolvió {resp.status_code}, intentando método alternativo...")
            return search_listings_v2(api_key)

        data = resp.json()
        return parse_v2_response(data)

    except Exception as e:
        print(f"[{now()}] ⚠️  Error: {e}")
        return search_listings_v2(api_key)


def search_listings_v2(api_key):
    """Método alternativo: scraping de la página de resultados."""
    url = f"https://www.airbnb.com/s/Aruba/homes"
    params = {
        "checkin": CHECK_IN,
        "checkout": CHECK_OUT,
        "adults": ADULTS,
        "room_types[]": "Entire home/apt",
        "price_max": MAX_PRICE_PER_NIGHT,
        "currency": CURRENCY,
    }
    try:
        resp = SESSION.get(url, params=params, timeout=15)
        # Buscar el JSON embebido en la página
        match = re.search(r'<script[^>]*id="data-deferred-state"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
        if not match:
            match = re.search(r'"listings":\s*(\[.*?\])', resp.text, re.DOTALL)
        if match:
            try:
                raw = match.group(1)
                data = json.loads(raw)
                return parse_embedded_json(data)
            except:
                pass
        print(f"[{now()}] ⚠️  No se pudo parsear la respuesta de Airbnb")
        return []
    except Exception as e:
        print(f"[{now()}] ⚠️  Error método alternativo: {e}")
        return []


def parse_v2_response(data):
    listings = []
    for tab in data.get("explore_tabs", []):
        for section in tab.get("sections", []):
            for listing_data in section.get("listings", []):
                l = parse_listing(listing_data)
                if l:
                    listings.append(l)
    return listings


def parse_embedded_json(data):
    listings = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                l = parse_listing(item)
                if l:
                    listings.append(l)
    return listings


def parse_listing(listing_data):
    try:
        listing = listing_data.get("listing", listing_data)
        pricing = listing_data.get("pricing_quote", listing_data.get("pricingQuote", {}))

        if not listing.get("id"):
            return None

        # Precio por noche
        rate = pricing.get("rate", pricing.get("rate_with_service_fee", {}))
        price_per_night = 0.0
        if isinstance(rate, dict):
            price_per_night = float(rate.get("amount", rate.get("value", 0)) or 0)

        name = listing.get("name", "")
        has_pool = any(
            w in (name + " " + str(listing.get("amenities", ""))).lower()
            for w in ["pool", "piscina", "pileta", "zwembad"]
        )

        return {
            "id":              str(listing.get("id")),
            "name":            name,
            "room_type":       listing.get("room_type_category", listing.get("roomTypeCategory", "")),
            "price_per_night": price_per_night,
            "beds":            int(listing.get("beds", 0) or 0),
            "bedrooms":        int(listing.get("bedrooms", 0) or 0),
            "rating":          float(listing.get("avg_rating", listing.get("avgRating", 0)) or 0),
            "reviews":         int(listing.get("reviews_count", listing.get("reviewsCount", 0)) or 0),
            "has_pool":        has_pool,
            "url":             f"https://www.airbnb.com/rooms/{listing.get('id')}?checkin={CHECK_IN}&checkout={CHECK_OUT}&adults={ADULTS}",
        }
    except:
        return None

# ══════════════════════════════════════════
#  📱  TELEGRAM — enviar
# ══════════════════════════════════════════

def send_telegram(message, chat_id=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id or TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[{now()}] ❌ Error Telegram: {e}")
        return False

# ══════════════════════════════════════════
#  📱  TELEGRAM — escuchar comandos
# ══════════════════════════════════════════

last_update_id = None

def get_updates():
    global last_update_id
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 5, "offset": last_update_id}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("result", [])
    except:
        return []

def handle_commands(seen_ids):
    global last_update_id
    print(f"[{now()}] 👂 Escuchando comandos...")
    while True:
        updates = get_updates()
        for update in updates:
            last_update_id = update["update_id"] + 1
            message = update.get("message", {})
            text = message.get("text", "").strip().lower()
            chat_id = str(message.get("chat", {}).get("id", ""))

            if chat_id != str(TELEGRAM_CHAT_ID):
                continue

            if text.startswith("/buscar"):
                print(f"[{now()}] 📲 Comando /buscar recibido")
                send_telegram("🔍 Buscando ahora mismo, un segundo...", chat_id)
                listings = search_listings()
                good = filter_listings(listings)

                if not good:
                    send_telegram(
                        "😕 No encontré nada bajo los filtros actuales.\n\n"
                        f"Filtros activos: casa/depto entero · máx ${MAX_PRICE_PER_NIGHT}/noche · {ADULTS} personas\n"
                        f"Fechas: {CHECK_IN} → {CHECK_OUT}",
                        chat_id
                    )
                else:
                    trusted = [l for l in good if l["rating"] >= HIGHLIGHT_MIN_RATING and l["reviews"] >= HIGHLIGHT_MIN_REVIEWS]
                    send_telegram(
                        f"📊 <b>Resultado de búsqueda</b>\n"
                        f"Hay <b>{len(good)}</b> opciones bajo ${MAX_PRICE_PER_NIGHT}/noche"
                        + (f", <b>{len(trusted)}</b> destacadas 🌟" if trusted else "") + ".\n\nTe mando las mejores:",
                        chat_id
                    )
                    sorted_good = sorted(good, key=lambda x: (
                        -(x["rating"] >= HIGHLIGHT_MIN_RATING and x["reviews"] >= HIGHLIGHT_MIN_REVIEWS),
                        x["price_per_night"]
                    ))
                    for l in sorted_good[:5]:
                        send_telegram(format_listing_message(l, "🔎 DISPONIBLE"), chat_id)
                        time.sleep(1)

            elif text.startswith("/ayuda") or text.startswith("/start") or text.startswith("/help"):
                send_telegram(
                    "🏖️ <b>Comandos disponibles:</b>\n\n"
                    "/buscar — busca ahora y te manda lo disponible\n"
                    "/ayuda — muestra este mensaje\n\n"
                    f"📅 Fechas: {CHECK_IN} → {CHECK_OUT}\n"
                    f"💰 Máx: ${MAX_PRICE_PER_NIGHT}/noche · 👥 {ADULTS} personas\n"
                    f"🏠 Solo casas/deptos enteros\n"
                    f"🌟 Destaca: +{HIGHLIGHT_MIN_RATING}⭐ y +{HIGHLIGHT_MIN_REVIEWS} reseñas\n"
                    f"⏰ Revisión automática cada {CHECK_INTERVAL_MINUTES} min",
                    chat_id
                )
        time.sleep(2)

# ══════════════════════════════════════════
#  🔄  FILTROS Y FORMATO
# ══════════════════════════════════════════

def now():
    return datetime.now().strftime("%H:%M:%S")

def filter_listings(listings):
    good = []
    for l in listings:
        if not l or l["price_per_night"] <= 0:
            continue
        if l["price_per_night"] > MAX_PRICE_PER_NIGHT:
            continue
        if l["beds"] < MIN_BEDS:
            continue
        if ENTIRE_HOME_ONLY:
            room_type = l.get("room_type", "").lower()
            if any(x in room_type for x in ["private_room", "shared_room", "hotel_room"]):
                continue
        good.append(l)
    return good

def format_listing_message(listing, tag="🆕 NUEVO"):
    is_trusted = listing["rating"] >= HIGHLIGHT_MIN_RATING and listing["reviews"] >= HIGHLIGHT_MIN_REVIEWS
    header = f"🌟 <b>DESTACADO</b> · {tag}" if is_trusted else tag

    if listing["rating"]:
        rating_line = f"⭐ {listing['rating']:.1f} ({listing['reviews']} reseñas)"
        if is_trusted:
            rating_line += " ✅"
    else:
        rating_line = "⭐ Sin calificación aún"

    pool_line = "🏊 Tiene pileta" if listing["has_pool"] else ""
    total = listing["price_per_night"] * NIGHTS

    lines = [
        header,
        "",
        f"🏠 <b>{listing['name']}</b>",
        "",
        f"💰 <b>${listing['price_per_night']:.0f}/noche</b> · ${total:.0f} total ({NIGHTS} noches)",
        f"🛏️ {listing['beds']} camas · {listing['bedrooms']} hab.",
        rating_line,
    ]
    if pool_line:
        lines.append(pool_line)
    lines += [f"📅 {CHECK_IN} → {CHECK_OUT}", "", f'🔗 <a href="{listing["url"]}">Ver en Airbnb</a>']
    return "\n".join(lines)

# ══════════════════════════════════════════
#  🚀  MAIN
# ══════════════════════════════════════════

def main():
    seen_ids = set()
    first_run = True

    print(f"""
🏖️  Airbnb Aruba Monitor iniciado
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 {CHECK_IN} → {CHECK_OUT}
💰 Máx: ${MAX_PRICE_PER_NIGHT}/noche
👥 {ADULTS} personas · 🏠 Solo casa/depto entero
🌟 Destaca: +{HIGHLIGHT_MIN_RATING}⭐ y +{HIGHLIGHT_MIN_REVIEWS} reseñas
⏰ Revisando cada {CHECK_INTERVAL_MINUTES} min
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")

    t = threading.Thread(target=handle_commands, args=(seen_ids,), daemon=True)
    t.start()

    send_telegram(
        f"🏖️ <b>Monitor de Airbnb Aruba activado</b>\n\n"
        f"📅 {CHECK_IN} → {CHECK_OUT}\n"
        f"🏠 Solo casas/deptos enteros · 👥 {ADULTS} personas\n"
        f"💰 Máx: ${MAX_PRICE_PER_NIGHT}/noche\n"
        f"🌟 Destaco los que tienen +{HIGHLIGHT_MIN_RATING}⭐ y +{HIGHLIGHT_MIN_REVIEWS} reseñas\n"
        f"⏰ Revisando cada {CHECK_INTERVAL_MINUTES} minutos\n\n"
        f"Escribime /buscar cuando quieras ver qué hay disponible 🎯"
    )

    while True:
        print(f"[{now()}] 🔍 Buscando listings...")
        listings = search_listings()

        if not listings:
            print(f"[{now()}] 😶 Sin resultados (posible bloqueo de Airbnb)")
        else:
            good = filter_listings(listings)
            print(f"[{now()}] ✅ {len(listings)} encontrados · {len(good)} bajo ${MAX_PRICE_PER_NIGHT}/noche")

            new_ones = [l for l in good if l["id"] not in seen_ids]
            for l in new_ones:
                seen_ids.add(l["id"])

            if first_run:
                if good:
                    sorted_good = sorted(good, key=lambda x: (
                        -(x["rating"] >= HIGHLIGHT_MIN_RATING and x["reviews"] >= HIGHLIGHT_MIN_REVIEWS),
                        x["price_per_night"]
                    ))
                    trusted = [l for l in sorted_good if l["rating"] >= HIGHLIGHT_MIN_RATING and l["reviews"] >= HIGHLIGHT_MIN_REVIEWS]
                    send_telegram(
                        f"📊 <b>Primera búsqueda lista</b>\n"
                        f"Encontré <b>{len(good)}</b> opciones bajo ${MAX_PRICE_PER_NIGHT}/noche"
                        + (f", de las cuales <b>{len(trusted)}</b> son destacadas 🌟" if trusted else "") + ".\n\nTe mando las mejores:"
                    )
                    for l in sorted_good[:3]:
                        send_telegram(format_listing_message(l, "💡 DISPONIBLE"))
                        time.sleep(1)
                else:
                    send_telegram(f"😕 No encontré nada bajo ${MAX_PRICE_PER_NIGHT}/noche por ahora. Seguiré buscando cada {CHECK_INTERVAL_MINUTES} min...")
                first_run = False

            elif new_ones:
                trusted_new = [l for l in new_ones if l["rating"] >= HIGHLIGHT_MIN_RATING and l["reviews"] >= HIGHLIGHT_MIN_REVIEWS]
                if trusted_new:
                    send_telegram(f"🚨🌟 <b>¡{len(new_ones)} nuevo(s) en Aruba, {len(trusted_new)} destacado(s)!</b>")
                else:
                    send_telegram(f"🚨 <b>¡{len(new_ones)} listing(s) nuevo(s) en Aruba!</b>")

                ordered = sorted(new_ones, key=lambda x: (
                    -(x["rating"] >= HIGHLIGHT_MIN_RATING and x["reviews"] >= HIGHLIGHT_MIN_REVIEWS),
                    x["price_per_night"]
                ))
                for l in ordered[:5]:
                    send_telegram(format_listing_message(l, "🆕 NUEVO"))
                    time.sleep(1)

        print(f"[{now()}] 💤 Esperando {CHECK_INTERVAL_MINUTES} minutos...\n")
        time.sleep(CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
