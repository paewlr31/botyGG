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
    let messageQueue = []; // Kolejka wiadomości
    let isProcessingQueue = false; // Flaga przetwarzania kolejki

    function connectWebSocket() {
        console.log("Łączenie WebSocket dla userId:", userId);
        ws = new WebSocket(`wss://${location.host}/ws/${userId}`);
        ws.onopen = () => {
            console.log("WebSocket połączony");
            queueMessage({ type: "message", content: "✅ Połączono z serwerem" });
            ws.send(JSON.stringify({ type: "get_status" }));
        };
        ws.onmessage = (event) => {
            console.log("Otrzymano wiadomość:", event.data);
            try {
                let data = JSON.parse(event.data);
                queueMessage(data); // Dodaj wiadomość do kolejki
            } catch (e) {
                console.error("Błąd parsowania wiadomości:", e);
            }
        };
        ws.onclose = () => {
            console.log("WebSocket zamknięty, ponowne łączenie...");
            queueMessage({ type: "message", content: "❌ Połączenie zamknięte. Próbuję ponownie..." });
            setTimeout(connectWebSocket, 2000);
        };
        ws.onerror = (error) => {
            console.error("Błąd WebSocket:", error);
            queueMessage({ type: "message", content: `⚠️ Błąd WebSocket: ${error}` });
        };
    }

    // Funkcja do dodawania wiadomości do kolejki
    function queueMessage(data) {
        messageQueue.push(data);
        processQueue();
    }

    // Funkcja do przetwarzania kolejki wiadomości
    async function processQueue() {
        if (isProcessingQueue || messageQueue.length === 0) return;
        isProcessingQueue = true;
        while (messageQueue.length > 0) {
            let data = messageQueue.shift();
            let msgBox = document.getElementById("messages");
            if (data.type === "message") {
                msgBox.innerHTML += `<div>${data.content}</div>`;
                msgBox.scrollTop = msgBox.scrollHeight;
                // Odczytuj TTS tylko dla wiadomości botów (zaczynających się od 🤖)
                if (data.content.startsWith("🤖")) {
                    try {
                        // Wyodrębnij treść po "🤖 <nazwa>: "
                        let botResponse = data.content.replace(/^🤖\s+[^:]+:\s*/, "");
                        let utterance = new SpeechSynthesisUtterance(botResponse);
                        utterance.lang = "pl-PL";
                        await new Promise(resolve => {
                            utterance.onend = resolve;
                            window.speechSynthesis.speak(utterance);
                        });
                    } catch (e) {
                        console.error("Błąd TTS:", e);
                        msgBox.innerHTML += `<div style="color: red;">⚠️ TTS nieobsługiwane w tej przeglądarce</div>`;
                    }
                } else {
                    console.log(`Pomijanie TTS dla wiadomości: ${data.content}`);
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
            await new Promise(resolve => setTimeout(resolve, 2000)); // 2-sekundowa przerwa
        }
        isProcessingQueue = false;
    }

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
                queueMessage({ type: "message", content: "⚠️ Połączenie z serwerem nieaktywne. Spróbuj ponownie." });
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
                queueMessage({ type: "message", content: `⚠️ Błąd rozpoznawania mowy: ${event.error}` });
            };
            recognition.start();
        } catch (e) {
            console.error("Błąd STT:", e);
            queueMessage({ type: "message", content: "⚠️ Rozpoznawanie mowy nieobsługiwane w tej przeglądarce" });
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
                queueMessage({ type: "message", content: "⚠️ Połączenie z serwerem nieaktywne. Spróbuj ponownie." });
            }
        } else {
            console.log("Brak nowej nazwy użytkownika");
            queueMessage({ type: "message", content: "⚠️ Podaj nową nazwę użytkownika!" });
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
                queueMessage({ type: "message", content: "⚠️ Połączenie z serwerem nieaktywne. Spróbuj ponownie." });
            }
        } else {
            console.log("Brak nazwy lub charakteru bota");
            queueMessage({ type: "message", content: "⚠️ Podaj nazwę i charakter bota!" });
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
                queueMessage({ type: "message", content: "⚠️ Połączenie z serwerem nieaktywne. Spróbuj ponownie." });
            }
        } else {
            console.log("Brak nazwy bota do usunięcia");
            queueMessage({ type: "message", content: "⚠️ Podaj nazwę bota do usunięcia!" });
        }
    }

    connectWebSocket();
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
        self.active_connections: Dict[str, WebSocket] = {}  # user_id -> WebSocket
        self.users: Dict[str, str] = {}  # user_id -> user_name
        self.bots: List[Bot] = []  # Lista botów
        self.last_message_was_bot: bool = False  # Flaga, czy ostatnia wiadomość była od bota
        self.timeout_seconds: int = 5  # Timeout w sekundach

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        user_name = self.users.get(user_id, f"Użytkownik_{user_id[:5]}")
        self.active_connections[user_id] = websocket
        self.users[user_id] = user_name
        logging.info(f"Użytkownik {user_name} (ID: {user_id}) dołączył")
        await self.broadcast({"type": "message", "content": f"👋 {user_name} dołączył ({len(self.active_connections)} osób)."})
        await self.update_user_list()

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            user_name = self.users.get(user_id, user_id)
            del self.active_connections[user_id]
            if user_id in self.users:
                del self.users[user_id]
            self.bots = [bot for bot in self.bots if bot.owner_id != user_id]
            logging.info(f"Użytkownik {user_name} (ID: {user_id}) odłączony, usunięto jego boty")
            return user_name
        return None

    async def broadcast(self, message: dict):
        logging.debug(f"Broadcast wiadomości: {message}")
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
            "bots": [{"name": bot.name, "owner": self.users.get(bot.owner_id, bot.owner_id), "owner_id": bot.owner_id} for bot in self.bots]
        })

    async def handle_message(self, user_id: str, message: str, user_name: str):
        logging.debug(f"Obsługa wiadomości od {user_name} (ID: {user_id}): {message}")
        self.last_message_was_bot = False
        await self.broadcast({"type": "message", "content": f"💬 {user_name}: {message}"})
        logging.debug(f"Liczba botów: {len(self.bots)}")
        any_bot_responded = False
        for bot in self.bots:
            logging.debug(f"Sprawdzanie bota {bot.name} (owner_id: {bot.owner_id}, user_id: {user_id})")
            response = await bot.respond(message)
            await self.broadcast({"type": "message", "content": f"🤖 {bot.name}: {response}"})
            any_bot_responded = True
            await asyncio.sleep(2)  # 2-sekundowa przerwa między odpowiedziami botów
        if any_bot_responded:
            self.last_message_was_bot = True
            await self.broadcast({"type": "timeout_info", "content": f"⏳ Oczekiwanie na wiadomość użytkownika ({self.timeout_seconds} sekund)"})
            await asyncio.sleep(2)  # Przerwa przed timeoutem
            await asyncio.sleep(self.timeout_seconds)
            if self.last_message_was_bot:  # Sprawdź, czy nie było nowej wiadomości
                self.last_message_was_bot = False
                await self.broadcast({"type": "timeout_info", "content": "⏳ Timeout minął, boty mogą odpowiadać."})
                await asyncio.sleep(2)  # Przerwa przed komunikatem o kolejce
                await self.broadcast({"type": "turn_info", "content": "🗣️ Twoja kolej na mówienie!"})
        else:
            await asyncio.sleep(2)  # Przerwa przed komunikatem o kolejce
            await self.broadcast({"type": "turn_info", "content": "🗣️ Twoja kolej na mówienie!"})

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
                    await manager.broadcast({"type": "message", "content": "⚠️ Podaj nową nazwę użytkownika!"})
                    continue
                manager.users[user_id] = new_name
                logging.info(f"Ustawiono nazwę użytkownika {user_id}: {new_name}")
                await manager.broadcast({"type": "message", "content": f"👤 {user_name} zmienił nazwę na {new_name}."})
                await manager.update_user_list()
            elif data["type"] == "add_bot":
                bot_name = data.get("name", "").strip()
                bot_character = data.get("character", "").strip()
                if not bot_name or not bot_character:
                    logging.warning("Brak nazwy lub charakteru bota")
                    await manager.broadcast({"type": "message", "content": "⚠️ Podaj nazwę i charakter bota!"})
                    continue
                if any(bot.name.lower() == bot_name.lower() and bot.owner_id == user_id for bot in manager.bots):
                    logging.warning(f"Bot {bot_name} już istnieje dla użytkownika {user_name}")
                    await manager.broadcast({"type": "message", "content": f"⚠️ Bot {bot_name} już istnieje!"})
                    continue
                bot_id = str(uuid.uuid4())
                manager.bots.append(Bot(bot_id, bot_name, bot_character, user_id))
                logging.info(f"Dodano bota {bot_name} (charakter: {bot_character}, ID: {bot_id}, właściciel: {user_name})")
                await manager.broadcast({"type": "message", "content": f" 🟢{user_name} dodał bota {bot_name} jako {bot_character}."})
                await manager.broadcast({"type": "turn_info", "content": "🗣️ Twoja kolej na mówienie!"})
                await manager.update_user_list()
            elif data["type"] == "remove_bot":
                bot_name = data.get("name", "").strip()
                if not bot_name:
                    logging.warning("Brak nazwy bota do usunięcia")
                    await manager.broadcast({"type": "message", "content": "⚠️ Podaj nazwę bota do usunięcia!"})
                    continue
                bots_before = len(manager.bots)
                manager.bots = [bot for bot in manager.bots if not (bot.name.lower() == bot_name.lower() and bot.owner_id == user_id)]
                if len(manager.bots) < bots_before:
                    logging.info(f"Usunięto bota {bot_name} przez {user_name}")
                    await manager.broadcast({"type": "message", "content": f"🧹 {user_name} usunął bota {bot_name}."})
                    await manager.broadcast({"type": "turn_info", "content": "🗣️ Twoja kolej na mówienie!"})
                    await manager.update_user_list()
                else:
                    logging.warning(f"Nie znaleziono bota {bot_name} dla użytkownika {user_name}")
                    await manager.broadcast({"type": "message", "content": f"⚠️ Nie znaleziono bota {bot_name}."})
            elif data["type"] == "get_status":
                await manager.update_user_list()
    except WebSocketDisconnect:
        user_name = manager.disconnect(user_id)
        if user_name:
            logging.info(f"Użytkownik {user_name} odłączony przez WebSocketDisconnect")
            await manager.broadcast({"type": "message", "content": f"🚪 {user_name} wyszedł ({len(manager.active_connections)} osób)."})
            await manager.update_user_list()
    except Exception as e:
        logging.error(f"Błąd w websocket_endpoint: {str(e)}")

if __name__ == "__main__":
    public_url = ngrok.connect(8000)
    logging.info(f"Publiczny link: {public_url}")
    uvicorn.run(app, host="0.0.0.0", port=8000)

    """
    TODO:
    dobra chce tutaj mieć pomiedzy akcjami dwie sekundy przerwy: 
    forntend ma wspolgrac: masz fronten i abckend: jajakolwiek akcja
      to 2 sekundy przerwy, ma sie wtedy nic nie dizac, mozesz
        przechowywac wypeoiwdxi boty gdzie sna zewnatrz czy cos, 
        jak jeden bot mowi to tylko on mowi i koniec jak ja to ja 
    (tyczy sir to za rowni mowienia z glsocinka jak i wypisywania 
    na ekranie), jedna rzecz na raz
    """