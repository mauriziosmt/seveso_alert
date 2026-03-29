import requests
import time
import os
import logging
from logging.handlers import RotatingFileHandler

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT")

if not TOKEN or not CHAT_ID:
    raise ValueError("TELEGRAM_TOKEN e TELEGRAM_CHAT devono essere definiti")

# Soglie ancora da perfezionare quando ottenuto un endpoint API funzionante.
STATIONS = {
    "Cantù Asnago": {
        "idro_id": "8119",
        "levels": [
            {"name": "gialla",    "threshold": 120, "emoji": "🟡"},
            {"name": "arancione", "threshold": 150, "emoji": "🟠"},
            {"name": "rossa",     "threshold": 180, "emoji": "🔴"},
        ],
    },
    "Paderno Palazzolo": {
        "idro_id": "8121",
        "levels": [
            {"name": "gialla",    "threshold": 160, "emoji": "🟡"},
            {"name": "arancione", "threshold": 200, "emoji": "🟠"},
            {"name": "rossa",     "threshold": 245, "emoji": "🔴"},
        ],
    },
    "Milano Niguarda": {
        "idro_id": "3118",
        "levels": [
            {"name": "gialla",    "threshold": 300, "emoji": "🟡"},
        ],
    },
}

SODA_API = (
    "https://www.dati.lombardia.it/resource/3e8b-w7ay.json"
    "?idsensore={sensor_id}"
    "&$order=data%20DESC"
    "&$limit=1"
)

# Rotating file handler: 100MB per file, max 5 file
handler = RotatingFileHandler("seveso.log", maxBytes=100_000_000, backupCount=5)
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

# alert_state[sensor_id] = nome del livello attivo ("gialla"/"arancione"/"rossa") oppure None
alert_state = {}

def send(msg):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg},
            timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        logger.error(f"Errore invio Telegram: {e}")


def get_level(sensor_id):
    url = SODA_API.format(sensor_id=sensor_id)
    r = requests.get(url, timeout=15)
    r.raise_for_status()

    data = r.json()
    logger.debug(f"Risposta SODA per sensore {sensor_id}: {data}")

    if not data:
        raise ValueError("Nessun dato ricevuto dall'API")

    valore = data[0].get("valore")
    if valore is None:
        raise ValueError(f"Campo 'valore' non trovato: {data[0]}")

    return float(valore), data[0].get("data", "N/D")


def get_active_level(levels, value):
    """Restituisce il livello di allerta attivo (il più alto superato), o None."""
    active = None
    for lvl in levels:
        if value >= lvl["threshold"]:
            active = lvl
    return active


send("✅ Monitor Seveso avviato. Il servizio è sperimentale e a scopo informativo, si raccomanda sempre di fare riferimento ai canali ufficiali.")
logger.info("Monitor Seveso avviato")

while True:
    for name, cfg in STATIONS.items():
        sensor_id = cfg["idro_id"]
        levels = cfg["levels"]

        try:
            level, timestamp = get_level(sensor_id)
            soglie_str = " | ".join(
                f"{lvl['emoji']} {lvl['name']}: {lvl['threshold']} cm"
                for lvl in levels
            )
            logger.info(f"{name} — livello: {level} cm (dati del: {timestamp}) | soglie: {soglie_str}")

            active = get_active_level(levels, level)
            active_name = active["name"] if active else None
            prev_name = alert_state.get(sensor_id)

            if active_name != prev_name:
                if active:
                    # Salita a un nuovo livello (o primo superamento)
                    msg = (
                        f"{active['emoji']} Seveso — possibile livello {active_name.upper()}\n"
                        f"📍 {name}\n"
                        f"📏 Livello: {level} cm (soglia {active_name}: {active['threshold']} cm)\n"
                        f"🕐 Rilevato: {timestamp}"
                        f"⚠️ Verifica SEMPRE sui canali ufficiali"
                    )
                    logger.warning(f"ALERT {active_name}: {name} a {level} cm")
                else:
                    # Rientro sotto tutte le soglie
                    msg = (
                        f"✅ Seveso rientrato nella norma\n"
                        f"📍 {name}\n"
                        f"📏 Livello: {level} cm\n"
                        f"🕐 Rilevato: {timestamp}"
                    )
                    logger.info(f"CLEAR: {name} rientrato a {level} cm")

                send(msg)
                alert_state[sensor_id] = active_name

        except Exception as e:
            logger.error(f"Errore stazione {name}: {e}")
            send(f"⚠️ Errore stazione {name}: {e}")

    time.sleep(600)