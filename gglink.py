import logging
import numpy as np
import ggwave  # ✅ poprawny import dla ggwave-wheels

# Inicjalizacja GGWave
try:
    ggwave_instance = ggwave.init()
    logging.info("✅ GGWave zainicjalizowany poprawnie.")
except Exception as e:
    logging.error(f"❌ Błąd inicjalizacji GGWave: {e}")
    ggwave_instance = None


def send_via_ggwave(message: str):
    """
    Koduje tekst do formatu dźwiękowego GGWave (bytes).
    """
    if not ggwave_instance:
        logging.error("GGWave nie jest zainicjalizowany.")
        return None

    if not message:
        return None

    try:
        payload = message.encode("utf-8")
        data = ggwave_instance.encode(payload)
        logging.info(f"📡 [GGWave] Zakodowano wiadomość ({len(data)} bajtów).")
        return np.frombuffer(data, dtype=np.uint8)
    except Exception as e:
        logging.error(f"Błąd przy kodowaniu GGWave: {e}")
        return None


def receive_via_ggwave(data):
    """
    Dekoduje dane audio z GGWave z powrotem na tekst.
    """
    if not ggwave_instance:
        logging.error("GGWave nie jest zainicjalizowany.")
        return None

    if data is None:
        return None

    try:
        if isinstance(data, np.ndarray):
            data = data.tobytes()

        decoded = ggwave_instance.decode(data)
        if decoded:
            decoded_text = decoded.decode("utf-8")
            logging.info(f"📡 [GGWave] Odebrano: {decoded_text}")
            return decoded_text
        else:
            logging.warning("⚠️ GGWave nie zwrócił żadnego tekstu.")
            return None
    except Exception as e:
        logging.error(f"Błąd przy dekodowaniu GGWave: {e}")
        return None
