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

import ggwave
import sounddevice as sd
import numpy as np
import logging

def send_via_ggwave(message: str, protocolId=1, volume=10):
    """
    Wysyła wiadomość GGWave przez głośniki.
    """
    try:
        if not message:
            return None

        # ✅ w ggwave-wheels encode() to globalna funkcja, nie metoda obiektu
        waveform = ggwave.encode(message, protocolId, volume)
        audio = np.frombuffer(waveform, dtype=np.float32)
        sd.play(audio, samplerate=48000)
        sd.wait()
        logging.info(f"📡 [GGWave] Wysłano: {message}")
        return waveform
    except Exception as e:
        logging.error(f"Błąd przy wysyłaniu GGWave: {e}")
        return None
import ggwave
import sounddevice as sd
import numpy as np
import logging

def receive_via_ggwave(timeout=5.0):
    """
    Nasłuchuje mikrofonu i próbuje zdekodować wiadomość GGWave.
    """
    try:
        decoded = None

        def callback(indata, frames, time, status):
            nonlocal decoded
            if status:
                logging.warning(status)
            data_bytes = indata.tobytes()
            res = ggwave.decode(data_bytes)
            if res:
                decoded = res.decode("utf-8")

        with sd.InputStream(callback=callback, channels=1, samplerate=48000, dtype='float32', blocksize=1024):
            sd.sleep(int(timeout * 1000))

        if decoded:
            logging.info(f"📡 [GGWave] Odebrano: {decoded}")
        else:
            logging.info("⚠️ GGWave nie odebrał niczego.")

        return decoded
    except Exception as e:
        logging.error(f"Błąd przy odbiorze GGWave: {e}")
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
