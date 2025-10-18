from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from pyngrok import ngrok
import uvicorn
from typing import Dict, List, Optional
from openai import OpenAI
from dotenv import load_dotenv
import os
import uuid
import logging
import asyncio

# Konfiguracja logowania
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI()

# Logowanie niepoprawnych żądań HTTP
@app.middleware("http")
async def log_invalid_requests(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logging.error(f"Niepoprawne żądanie HTTP: {request.url}, błąd: {str(e)}")
        raise

# Inicjalizacja OpenAI
load_dotenv("klucz.env")
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    logging.error("Brak klucza OPENAI_API_KEY w pliku klucz.env")
    raise ValueError("Brak klucza OpenAI API")
client = OpenAI(api_key=api_key)

# HTML dla frontendu
html = """
<!DOCTYPE html>
<html>
<head>
    <title>Grupowy czat</title>
    <style>
        body { font-family: Arial; background-color: #fafafa; padding: 20px; }
        #messages { height: 400px; overflow-y: scroll; border: 1px solid #ccc; padding: 10px; margin-bottom: 10px; }
        #userList { border: 1px solid #ccc; padding: 10px; margin-bottom: 10px; }
        #inputArea { display: flex; flex-direction: column; gap: 10px; }
        input, button { padding: 8px; font-size: 16px; }
        button { cursor: pointer; }
        button:disabled { cursor: not-allowed; opacity: 0.5; }
        #userName, #botName, #botCharacter, #removeBotName { width: 200px; }
        .timeout-info { color: blue; font-style: italic; }
        .turn-info { color: green; font-weight: bold; }
    </style>
</head>
<body>
    <h2>Pokój czatu</h2>
    <div>
        Twoja nazwa: <span id="currentUserName">Użytkownik</span>
        <input id="userName" placeholder="Nowa nazwa" />
        <button onclick="setUserName()">Ustaw nazwę</button>
    </div>
    <div>Lista użytkowników i botów:</div>
    <div id="userList"></div>
    <div id="messages"></div>
    <div id="inputArea">
        <input id="messageText" placeholder="Napisz lub powiedz wiadomość..." onkeypress="if(event.key === 'Enter') sendMessage()" />
        <div>
            <button onclick="sendMessage()">Wyślij</button>
            <button onclick="startSpeechRecognition()">🎤 Mów</button>
        </div>
        <div>
            <h4>Dodaj bota</h4>
            <input id="botName" placeholder="Nazwa bota" />
            <input id="botCharacter" placeholder="Charakter bota (np. pisarz)" />
            <button id="addBotButton" onclick="addBot()">+ Bot</button>
        </div>
        <div>
            <h4>Usuń bota</h4>
            <input id="removeBotName" placeholder="Nazwa bota do usunięcia" />
            <button id="removeBotButton" onclick="removeBot()">Usuń bota</button>
        </div>
    </div>

    <script>
        let ws;
        let userId = localStorage.getItem("userId") || `Użytkownik_${Math.random().toString(36).substr(2, 5)}`;
        localStorage.setItem("userId", userId);
        let userName = "Użytkownik";
        let userBots = [];

        function connectWebSocket() {
            console.log("Łączenie WebSocket dla userId:", userId);
            ws = new WebSocket(`wss://${location.host}/ws/${userId}`);
            ws.onopen = () => {
                console.log("WebSocket połączony");
                let msgBox = document.getElementById("messages");
                msgBox.innerHTML += `<div>✅ Połączono z serwerem</div>`;
                ws.send(JSON.stringify({ type: "get_status" }));
            };
            ws.onmessage = (event) => {
                console.log("Otrzymano wiadomość:", event.data);
                try {
                    let data = JSON.parse(event.data);
                    let msgBox = document.getElementById("messages");
                    if (data.type === "message") {
                        msgBox.innerHTML += `<div>${data.content}</div>`;
                        msgBox.scrollTop = msgBox.scrollHeight;
                        try {
                            let utterance = new SpeechSynthesisUtterance(data.content);
                            utterance.lang = "pl-PL";
                            window.speechSynthesis.speak(utterance);
                        } catch (e) {
                            console.error("Błąd TTS:", e);
                            msgBox.innerHTML += `<div style="color: red;">⚠️ TTS nieobsługiwane w tej przeglądarce</div>`;
                        }
                    } else if (data.type === "user_list") {
                        let userList = document.getElementById("userList");
                        let usersHtml = "<strong>Użytkownicy:</strong> " + (data.users.length ? data.users.join(", ") : "Brak");
                        let botsHtml = "<strong>Boty:</strong> " + (data.bots.length ? data.bots.map(b => `${b.name} (właściciel: ${b.owner})`).join(", ") : "Brak");
                        userList.innerHTML = usersHtml + "<br>" + botsHtml;
                        userBots = data.bots.filter(b => b.owner_id === userId).map(b => b.name);
                        updateButtons();
                    } else if (data.type === "timeout_info") {
                        console.log("Otrzymano timeout_info:", data.content);
                        msgBox.innerHTML += `<div class="timeout-info">${data.content}</div>`;
                        msgBox.scrollTop = msgBox.scrollHeight;
                    } else if (data.type === "turn_info") {
                        console.log("Otrzymano turn_info:", data.content);
                        msgBox.innerHTML += `<div class="turn-info">${data.content}</div>`;
                        msgBox.scrollTop = msgBox.scrollHeight;
                    }
                } catch (e) {
                    console.error("Błąd parsowania wiadomości:", e);
                }
            };
            ws.onclose = () => {
                console.log("WebSocket zamknięty, ponowne łączenie...");
                let msgBox = document.getElementById("messages");
                msgBox.innerHTML += `<div style="color: red;">❌ Połączenie zamknięte. Próbuję ponownie...</div>`;
                setTimeout(connectWebSocket, 2000);
            };
            ws.onerror = (error) => {
                console.error("Błąd WebSocket:", error);
                let msgBox = document.getElementById("messages");
                msgBox.innerHTML += `<div style="color: red;">⚠️ Błąd WebSocket: ${error}</div>`;
            };
        }
        connectWebSocket();

        function updateButtons() {
            let addBotButton = document.getElementById("addBotButton");
            let removeBotButton = document.getElementById("removeBotButton");
            removeBotButton.disabled = userBots.length === 0;
            console.log("Aktualizacja przycisków: addBot=aktywny, removeBot=", userBots.length > 0);
        }

        function sendMessage() {
            let input = document.getElementById("messageText");
            if (input.value.trim()) {
                let message = { type: "message", content: input.value, user: userName };
                console.log("Wysyłanie wiadomości:", message);
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify(message));
                    input.value = "";
                } else {
                    console.log("WebSocket nie jest otwarty");
                    alert("Połączenie z serwerem nieaktywne. Spróbuj ponownie.");
                }
            }
        }

        function startSpeechRecognition() {
            try {
                let recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
                recognition.lang = "pl-PL";
                recognition.onresult = (event) => {
                    let transcript = event.results[0][0].transcript;
                    console.log("Rozpoznano mowę:", transcript);
                    document.getElementById("messageText").value = transcript;
                    sendMessage();
                };
                recognition.onerror = (event) => {
                    console.error("Błąd STT:", event.error);
                    let msgBox = document.getElementById("messages");
                    msgBox.innerHTML += `<div style="color: red;">⚠️ Błąd rozpoznawania mowy: ${event.error}</div>`;
                };
                recognition.start();
            } catch (e) {
                console.error("Błąd STT:", e);
                let msgBox = document.getElementById("messages");
                msgBox.innerHTML += `<div style="color: red;">⚠️ Rozpoznawanie mowy nieobsługiwane w tej przeglądarce</div>`;
            }
        }

        function setUserName() {
            let newName = document.getElementById("userName").value.trim();
            if (newName) {
                userName = newName;
                document.getElementById("currentUserName").innerHTML = userName;
                document.getElementById("userName").value = "";
                let message = { type: "set_user_name", content: userName };
                console.log("Wysyłanie set_user_name:", message);
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify(message));
                } else {
                    console.log("WebSocket nie jest otwarty");
                    alert("Połączenie z serwerem nieaktywne. Spróbuj ponownie.");
                }
            } else {
                console.log("Brak nowej nazwy użytkownika");
                alert("Podaj nową nazwę użytkownika!");
            }
        }

        function addBot() {
            let botName = document.getElementById("botName").value.trim();
            let botCharacter = document.getElementById("botCharacter").value.trim();
            if (botName && botCharacter) {
                let message = { type: "add_bot", name: botName, character: botCharacter };
                console.log("Wysyłanie add_bot:", message);
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify(message));
                    document.getElementById("botName").value = "";
                    document.getElementById("botCharacter").value = "";
                } else {
                    console.log("WebSocket nie jest otwarty");
                    alert("Połączenie z serwerem nieaktywne. Spróbuj ponownie.");
                }
            } else {
                console.log("Brak nazwy lub charakteru bota");
                alert("Podaj nazwę i charakter bota!");
            }
        }

        function removeBot() {
            let botName = document.getElementById("removeBotName").value.trim();
            if (botName) {
                let message = { type: "remove_bot", name: botName };
                console.log("Wysyłanie remove_bot:", message);
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify(message));
                    document.getElementById("removeBotName").value = "";
                } else {
                    console.log("WebSocket nie jest otwarty");
                    alert("Połączenie z serwerem nieaktywne. Spróbuj ponownie.");
                }
            } else {
                console.log("Brak nazwy bota do usunięcia");
                alert("Podaj nazwę bota do usunięcia!");
            }
        }
    </script>
</body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(html)

class Bot:
    def __init__(self, id: str, name: str, character: str, owner_id: str):
        self.id = id
        self.name = name
        self.system_prompt = f"Jesteś {character}, który odpowiada zwięźle po polsku."
        self.owner_id = owner_id

    async def respond(self, message: str) -> str:
        logging.debug(f"Bot {self.name} próbuje odpowiedzieć na: {message}")
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": message}
                ],
                max_tokens=30
            )
            answer = response.choices[0].message.content.strip()
            logging.info(f"Bot {self.name} odpowiada: {answer}")
            return answer
        except Exception as e:
            logging.error(f"Błąd odpowiedzi bota {self.name}: {str(e)}")
            return f"{self.name}: Cześć, co słychać?"

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.users: Dict[str, str] = {}
        self.bots: List[Bot] = []
        self.last_message: Optional[str] = None
        self.last_speaker: Optional[str] = None
        self.user_timeout_seconds: int = 5
        self.bot_pause_seconds: int = 2
        self.user_silence_count: int = 0
        self.conversation_active: bool = False

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        user_name = self.users.get(user_id, f"Użytkownik_{user_id[:5]}")
        self.active_connections[user_id] = websocket
        self.users[user_id] = user_name
        logging.info(f"Użytkownik {user_name} dołączył")
        await self.broadcast({"type": "message", "content": f"👋 {user_name} dołączył ({len(self.active_connections)} osób)."})
        await self.update_user_list()

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            user_name = self.users.get(user_id, f"Użytkownik_{user_id[:5]}")
            del self.active_connections[user_id]
            del self.users[user_id]
            # usuń boty tego użytkownika
            self.bots = [bot for bot in self.bots if bot.owner_id != user_id]
            logging.info(f"Użytkownik {user_name} wyszedł — jego boty usunięte.")
            return user_name
        return None

    async def broadcast(self, message: dict):
        for user_id, conn in list(self.active_connections.items()):
            try:
                await conn.send_json(message)
            except Exception as e:
                logging.error(f"Błąd broadcastu do {user_id}: {str(e)}")
                self.disconnect(user_id)

    async def update_user_list(self):
        await self.broadcast({
            "type": "user_list",
            "users": list(self.users.values()),
            "bots": [{"name": b.name, "owner": self.users.get(b.owner_id, b.owner_id)} for b in self.bots]
        })

    async def handle_message(self, user_id: str, message: str, user_name: str):
        """Obsługa wypowiedzi użytkownika — resetuje licznik ciszy i uruchamia kolejkę botów."""
        self.last_message = message
        self.last_speaker = user_name
        self.user_silence_count = 0
        self.conversation_active = True

        await self.broadcast({"type": "message", "content": f"{user_name}: {message}"})
        await asyncio.sleep(self.bot_pause_seconds)  # chwila ciszy po wypowiedzi użytkownika

        await self.start_bot_turn()

    async def start_bot_turn(self):
        """Boty mówią po kolei, jeden po drugim, z przerwami."""
        if not self.bots:
            await self.broadcast({"type": "turn_info", "content": "Brak botów w rozmowie."})
            return

        self.last_speaker = "bot"
        for bot in self.bots:
            response = await bot.respond(self.last_message)
            await self.broadcast({"type": "message", "content": f"{bot.name}: {response}"})
            self.last_message = response
            await asyncio.sleep(self.bot_pause_seconds)  # przerwa po wypowiedzi bota

        await self.wait_for_user_turn()

    async def wait_for_user_turn(self):
        """Oczekiwanie na reakcję człowieka po turze botów."""
        self.last_speaker = "bot"
        await self.broadcast({
            "type": "timeout_info",
            "content": f"Czekam na odpowiedź użytkownika (limit: {self.user_timeout_seconds} sek.)"
        })

        try:
            await asyncio.wait_for(self.wait_for_user_message(), timeout=self.user_timeout_seconds)
        except asyncio.TimeoutError:
            self.user_silence_count += 1
            logging.info(f"Brak odpowiedzi użytkownika. Cisza #{self.user_silence_count}")
            await self.broadcast({
                "type": "timeout_info",
                "content": f"Użytkownik milczy... ({self.user_silence_count})"
            })
            # po ciszy — kontynuuj rozmowę botów
            await self.start_bot_turn()

    async def wait_for_user_message(self):
        """Pomocnicze — wstrzymuje się, dopóki nie pojawi się nowa wiadomość użytkownika."""
        while self.last_speaker == "bot":
            await asyncio.sleep(0.5)
manager = ConnectionManager()

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_json()
            logging.debug(f"Otrzymano dane WebSocket: {data}")
            user_name = manager.users.get(user_id, user_id)
            if data["type"] == "message":
                logging.info(f"Wiadomość od {user_name}: {data['content']}")
                await manager.handle_message(user_id, data["content"], user_name)
            elif data["type"] == "set_user_name":
                new_name = data.get("content", "").strip()
                if not new_name:
                    logging.warning("Brak nowej nazwy użytkownika")
                    await manager.broadcast({"type": "message", "content": " Podaj nową nazwę użytkownika!"})
                    continue
                manager.users[user_id] = new_name
                logging.info(f"Ustawiono nazwę użytkownika {user_id}: {new_name}")
                await manager.broadcast({"type": "message", "content": f" {user_name} zmienił nazwę na {new_name}."})
                await manager.update_user_list()
            elif data["type"] == "add_bot":
                bot_name = data.get("name", "").strip()
                bot_character = data.get("character", "").strip()
                if not bot_name or not bot_character:
                    logging.warning("Brak nazwy lub charakteru bota")
                    await manager.broadcast({"type": "message", "content": " Podaj nazwę i charakter bota!"})
                    continue
                if any(bot.name.lower() == bot_name.lower() and bot.owner_id == user_id for bot in manager.bots):
                    logging.warning(f"Bot {bot_name} już istnieje dla użytkownika {user_name}")
                    await manager.broadcast({"type": "message", "content": f" Bot {bot_name} już istnieje!"})
                    continue
                bot_id = str(uuid.uuid4())
                manager.bots.append(Bot(bot_id, bot_name, bot_character, user_id))
                logging.info(f"Dodano bota {bot_name} (charakter: {bot_character}, ID: {bot_id}, właściciel: {user_name})")
                await manager.broadcast({"type": "message", "content": f" {user_name} dodał bota {bot_name} jako {bot_character}."})
                await manager.broadcast({"type": "turn_info", "content": " Twoja kolej na mówienie!"})
                await manager.update_user_list()
            elif data["type"] == "remove_bot":
                bot_name = data.get("name", "").strip()
                if not bot_name:
                    logging.warning("Brak nazwy bota do usunięcia")
                    await manager.broadcast({"type": "message", "content": " Podaj nazwę bota do usunięcia!"})
                    continue
                bots_before = len(manager.bots)
                manager.bots = [bot for bot in manager.bots if not (bot.name.lower() == bot_name.lower() and bot.owner_id == user_id)]
                if len(manager.bots) < bots_before:
                    logging.info(f"Usunięto bota {bot_name} przez {user_name}")
                    await manager.broadcast({"type": "message", "content": f" {user_name} usunął bota {bot_name}."})
                    await manager.broadcast({"type": "turn_info", "content": " Twoja kolej na mówienie!"})
                    await manager.update_user_list()
                else:
                    logging.warning(f"Nie znaleziono bota {bot_name} dla użytkownika {user_name}")
                    await manager.broadcast({"type": "message", "content": f" Nie znaleziono bota {bot_name}."})
            elif data["type"] == "get_status":
                await manager.update_user_list()
    except WebSocketDisconnect:
        user_name = manager.disconnect(user_id)
        if user_name:
            logging.info(f"Użytkownik {user_name} odłączony przez WebSocketDisconnect")
            await manager.broadcast({"type": "message", "content": f" {user_name} wyszedł ({len(manager.active_connections)} osób)."})
            await manager.update_user_list()
    except Exception as e:
        logging.error(f"Błąd w websocket_endpoint: {str(e)}")

if __name__ == "__main__":
    public_url = ngrok.connect(8000)
    logging.info(f"Publiczny link: {public_url}")
    uvicorn.run(app, host="0.0.0.0", port=8000)

"""
TODO:
   Do kazdej akcji chce dodac dwie skeundy ciszy: 
   jedna akcja+ dwie skeundy ciszy i do puki te 
   dwie skeundy si eni skoncza o zadan nowa si 
   enie zaczyna
"""
