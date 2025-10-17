import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QPushButton, QVBoxLayout, QWidget
from PyQt5.QtCore import QThread, pyqtSignal
import logging
from logging.handlers import QueueHandler
import queue
import threading
import time
import random
import speech_recognition as sr
from gtts import gTTS
from playsound import playsound
import os
import tempfile
import sounddevice as sd
import numpy as np
import ggwave
from queue import Queue
from openai import OpenAI
from dotenv import load_dotenv

# Konfiguracja logowania
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

# Inicjalizacja OpenAI
load_dotenv("klucz.env")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Inicjalizacja GGWave
try:
    ggwave_instance = ggwave.init()
    logging.info("✅ GGWave zainicjalizowany poprawnie.")
except Exception as e:
    logging.error(f"❌ Błąd inicjalizacji GGWave: {e}")
    ggwave_instance = None

# Funkcja OpenAI
def get_response(user_input, system_prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            max_tokens=30,
            temperature=0.8,
            top_p=0.95
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Błąd API Open AI: {str(e)}")
        return f"Błąd API Open AI: {str(e)}"

# Funkcje GGWave
def send_via_ggwave(message: str, protocolId: int = 1, volume: int = 60):
    try:
        if not message:
            logging.warning("Pusta wiadomość, pomijam wysyłanie.")
            return None

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
    last_data_time = time.time()
    start_time = time.time()

    def callback(indata, frames, time_info, status):
        nonlocal decoded, last_data_time
        if status:
            logging.debug(f"[{bot_name}] Status: {status}")
        if stop_event.is_set():
            return
            
        try:
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
                if time.time() - last_data_time > silence_timeout:
                    logging.info(f"⏰ [{bot_name}] Timeout ciszy ({silence_timeout}s)")
                    break
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

# Funkcja STT
def listen():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        logging.info("🎤 Mów teraz... (5 sekund na rozpoczęcie)")
        try:
            audio = r.listen(source, timeout=5)
            text = r.recognize_google(audio, language="pl-PL")
            return text
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            logging.error(f"Błąd połączenia ze STT: {str(e)}")
            return ""

# Funkcja TTS
def speak(text):
    if not text or not text.strip():
        return
    try:
        logging.info(f"Mówię: {text}")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tts = gTTS(text=text, lang="pl")
            tts.save(fp.name)
            temp_path = fp.name
        playsound(temp_path)
        os.remove(temp_path)
    except Exception as e:
        logging.error(f"Błąd w TTS: {e}")

# Klasa Bot
class Bot:
    def __init__(self, name, system_prompt):
        self.name = name
        self.system_prompt = system_prompt

# Wątek główny aplikacji
class MainThread(QThread):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = False
        self.bots = []
        self.last_input = None
        self.last_speaker = None
        self.silence_counter = 0

    def run(self):
        self.running = True
        self.log_signal.emit("🤖 Witaj! Rozpoczynamy rozmowę. Powiedz 'do widzenia', aby zakończyć.")
        self.log_signal.emit("Komendy: 'Dodaj bota <nazwa> jako <charakter>', 'Idź bot <nazwa>'")

        while self.running:
            try:
                user_input = listen()

                if user_input:
                    self.silence_counter = 0
                    self.log_signal.emit(f"🧍 Ty: {user_input}")
                    self.last_input = user_input
                    self.last_speaker = None

                    # Obsługa poleceń
                    if user_input.lower().startswith("dodaj bota"):
                        try:
                            parts = user_input.lower().split(" jako ")
                            bot_name = parts[0].replace("dodaj bota ", "").strip()
                            bot_character = parts[1].strip()
                            self.bots.append(Bot(bot_name, f"Jesteś {bot_character}, który odpowiada w języku polskim."))
                            response = f"Dodano bota {bot_name} jako {bot_character}."
                            self.log_signal.emit(f"🤖 System: {response}")
                            speak(response)
                        except IndexError:
                            response = "Błąd: Podaj nazwę bota i charakter, np. 'Dodaj bota Rafał jako pisarz'."
                            self.log_signal.emit(f"🤖 System: {response}")
                            speak(response)
                        continue

                    if user_input.lower().startswith("idź bot"):
                        try:
                            bot_name = user_input.lower().replace("idź bot ", "").strip()
                            bots_before = len(self.bots)
                            self.bots = [bot for bot in self.bots if bot.name.lower() != bot_name.lower()]
                            if len(self.bots) < bots_before:
                                response = f"Usunięto bota {bot_name}."
                                if self.last_speaker and self.last_speaker.lower() == bot_name.lower():
                                    self.last_speaker = None
                            else:
                                response = f"Nie znaleziono bota {bot_name}."
                            self.log_signal.emit(f"🤖 System: {response}")
                            speak(response)
                        except Exception:
                            response = "Błąd: Podaj poprawną nazwę bota, np. 'Idź bot Rafał'."
                            self.log_signal.emit(f"🤖 System: {response}")
                            speak(response)
                        continue

                    if "do widzenia" in user_input.lower():
                        response = "Do widzenia! Kończę rozmowę."
                        self.log_signal.emit(f"🤖 System: {response}")
                        speak(response)
                        self.running = False
                        break

                else:
                    self.silence_counter += 1

                if self.bots:
                    if user_input:
                        for bot in self.bots:
                            response = get_response(user_input, bot.system_prompt)
                            self.log_signal.emit(f"🤖 {bot.name}: {response}")
                            try:
                                speak(f"{bot.name} mówi: {response}")
                                self.last_input = response
                                self.last_speaker = bot.name
                                time.sleep(0.5)
                            except Exception as e:
                                self.log_signal.emit(f"Błąd TTS dla {bot.name}: {str(e)}")

                    # Komunikacja GGWave między botami
                    if self.silence_counter >= 2 and len(self.bots) > 1:
                        current_bot = random.choice([b for b in self.bots if b.name != self.last_speaker])
                        context = self.last_input if self.last_input else "Cześć, co słychać?"
                        response = get_response(context, current_bot.system_prompt)
                        self.log_signal.emit(f"🤖 {current_bot.name}: {response}")

                        result_queue = Queue()
                        stop_event = threading.Event()
                        threads = []

                        for bot in [b for b in self.bots if b.name != current_bot.name]:
                            thread = threading.Thread(
                                target=receive_via_ggwave,
                                args=(result_queue, stop_event, bot.name, 12.0)
                            )
                            threads.append(thread)
                            thread.start()

                        time.sleep(1.0)
                        send_thread = threading.Thread(target=send_via_ggwave, args=(response,))
                        send_thread.start()

                        send_thread.join()
                        time.sleep(2.0)

                        stop_event.set()

                        for thread in threads:
                            thread.join()

                        received_messages = []
                        while not result_queue.empty():
                            bot_name, decoded = result_queue.get()
                            if decoded:
                                received_messages.append((bot_name, decoded))

                        if received_messages:
                            bot_name, decoded = random.choice(received_messages)
                            self.log_signal.emit(f"📡 {bot_name} (GGWave odebrane): {decoded}")
                            self.last_input = decoded
                            self.last_speaker = current_bot.name
                        else:
                            self.log_signal.emit("⚠️ Żaden bot nie odebrał wiadomości przez GGWave, używam TTS")
                            speak(f"{current_bot.name} mówi: {response}")
                            self.last_input = response
                            self.last_speaker = current_bot.name

                    elif len(self.bots) >= 1:
                        available_bots = [bot for bot in self.bots if bot.name != self.last_speaker]
                        if available_bots:
                            self.log_signal.emit("🤖 Boty rozmawiają między sobą (tryb normalny)...")
                            current_bot = random.choice(available_bots)
                            context = self.last_input if self.last_input else "Cześć, co słychać?"
                            response = get_response(context, current_bot.system_prompt)
                            self.log_signal.emit(f"🤖 {current_bot.name}: {response}")
                            try:
                                speak(f"{current_bot.name} mówi: {response}")
                                self.last_input = response
                                self.last_speaker = current_bot.name
                                time.sleep(0.5)
                            except Exception as e:
                                self.log_signal.emit(f"Błąd TTS dla {current_bot.name}: {str(e)}")

                if not self.bots and user_input and not user_input.lower().startswith(("dodaj bota", "do widzenia")):
                    response = "Nie ma żadnych botów. Dodaj bota komendą 'Dodaj bota <nazwa> jako <charakter>'."
                    self.log_signal.emit(f"🤖 System: {response}")
                    speak(response)

            except Exception as e:
                self.log_signal.emit(f"Błąd w głównej pętli: {str(e)}")
                continue

# Interfejs graficzny
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bot Conversation App")
        self.setGeometry(100, 100, 800, 600)

        # Utworzenie głównego widżetu i układu
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # Pole tekstowe na logi
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.layout.addWidget(self.log_display)

        # Przyciski
        self.start_button = QPushButton("Uruchom")
        self.stop_button = QPushButton("Zatrzymaj")
        self.layout.addWidget(self.start_button)
        self.layout.addWidget(self.stop_button)

        # Wątek główny
        self.main_thread = MainThread()
        self.main_thread.log_signal.connect(self.append_log)

        # Konfiguracja logowania do GUI
        self.log_queue = queue.Queue()
        self.log_handler = QueueHandler(self.log_queue)
        logging.getLogger().addHandler(self.log_handler)

        # Połączenie przycisków
        self.start_button.clicked.connect(self.start_main_thread)
        self.stop_button.clicked.connect(self.stop_main_thread)

        # Wątek do obsługi logów
        self.log_thread = threading.Thread(target=self.process_log_queue)
        self.log_thread.daemon = True
        self.log_thread.start()

    def append_log(self, message):
        self.log_display.append(message)

    def process_log_queue(self):
        while True:
            try:
                record = self.log_queue.get(timeout=1)
                if record and record.levelno >= logging.INFO:  # Tylko INFO i wyższe do GUI
                    self.main_thread.log_signal.emit(record.getMessage())
            except queue.Empty:
                continue

    def start_main_thread(self):
        if not self.main_thread.isRunning():
            self.main_thread.start()
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)

    def stop_main_thread(self):
        self.main_thread.running = False
        self.main_thread.wait()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def closeEvent(self, event):
        self.main_thread.running = False
        self.main_thread.wait()
        event.accept()

if __name__ == "__main__":
    sd.default.device = (13, 3)  # (input_id, output_id)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())