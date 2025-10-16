import logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
import sounddevice as sd
import numpy as np
import ggwave
import time
import threading
from queue import Queue

try:
    ggwave_instance = ggwave.init()
    logging.info("✅ GGWave zainicjalizowany poprawnie.")
except Exception as e:
    logging.error(f"❌ Błąd inicjalizacji GGWave: {e}")
    ggwave_instance = None

def send_via_ggwave(message: str, protocolId: int = 1, volume: int = 60):
 
    try:
        if not message:
            logging.warning("Pusta wiadomość, pomijam wysyłanie.")
            return None

        # limit GGWave
        if len(message.encode('utf-8')) > 100:
            logging.warning(f"Wiadomość zbyt długa ({len(message.encode('utf-8'))} bajtów), obcinam do 100 znaków.")
            message = message[:100]

        waveform = ggwave.encode(message, protocolId=protocolId, volume=volume)
        audio = np.frombuffer(waveform, dtype=np.float32)
        logging.debug(f"Rozmiar waveform: {len(waveform)} bajtów")
        sd.play(audio, samplerate=48000)
        sd.wait()
        logging.info(f"📡 [GGWave] Wysłano: {message}")
        time.sleep(0.3)  
        return waveform
    except Exception as e:
        logging.error(f"Błąd przy wysyłaniu GGWave: {e}")
        return None

def receive_via_ggwave(queue: Queue, stop_event: threading.Event, bot_name: str, silence_timeout: float = 15.0):

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
            if audio_level > 0.001:  
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
        
        with sd.InputStream(
            callback=callback, 
            channels=1, 
            samplerate=48000, 
            dtype='float32', 
            blocksize=1024,  
            latency='low',
            device=sd.default.device[0]  
        ) as stream:
            
            while not stop_event.is_set():
                #cisz a15 s
                if time.time() - last_data_time > silence_timeout:
                    logging.info(f"⏰ [{bot_name}] Timeout ciszy ({silence_timeout}s)")
                    break
                #szumanie
                if time.time() - start_time > 30:
                    logging.info(f"⏰ [{bot_name}] Maksymalny czas nasłuchiwania")
                    break
                    
                time.sleep(0.1)  
                
    except Exception as e:
        logging.error(f"❌ Błąd InputStream dla {bot_name}: {e}")
        queue.put((bot_name, None))
        return

    if decoded:
        logging.info(f"✅ {bot_name} ODEBRAŁ: '{decoded}'")
        queue.put((bot_name, decoded))
    else:
        logging.info(f"❌ {bot_name} nic nie odebrał")
        queue.put((bot_name, None))

