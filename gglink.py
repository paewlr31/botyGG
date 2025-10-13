import logging
import time
import random
from stt import listen
from bot import get_response
from tts import speak
import numpy as np
import sounddevice as sd  
import ggwave


try:
    ggwave_instance = ggwave.init()
    logging.info(f"✅ GGWave zainicjalizowany poprawnie, ggwave_instance={ggwave_instance}, type={type(ggwave_instance)}")
except Exception as e:
    logging.error(f"❌ Błąd inicjalizacji GGWave: {e}")
    ggwave_instance = None

def send_via_ggwave(message: str):
    """
    Koduje tekst do formatu dźwiękowego GGWave (bytes). Zachowane dla zgodności.
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
    Dekoduje dane audio z GGWave z powrotem na tekst. Zachowane dla zgodności.
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

def play_ggwave_like_sound(message: str):
    """
    Generuje serię krótkich, robotycznych impulsów (pi pi pip pip pi) przez 5 sekund.
    """
    try:
        sample_rate = 48000
        duration = 5.0  
        pulse_duration = 0.1
        gap_duration = 0.05 
        freqs = [7000, 7400, 7480, 7520, 7560, 7600]   # Częstotliwości 
        pulse_samples = int(pulse_duration * sample_rate)
        gap_samples = int(gap_duration * sample_rate)
        total_samples = int(duration * sample_rate)
        audio = np.zeros(total_samples)

        current_sample = 0
        while current_sample < total_samples:
            # Generujemy krótki impuls
            freq = random.choice(freqs)  # Losowa częstotliwość
            t = np.linspace(0, pulse_duration, pulse_samples, False)
            pulse = 0.5 * np.sin(2 * np.pi * freq * t)
            # Dodajemy lekką modulację amplitudy
            pulse *= 0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t)
    
            end_sample = min(current_sample + pulse_samples, total_samples)
            audio[current_sample:end_sample] = pulse[:end_sample - current_sample]
    
            current_sample += pulse_samples + gap_samples
            if current_sample >= total_samples:
                break

        audio = np.clip(audio, -1.0, 1.0)
        sd.play(audio, sample_rate)
        sd.wait()
        logging.info("📢 Odtworzono serię krótkich, robotycznych impulsów przypominających GGWave.")
    except Exception as e:
        logging.error(f"Błąd odtwarzania syntetycznego piszczenia: {e}")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
