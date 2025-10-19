import sys
import argparse
from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QPushButton, QVBoxLayout, QWidget
from PyQt5.QtCore import QThread, pyqtSignal
import logging
from logging.handlers import QueueHandler
import queue
import threading
import time
import random
import uuid
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
import requests
import json

# Konfiguracja logowania
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger()

# Inicjalizacja OpenAI
load_dotenv("klucz.env")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Inicjalizacja GGWave
try:
    ggwave_instance = ggwave.init()
    logger.info("✅ GGWave zainicjalizowany poprawnie.")
except Exception as e:
    logger.error(f"❌ Błąd inicjalizacji GGWave: {e}")
    ggwave_instance = None

# Action types
ACTION_HUMAN_SPEAK = "human_speak"
ACTION_BOT_SPEAK = "bot_speak"
ACTION_GGWAVE_SEND = "ggwave_send"
ACTION_GGWAVE_RECEIVE = "ggwave_receive"

# Funkcje GGWave
def send_via_ggwave(message: str, instance_id: str, protocolId: int = 1, volume: int = 80):
    try:
        if not message:
            logger.warning("Pusta wiadomość, pomijam wysyłanie.")
            return None
        message_with_id = f"{instance_id}:{message}"
        if len(message_with_id.encode('utf-8')) > 100:
            logger.warning(f"Wiadomość zbyt długa, obcinam do 100 znaków.")
            message_with_id = message_with_id[:100]
        waveform = ggwave.encode(message_with_id, protocolId=protocolId, volume=volume)
        audio = np.frombuffer(waveform, dtype=np.float32)
        logger.debug(f"Rozmiar waveform: {len(waveform)} bajtów")
        sd.play(audio, samplerate=48000)
        sd.wait()
        logger.info(f"📡 [GGWave] Wysłano: {message_with_id}")
        time.sleep(0.5)
        return waveform
    except Exception as e:
        logger.error(f"Błąd przy wysyłaniu GGWave: {e}")
        return None

def receive_via_ggwave(queue: Queue, stop_event: threading.Event, bot_name: str, instance_id: str, silence_timeout: float = 15.0):
    if ggwave_instance is None:
        logger.error("❌ Brak instancji GGWave — nie można odbierać.")
        queue.put((bot_name, None))
        return
    decoded = None
    last_data_time = time.time()
    start_time = time.time()
    def callback(indata, frames, time_info, status):
        nonlocal decoded, last_data_time
        if status:
            logger.debug(f"[{bot_name}] Status: {status}")
        if stop_event.is_set():
            return
        try:
            audio_level = np.max(np.abs(indata))
            if audio_level > 0.01:
                last_data_time = time.time()
                logger.debug(f"[{bot_name}] Poziom audio: {audio_level:.6f}")
            data_bytes = indata.tobytes()
            res = ggwave.decode(ggwave_instance, data_bytes)
            if res:
                try:
                    decoded_text = res.decode("utf-8")
                    if decoded_text.startswith(f"{instance_id}:"):
                        logger.debug(f"[{bot_name}] Ignoruję własną wiadomość: {decoded_text}")
                        return
                    logger.info(f"🎯 [{bot_name}] ZDEKODOWANO: '{decoded_text}'")
                    decoded = decoded_text
                    queue.put((bot_name, decoded))
                    return
                except Exception as e:
                    logger.debug(f"[{bot_name}] Błąd dekodowania UTF-8: {e}")
                    decoded = str(res)
                    queue.put((bot_name, decoded))
                    return
        except Exception as e:
            logger.debug(f"[{bot_name}] Błąd w callback: {e}")
    try:
        logger.info(f"🎧 {bot_name} nasłuchuje GGWave (timeout: {silence_timeout}s)...")
        with sd.InputStream(
            callback=callback,
            channels=1,
            samplerate=48000,
            dtype='float32',
            blocksize=2048,
            latency='low',
            device=sd.default.device[0]
        ) as stream:
            while not stop_event.is_set():
                if time.time() - last_data_time > silence_timeout:
                    logger.info(f"⏰ [{bot_name}] Timeout ciszy ({silence_timeout}s)")
                    break
                if time.time() - start_time > 30:
                    logger.info(f"⏰ [{bot_name}] Maksymalny czas nasłuchiwania")
                    break
                time.sleep(0.1)
    except Exception as e:
        logger.error(f"❌ Błąd InputStream dla {bot_name}: {e}")
        queue.put((bot_name, None))
        return
    if decoded:
        logger.info(f"✅ {bot_name} ODEBRAŁ: '{decoded}'")
        queue.put((bot_name, decoded))
    else:
        logger.info(f"❌ {bot_name} nic nie odebrał")
        queue.put((bot_name, None))

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
        logger.error(f"Błąd API Open AI: {str(e)}")
        return f"Błąd API Open AI: {str(e)}"

# Funkcja STT
def listen():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        logger.info("🎤 Mów teraz... (5 sekund na rozpoczęcie)")
        try:
            audio = r.listen(source, timeout=5)
            text = r.recognize_google(audio, language="pl-PL")
            return text
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            logger.error(f"Błąd połączenia ze STT: {str(e)}")
            return ""

# Funkcja TTS
def speak(text):
    if not text or not text.strip():
        return
    try:
        logger.info(f"Mówię: {text}")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tts = gTTS(text=text, lang="pl")
            tts.save(fp.name)
            temp_path = fp.name
        playsound(temp_path)
        os.remove(temp_path)
    except Exception as e:
        logger.error(f"Błąd w TTS: {e}")

# Klasa Bot
class Bot:
    def __init__(self, name, system_prompt):
        self.name = name
        self.system_prompt = system_prompt

# Wątek główny aplikacji
class MainThread(QThread):
    log_signal = pyqtSignal(str)
    
    def __init__(self, bot_name, bot_type, server_url, instance_id):
        super().__init__()
        self.running = False
        self.bot = Bot(bot_name, f"Jesteś {bot_type}, który odpowiada w języku polskim.")
        self.server_url = server_url
        self.instance_id = instance_id
        self.last_input = None
        self.silence_counter = 0
        self.ggwave_mode = False
        try:
            response = requests.post(
                f"{self.server_url}/register",
                json={"instance_id": self.instance_id, "bot_name": bot_name}
            ).json()
            logger.info(f"📝 Rejestracja instancji: {response}")
        except Exception as e:
            logger.error(f"Błąd rejestracji: {e}")

    def run(self):
        self.running = True
        self.log_signal.emit(f"🤖 Witaj! Jestem {self.bot.name}. Rozpoczynamy rozmowę. Powiedz 'do widzenia', aby zakończyć.")
        
        while self.running:
            try:
                # Sprawdź status akcji
                status_response = requests.post(
                    f"{self.server_url}/check_action_status",
                    json={"instance_id": self.instance_id}
                ).json()
                status = status_response.get("status", "idle")
                self.ggwave_mode = status_response.get("ggwave_mode", False)

                if status == "queued":
                    if self.ggwave_mode:
                        self.log_signal.emit(f"📡 {self.bot.name} czeka na swoją kolej w trybie GGWave.")
                        # Odbieraj w trybie GGWave
                        action_response = requests.post(
                            f"{self.server_url}/request_action",
                            json={"instance_id": self.instance_id, "action_type": ACTION_GGWAVE_RECEIVE}
                        ).json()
                        if action_response["status"] == "approved":
                            result_queue = Queue()
                            stop_event = threading.Event()
                            receive_thread = threading.Thread(
                                target=receive_via_ggwave,
                                args=(result_queue, stop_event, self.bot.name, self.instance_id, 15.0)
                            )
                            receive_thread.start()
                            time.sleep(15.0)
                            stop_event.set()
                            receive_thread.join()
                            while not result_queue.empty():
                                _, decoded = result_queue.get()
                                if decoded:
                                    try:
                                        sender_id, message = decoded.split(":", 1)
                                        self.log_signal.emit(f"📡 {self.bot.name} (GGWave odebrano od {sender_id}): {message}")
                                        self.last_input = message
                                    except ValueError:
                                        logger.warning(f"Nieprawidłowy format wiadomości GGWave: {decoded}")
                            requests.post(
                                f"{self.server_url}/complete_action",
                                json={"instance_id": self.instance_id}
                            )
                    else:
                        self.log_signal.emit(f"⏳ {self.bot.name} czeka w kolejce na swoją kolej.")
                    time.sleep(1)
                    continue
                elif status == "active":
                    if self.ggwave_mode and status_response["action"] == ACTION_GGWAVE_SEND:
                        # Bot jest nadawcą w trybie GGWave
                        context = self.last_input if self.last_input else "Cześć, co słychać?"
                        bot_response = get_response(context, self.bot.system_prompt + " Odpowiadaj w kontekście poprzedniej wiadomości.")
                        self.log_signal.emit(f"🤖 {self.bot.name}: {bot_response}")
                        send_via_ggwave(bot_response, self.instance_id)
                        requests.post(
                            f"{self.server_url}/complete_action",
                            json={"instance_id": self.instance_id}
                        )
                        role_response = requests.post(
                            f"{self.server_url}/switch_roles",
                            json={"instance_id": self.instance_id}
                        ).json()
                        self.ggwave_mode = role_response.get("ggwave_mode", False)
                        self.silence_counter = 0  # Reset po GGWave
                    elif status_response["action"] == ACTION_HUMAN_SPEAK:
                        # Bot wykonuje human_speak
                        bot_response = get_response(self.last_input, self.bot.system_prompt)
                        self.log_signal.emit(f"🤖 {self.bot.name}: {bot_response}")
                        speak(f"{self.bot.name} mówi: {bot_response}")
                        self.last_input = bot_response
                        requests.post(
                            f"{self.server_url}/complete_action",
                            json={"instance_id": self.instance_id}
                        )
                    time.sleep(1)
                    continue

                # Status idle - nasłuchuj człowieka
                role_response = requests.post(
                    f"{self.server_url}/get_role",
                    json={"instance_id": self.instance_id}
                ).json()
                role = role_response.get("role", "receiver")
                self.ggwave_mode = role_response.get("ggwave_mode", False)

                if not self.ggwave_mode:
                    user_input = listen()
                    if user_input:
                        self.silence_counter = 0
                        self.log_signal.emit(f"🧍 Ty: {user_input}")
                        self.last_input = user_input
                        if "do widzenia" in user_input.lower():
                            response = "Do widzenia! Kończę rozmowę."
                            self.log_signal.emit(f"🤖 {self.bot.name}: {response}")
                            speak(response)
                            self.running = False
                            break
                        
                        action_response = requests.post(
                            f"{self.server_url}/request_action",
                            json={"instance_id": self.instance_id, "action_type": ACTION_HUMAN_SPEAK}
                        ).json()
                        
                        if action_response["status"] == "approved":
                            self.last_input = user_input
                        else:
                            self.log_signal.emit(f"⏳ {self.bot.name} czeka na swoją kolej.")
                            continue
                    else:
                        self.silence_counter += 1
                        self.log_signal.emit(f"🔇 {self.bot.name}: Brak mowy, licznik ciszy: {self.silence_counter}")
                        if self.silence_counter >= 4:
                            # Pierwszy bot zgłasza tryb GGWave
                            requests.post(
                                f"{self.server_url}/trigger_ggwave_mode",
                                json={"instance_id": self.instance_id}
                            )
                            self.ggwave_mode = True
                            self.silence_counter = 0
                            self.log_signal.emit(f"📡 {self.bot.name} zainicjował tryb GGWave.")
                time.sleep(1)

            except Exception as e:
                self.log_signal.emit(f"Błąd w głównej pętli: {str(e)}")
                time.sleep(1)

# Interfejs graficzny
class MainWindow(QMainWindow):
    def __init__(self, bot_name, bot_type, server_url, instance_id):
        super().__init__()
        self.setWindowTitle(f"Bot {bot_name} ({bot_type})")
        self.setGeometry(100, 100, 800, 600)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.layout.addWidget(self.log_display)
        self.start_button = QPushButton("Uruchom")
        self.stop_button = QPushButton("Zatrzymaj")
        self.layout.addWidget(self.start_button)
        self.layout.addWidget(self.stop_button)
        self.main_thread = MainThread(bot_name, bot_type, server_url, instance_id)
        self.main_thread.log_signal.connect(self.append_log)
        self.log_queue = queue.Queue()
        self.log_handler = QueueHandler(self.log_queue)
        logger.addHandler(self.log_handler)
        self.start_button.clicked.connect(self.start_main_thread)
        self.stop_button.clicked.connect(self.stop_main_thread)
        self.log_thread = threading.Thread(target=self.process_log_queue)
        self.log_thread.daemon = True
        self.log_thread.start()

    def append_log(self, message):
        self.log_display.append(message)

    def process_log_queue(self):
        while True:
            try:
                record = self.log_queue.get(timeout=1)
                if record and record.levelno >= logging.INFO:
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
    # Parsowanie argumentów linii poleceń
    parser = argparse.ArgumentParser(description="Bot Conversation App")
    parser.add_argument("--imieBota", required=True, help="Imię bota")
    parser.add_argument("--typBota", required=True, help="Typ/charakter bota")
    parser.add_argument("--serverUrl", required=True, help="URL serwera Flask/ngrok")
    args = parser.parse_args()
    bot_name = args.imieBota
    bot_type = args.typBota
    server_url = args.serverUrl
    # Generowanie unikalnego identyfikatora instancji
    instance_id = str(uuid.uuid4())
    # Konfiguracja urządzeń audio
    sd.default.device = (13, 3)  # Dostosuj do swoich urządzeń (input_id, output_id)
    # Uruchomienie aplikacji
    app = QApplication(sys.argv)
    window = MainWindow(bot_name, bot_type, server_url, instance_id)
    window.show()
    sys.exit(app.exec_())