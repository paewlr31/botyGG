import sys
import socket
import threading
import json
from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QVBoxLayout, QWidget
from PyQt5.QtCore import QThread, pyqtSignal
from gglink import send_via_ggwave, receive_via_ggwave
from queue import Queue
from tts import speak
import logging

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

# Wątek nasłuchiwania GGWave
class GGWaveThread(QThread):
    message_received = pyqtSignal(str)

    def __init__(self, bot_name):
        super().__init__()
        self.bot_name = bot_name
        self.queue = Queue()
        self.stop_event = threading.Event()

    def run(self):
        receive_via_ggwave(self.queue, self.stop_event, self.bot_name, silence_timeout=12.0)
        bot_name, message = self.queue.get()
        if message:
            self.message_received.emit(message)

# Wątek klienta socket
class ClientThread(QThread):
    message_received = pyqtSignal(dict)

    def __init__(self, port):
        super().__init__()
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.connect(('localhost', int(port)))

    def run(self):
        while True:
            try:
                data = self.client_socket.recv(1024).decode()
                if data:
                    self.message_received.emit(json.loads(data))
            except Exception as e:
                logging.error(f"Błąd klienta: {e}")
                break

    def send(self, message):
        try:
            self.client_socket.send(json.dumps(message).encode())
        except Exception as e:
            logging.error(f"Błąd wysyłania: {e}")

# Okno bota
class BotWindow(QMainWindow):
    def __init__(self, bot_name, bot_character, port):
        super().__init__()
        self.bot_name = bot_name
        self.bot_character = bot_character
        self.setWindowTitle(f"Bot {bot_name} ({bot_character})")
        self.setGeometry(100, 100, 600, 400)

        # GUI
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)

        layout = QVBoxLayout()
        layout.addWidget(self.log_area)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Inicjalizacja
        self.client_thread = ClientThread(port)
        self.client_thread.message_received.connect(self.handle_server_message)
        self.client_thread.start()
        self.ggwave_thread = None

    def log(self, message):
        self.log_area.append(message)

    def handle_server_message(self, message):
        if message['type'] == 'response' and message['bot_name'] != self.bot_name:
            self.log(f"Odebrano od {message['bot_name']}: {message['message']}")
            self.start_ggwave_listening()
        elif message['type'] == 'response' and message['bot_name'] == self.bot_name:
            self.log(f"Wysyłam: {message['message']}")
            send_via_ggwave(message['message'])
        elif message['type'] == 'exit':
            sys.exit()

    def start_ggwave_listening(self):
        if self.ggwave_thread and self.ggwave_thread.isRunning():
            return
        self.ggwave_thread = GGWaveThread(self.bot_name)
        self.ggwave_thread.message_received.connect(self.handle_ggwave_message)
        self.ggwave_thread.start()

    def handle_ggwave_message(self, message):
        self.log(f"Odebrano GGWave: {message}")
        self.client_thread.send({"bot_name": self.bot_name, "message": message})

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Użycie: python bot.py <nazwa_bota> <charakter> <port>")
        sys.exit(1)
    bot_name = sys.argv[1]
    bot_character = sys.argv[2]
    port = sys.argv[3]
    app = QApplication(sys.argv)
    window = BotWindow(bot_name, bot_character, port)
    window.show()
    sys.exit(app.exec_())