import logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
import sounddevice as sd
import numpy as np
import ggwave
import time
import threading
from queue import Queue



# Inicjalizacja GGWave
try:
    ggwave_instance = ggwave.init()
    logging.info("✅ GGWave zainicjalizowany poprawnie.")
except Exception as e:
    logging.error(f"❌ Błąd inicjalizacji GGWave: {e}")
    ggwave_instance = None

def send_via_ggwave(message: str, protocolId: int = 1, volume: int = 60):
    """
    Koduje tekst do fali audio (float32) i odtwarza przez głośniki.
    Zwraca waveform (bytes/bytearray) lub None.
    """
    try:
        if not message:
            logging.warning("Pusta wiadomość, pomijam wysyłanie.")
            return None

        # Ogranicz długość wiadomości do 100 znaków, aby zmieścić się w limicie GGWave
        if len(message.encode('utf-8')) > 100:
            logging.warning(f"Wiadomość zbyt długa ({len(message.encode('utf-8'))} bajtów), obcinam do 100 znaków.")
            message = message[:100]

        waveform = ggwave.encode(message, protocolId=protocolId, volume=volume)
        audio = np.frombuffer(waveform, dtype=np.float32)
        logging.debug(f"Rozmiar waveform: {len(waveform)} bajtów")
        sd.play(audio, samplerate=48000)
        sd.wait()
        logging.info(f"📡 [GGWave] Wysłano: {message}")
        time.sleep(0.3)  # Zwiększone opóźnienie na propagację dźwięku
        return waveform
    except Exception as e:
        logging.error(f"Błąd przy wysyłaniu GGWave: {e}")
        return None

def receive_via_ggwave(queue: Queue, stop_event: threading.Event, bot_name: str, silence_timeout: float = 15.0):
    """
    Nasłuchuje mikrofonu, aż do momentu zdekodowania wiadomości lub ciszy przez `silence_timeout` sekund.
    Wynik zapisuje do kolejki. Zatrzymuje się, gdy stop_event jest ustawiony.
    """
    if ggwave_instance is None:
        logging.error("❌ Brak instancji GGWave — nie można odbierać.")
        queue.put((bot_name, None))
        return

    decoded = None
    stream = None
    last_data_time = time.time()
    start_time = time.time()

    def callback(indata, frames, time_info, status):
        nonlocal decoded, last_data_time
        if status:
            logging.debug(f"[{bot_name}] Status: {status}")
        if stop_event.is_set():
            return
            
        try:
            # Sprawdź poziom audio - KLUCZOWE!
            audio_level = np.max(np.abs(indata))
            if audio_level > 0.001:  # Jeśli jest jakiś sygnał
                last_data_time = time.time()
                logging.debug(f"[{bot_name}] Poziom audio: {audio_level:.6f}")

            data_bytes = indata.tobytes()
            res = ggwave.decode(ggwave_instance, data_bytes)
            
            if res:
                try:
                    decoded_text = res.decode("utf-8")
                    logging.info(f"🎯 [{bot_name}] ZDEKODOWANO: '{decoded_text}'")
                    decoded = decoded_text
                    queue.put((bot_name, decoded))
                    # NIE ZATRZYMUJ STREAMU! - pozwól działać dalej
                    return
                except Exception as e:
                    logging.debug(f"[{bot_name}] Błąd dekodowania UTF-8: {e}")
                    decoded = str(res)
                    queue.put((bot_name, decoded))
                    return
                    
        except Exception as e:
            logging.debug(f"[{bot_name}] Błąd w callback: {e}")

    try:
        logging.info(f"🎧 {bot_name} nasłuchuje GGWave (timeout: {silence_timeout}s)...")
        
        # POPRAWIONE USTAWIENIA STREAMU:
        with sd.InputStream(
            callback=callback, 
            channels=1, 
            samplerate=48000, 
            dtype='float32', 
            blocksize=1024,  # ZWIĘKSZONY - lepsza wydajność
            latency='low',
            device=sd.default.device[0]  # JAWNE UŻYCIE URZĄDZENIA
        ) as stream:
            
            while not stop_event.is_set():
                # Sprawdź timeout ciszy
                if time.time() - last_data_time > silence_timeout:
                    logging.info(f"⏰ [{bot_name}] Timeout ciszy ({silence_timeout}s)")
                    break
                    
                # Maksymalny czas nasłuchiwania
                if time.time() - start_time > 30:
                    logging.info(f"⏰ [{bot_name}] Maksymalny czas nasłuchiwania")
                    break
                    
                time.sleep(0.1)  # Optymalne uśpienie
                
    except Exception as e:
        logging.error(f"❌ Błąd InputStream dla {bot_name}: {e}")
        queue.put((bot_name, None))
        return

    # ZAWSZE zwróć wynik przez kolejkę
    if decoded:
        logging.info(f"✅ {bot_name} ODEBRAŁ: '{decoded}'")
        queue.put((bot_name, decoded))
    else:
        logging.info(f"❌ {bot_name} nic nie odebrał")
        queue.put((bot_name, None))

def play_ggwave_like_sound(duration: float = 2.0):
    """
    Krótki testowy dźwięk do debugowania.
    """
    try:
        sr = 48000
        t = np.linspace(0, duration, int(sr * duration), False)
        tone = 0.2 * np.sin(2 * np.pi * 6000 * t)
        sd.play(tone, sr)
        sd.wait()
        logging.info("Testowy dźwięk odtworzony.")
    except Exception as e:
        logging.error(f"Błąd odtwarzania testowego tonu: {e}")