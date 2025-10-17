import sys
import logging
import socket
import threading
import json
from queue import Queue
from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QPushButton, QVBoxLayout, QWidget
from PyQt5.QtCore import QThread, pyqtSignal
from bot_manager import BotManager
from stt import listen
from tts import speak
import subprocess
import os
from dotenv import load_dotenv

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

# Wątek nasłuchiwania STT
class STTThread(QThread):
    text_received = pyqtSignal(str)

    def run(self):
        while True:
            text = listen()
            if text:
                self.text_received.emit(text)

# Wątek serwera socket
class ServerThread(QThread):
    message_received = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.clients = []
        self.port = self.find_free_port()

    def find_free_port(self):
        port = 12345
        while True:
            try:
                self.server_socket.bind(('localhost', port))
                logging.info(f"Zajęto port {port}")
                return port
            except OSError as e:
                logging.warning(f"Port {port} zajęty: {e}")
                port += 1
                if port > 65535:
                    raise Exception("Nie znaleziono wolnego portu")

    def run(self):
        self.server_socket.listen(5)
        logging.info(f"Serwer nasłuchuje na porcie {self.port}")
        while True:
            try:
                client_socket, _ = self.server_socket.accept()
                self.clients.append(client_socket)
                threading.Thread(target=self.handle_client, args=(client_socket,), daemon=True).start()
            except Exception as e:
                logging.error(f"Błąd serwera: {e}")
                break

    def handle_client(self, client_socket):
        while True:
            try:
                data = client_socket.recv(1024).decode()
                if data:
                    message = json.loads(data)
                    self.message_received.emit(message['bot_name'], message['message'])
            except Exception as e:
                logging.error(f"Błąd klienta: {e}")
                self.clients.remove(client_socket)
                client_socket.close()
                break

    def send_to_bots(self, message):
        for client in self.clients[:]:
            try:
                client.send(json.dumps(message).encode())
            except Exception as e:
                logging.error(f"Błąd wysyłania do klienta: {e}")
                self.clients.remove(client)
                client.close()

# Główne okno GUI
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("System Botów")
        self.setGeometry(100, 100, 600, 400)

        # GUI
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.start_button = QPushButton("🎤 Rozpocznij nasłuchiwanie")
        self.start_button.clicked.connect(self.start_listening)

        layout = QVBoxLayout()
        layout.addWidget(self.log_area)
        layout.addWidget(self.start_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Inicjalizacja
        load_dotenv("klucz.env")
        self.bot_manager = BotManager(os.getenv("OPENAI_API_KEY"))
        self.stt_thread = STTThread()
        self.stt_thread.text_received.connect(self.handle_input)
        try:
            self.server_thread = ServerThread()
            self.server_thread.message_received.connect(self.handle_bot_message)
            self.server_thread.start()
        except Exception as e:
            self.log(f"Błąd inicjalizacji serwera: {e}")
            sys.exit(1)

    def log(self, message):
        self.log_area.append(message)

    def start_listening(self):
        self.log("🎤 Nasłuchiwanie...")
        if not self.stt_thread.isRunning():
            self.stt_thread.start()

    def handle_input(self, user_input):
        self.log(f"🧍 Ty: {user_input}")
        if user_input.lower().startswith("dodaj bota"):
            try:
                parts = user_input.lower().split(" jako ")
                bot_name = parts[0].replace("dodaj bota ", "").strip()
                bot_character = parts[1].strip()
                self.bot_manager.add_bot(bot_name, f"Jesteś {bot_character}, który odpowiada w języku polskim.")
                self.log(f"Dodano bota {bot_name} jako {bot_character}")
                speak(f"Dodano bota {bot_name} jako {bot_character}")
                subprocess.Popen(["python", "bot.py", bot_name, bot_character, str(self.server_thread.port)])
                self.server_thread.send_to_bots({"type": "add_bot", "bot_name": bot_name, "bot_character": bot_character})
            except IndexError:
                self.log("Błąd: Podaj nazwę bota i charakter, np. 'Dodaj bota Rafał jako pisarz'.")
                speak("Błąd: Podaj nazwę bota i charakter.")
            return

        if user_input.lower().startswith("idź bot"):
            try:
                bot_name = user_input.lower().replace("idź bot ", "").strip()
                if self.bot_manager.remove_bot(bot_name):
                    self.log(f"Usunięto bota {bot_name}")
                    speak(f"Usunięto bota {bot_name}")
                    self.server_thread.send_to_bots({"type": "remove_bot", "bot_name": bot_name})
                else:
                    self.log(f"Nie znaleziono bota {bot_name}")
                    speak(f"Nie znaleziono bota {bot_name}")
            except:
                self.log("Błąd: Podaj poprawną nazwę bota.")
                speak("Błąd: Podaj poprawną nazwę bota.")
            return

        if user_input.lower() == "do widzenia":
            self.log("Do widzenia! Kończę rozmowę.")
            speak("Do widzenia! Kończę rozmowę.")
            self.server_thread.send_to_bots({"type": "exit"})
            sys.exit()

        self.bot_manager.process_user_input(user_input, self.log, self.server_thread.send_to_bots, speak)

    def handle_bot_message(self, bot_name, message):
        self.log(f"📡 {bot_name}: {message}")
        self.bot_manager.process_bot_message(bot_name, message, self.log, self.server_thread.send_to_bots, speak)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())