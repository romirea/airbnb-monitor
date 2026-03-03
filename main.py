"""
🏖️ Airbnb Aruba Monitor - Alertas por Telegram
"""

import requests
import time
import os
from datetime import datetime

# ══════════════════════════════════════════
#  ⚙️  CONFIGURACIÓN
# ══════════════════════════════════════════

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

CHECK_INTERVAL_MINUTES = 30
MAX_PRICE_PER_NIGHT    = 130       # USD por noche
MIN_BEDS               = 1
ENTIRE_HOME_ONLY       = True
CHECK_IN               = "2025-03-15"
CHECK_OUT              = "2025-03-25"
NIGHTS                 = 10
ADULTS                 = 2
CURRENCY               = "USD"

# Criterios para destacar un listing como "confiable"
HIGHLIGHT_MIN_RATING  = 4.0
HIGHLIGHT_MIN_REVIEWS = 15

# ══════════════════════════════════════════
#  📡  AIRBNB API
# ══════════════════════════════════════════

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-419",
    "X-Airbnb-API-Key": "d306zoyjsyarp7ifhu67rjxn52tv0t20",
    "Referer": "https://www.airbnb.com/",
}

def search_listings():
    search_url = "https://www.airbnb.com/api/v2/search_results"
    search_params = {
        "key": "d306zoyjsyarp7ifhu67rjxn52tv0t20",
        "locale": "es",
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
        "federated_search_id": "abc",
    }

    try:
        resp = requests.get(search_url, headers=HEADERS, params=search_params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        listings = []
        for tab in data.get("explore_tabs", []):
            for section in tab.get("sections", []):
                for listing_data in section.get("listings", []):
                    listing = listing_data.get("listing", {})
                    pricing = listing_data.get("pricing_quote", {})
                    if not listing:
                        continue

                    rate = pricing.get("rate", {})
                    price_per_night = float(rate.get("amount", 0)) if rate else 0.0

                    # Detectar pileta en nombre o amenities
                    name = listing.get("name", "")
                    amenities = listing.get("amenities", [])
                    has_pool = any(
                        word in (name + " " + str(amenities)).lower()
                        for word in ["pool", "piscina", "pileta", "zwembad"]
                    )

                    listings.append({
                        "id":              listing.get("id"),
                        "name":            name,
                        "room_type":       listing.get("room_type_category", ""),
                        "price_per_night": price_per_night,
                        "beds":            listing.get("beds", 0),
                        "bedrooms":        listing.get("bedrooms", 0),
                        "rating":          float(listing.get("avg_rating", 0) or 0),
                        "reviews":         int(listing.get("reviews_count", 0) or 0),
                        "has_pool":        has_pool,
                        "url":             f"https://www.airbnb.com/rooms/{listing.get('id')}?checkin={CHECK_IN}&checkout={CHECK_OUT}&adults={ADULTS}",
                    })

        return listings

    except Exception as e:
        print(f"[{now()}] ⚠️  Error al buscar: {e}")
        return []

# ══════════════════════════════════════════
#  📱  TELEGRAM
# ══════════════════════════════════════════

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
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

def format_listing_message(listing, tag="🆕 NUEVO"):
    # ¿Es un listing confiable?
    is_trusted = listing["rating"] >= HIGHLIGHT_MIN_RATING and listing["reviews"] >= HIGHLIGHT_MIN_REVIEWS

    # Badge principal
    if is_trusted:
        header = f"🌟 <b>DESTACADO</b> · {tag}"
    else:
        header = tag

    # Calificación
    if listing["rating"]:
        rating_line = f"⭐ {listing['rating']:.1f} ({listing['reviews']} reseñas)"
        if is_trusted:
            rating_line += " ✅"
    else:
        rating_line = "⭐ Sin calificación aún"

    # Pileta
    pool_line = "🏊 Tiene pileta" if listing["has_pool"] else ""

    # Precio total
    total = listing["price_per_night"] * NIGHTS

    msg = f"""{header}

🏠 <b>{listing['name']}</b>

💰 <b>${listing['price_per_night']:.0f}/noche</b> · ${total:.0f} total ({NIGHTS} noches)
🛏️ {listing['beds']} camas · {listing['bedrooms']} hab.
{rating_line}
{pool_line}
📅 {CHECK_IN} → {CHECK_OUT}

🔗 <a href="{listing['url']}">Ver en Airbnb</a>""".strip()

    # Limpiar líneas vacías si no hay pileta
    msg = "\n".join(line for line in msg.splitlines() if line.strip())
    return msg

# ══════════════════════════════════════════
#  🔄  FILTROS
# ══════════════════════════════════════════

def now():
    return datetime.now().strftime("%H:%M:%S")

def filter_listings(listings):
    good = []
    for l in listings:
        if l["price_per_night"] <= 0:
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

    send_telegram(
        f"🏖️ <b>Monitor de Airbnb Aruba activado</b>\n\n"
        f"📅 {CHECK_IN} → {CHECK_OUT}\n"
        f"🏠 Solo casas/deptos enteros\n"
        f"💰 Máx: ${MAX_PRICE_PER_NIGHT}/noche · 👥 {ADULTS} personas\n"
        f"🌟 Te destaco los que tienen +{HIGHLIGHT_MIN_RATING}⭐ y +{HIGHLIGHT_MIN_REVIEWS} reseñas\n"
        f"⏰ Revisando cada {CHECK_INTERVAL_MINUTES} minutos\n\n"
        f"¡Te aviso cuando aparezca algo bueno! 🎯"
    )

    while True:
        print(f"[{now()}] 🔍 Buscando listings...")
        listings = search_listings()

        if not listings:
            print(f"[{now()}] 😶 Sin resultados (posible error de API)")
        else:
            good = filter_listings(listings)
            print(f"[{now()}] ✅ {len(listings)} encontrados · {len(good)} bajo ${MAX_PRICE_PER_NIGHT}/noche")

            new_ones = [l for l in good if l["id"] not in seen_ids]
            for l in new_ones:
                seen_ids.add(l["id"])

            if first_run:
                if good:
                    # Ordenar: primero los destacados, luego por precio
                    sorted_good = sorted(good, key=lambda x: (
                        -(x["rating"] >= HIGHLIGHT_MIN_RATING and x["reviews"] >= HIGHLIGHT_MIN_REVIEWS),
                        x["price_per_night"]
                    ))
                    trusted = [l for l in sorted_good if l["rating"] >= HIGHLIGHT_MIN_RATING and l["reviews"] >= HIGHLIGHT_MIN_REVIEWS]
                    
                    send_telegram(
                        f"📊 <b>Primera búsqueda lista</b>\n"
                        f"Encontré <b>{len(good)}</b> opciones bajo ${MAX_PRICE_PER_NIGHT}/noche"
                        + (f", de las cuales <b>{len(trusted)}</b> son destacadas 🌟" if trusted else "") + ".\n\n"
                        f"Te mando las mejores:"
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

                # Primero los destacados, luego el resto
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
