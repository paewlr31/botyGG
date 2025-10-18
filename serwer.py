from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pyngrok import ngrok
import uvicorn
from typing import Dict, Optional
from openai import OpenAI
from dotenv import load_dotenv
import os
import uuid
import logging

# Konfiguracja logowania
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI()

# Inicjalizacja OpenAI (dla botów)
load_dotenv("klucz.env")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
        #userName, #botName, #botCharacter { width: 200px; }
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
            <button id="removeBotButton" onclick="removeBot()" disabled>Usuń bota</button>
        </div>
    </div>

    <script>
        let ws;
        let userId = localStorage.getItem("userId") || `Użytkownik_${Math.random().toString(36).substr(2, 5)}`;
        localStorage.setItem("userId", userId);
        let userName = "Użytkownik";
        let hasBot = false;

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
                    if (data.type === "message") {
                        let msgBox = document.getElementById("messages");
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
                        userList.innerHTML = "<strong>Użytkownik:</strong> " + data.user +
                                             "<br><strong>Bot:</strong> " + (data.bot ? data.bot : "Brak");
                        hasBot = !!data.bot;
                        updateButtons();
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
            addBotButton.disabled = hasBot;
            removeBotButton.disabled = !hasBot;
            console.log("Aktualizacja przycisków: addBot=", !hasBot, "removeBot=", hasBot);
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
            let message = { type: "remove_bot" };
            console.log("Wysyłanie remove_bot:", message);
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify(message));
            } else {
                console.log("WebSocket nie jest otwarty");
                alert("Połączenie z serwerem nieaktywne. Spróbuj ponownie.");
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
    def __init__(self, id: str, name: str, character: str):
        self.id = id
        self.name = name
        self.system_prompt = f"Jesteś {character}, który odpowiada zwięźle po polsku."

    async def respond(self, message: str) -> str:
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": message}
                ],
                max_tokens=30
            )
            logging.info(f"Bot {self.name} odpowiada: {response.choices[0].message.content.strip()}")
            return response.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"Błąd odpowiedzi bota {self.name}: {str(e)}")
            return f"{self.name}: Cześć, co słychać?"

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}  # user_id -> WebSocket
        self.user_name: str = "Użytkownik"  # Tylko jeden użytkownik
        self.bot: Optional[Bot] = None  # Tylko jeden bot

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logging.info(f"Użytkownik {self.user_name} (ID: {user_id}) dołączył")
        await self.broadcast({"type": "message", "content": f"👋 {self.user_name} dołączył."})
        await self.update_user_list()

        if self.bot:
            response = await self.bot.respond(f"Nowy użytkownik {self.user_name} dołączył.")
            await self.broadcast({"type": "message", "content": f"🤖 {self.bot.name}: {response}"})

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logging.info(f"Użytkownik {self.user_name} (ID: {user_id}) odłączony")
            return self.user_name
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
            "user": self.user_name,
            "bot": self.bot.name if self.bot else None
        })

    async def handle_message(self, message: str):
        await self.broadcast({"type": "message", "content": f"💬 {self.user_name}: {message}"})
        if self.bot:
            response = await self.bot.respond(message)
            await self.broadcast({"type": "message", "content": f"🤖 {self.bot.name}: {response}"})

manager = ConnectionManager()

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_json()
            logging.debug(f"Otrzymano dane WebSocket: {data}")
            if data["type"] == "message":
                logging.info(f"Wiadomość od {manager.user_name}: {data['content']}")
                await manager.handle_message(data["content"])
            elif data["type"] == "set_user_name":
                new_name = data.get("content", "").strip()
                if not new_name:
                    logging.warning("Brak nowej nazwy użytkownika")
                    await manager.broadcast({"type": "message", "content": "⚠️ Podaj nową nazwę użytkownika!"})
                    continue
                manager.user_name = new_name
                logging.info(f"Ustawiono nazwę użytkownika: {new_name}")
                await manager.broadcast({"type": "message", "content": f"👤 Nazwa zmieniona na {new_name}."})
                await manager.update_user_list()
            elif data["type"] == "add_bot":
                bot_name = data.get("name", "").strip()
                bot_character = data.get("character", "").strip()
                if not bot_name or not bot_character:
                    logging.warning("Brak nazwy lub charakteru bota")
                    await manager.broadcast({"type": "message", "content": "⚠️ Podaj nazwę i charakter bota!"})
                    continue
                if manager.bot:
                    logging.warning(f"Bot już istnieje: {manager.bot.name}")
                    await manager.broadcast({"type": "message", "content": f"⚠️ Bot już istnieje: {manager.bot.name}!"})
                    continue
                bot_id = str(uuid.uuid4())
                manager.bot = Bot(bot_id, bot_name, bot_character)
                logging.info(f"Dodano bota {bot_name} (charakter: {bot_character}, ID: {bot_id})")
                await manager.broadcast({"type": "message", "content": f"🤖 Dodano bota {bot_name} jako {bot_character}."})
                await manager.update_user_list()
            elif data["type"] == "remove_bot":
                if not manager.bot:
                    logging.warning("Brak bota do usunięcia")
                    await manager.broadcast({"type": "message", "content": "⚠️ Nie ma bota do usunięcia!"})
                    continue
                bot_name = manager.bot.name
                manager.bot = None
                logging.info(f"Usunięto bota {bot_name}")
                await manager.broadcast({"type": "message", "content": f"🧹 Usunięto bota {bot_name}."})
                await manager.update_user_list()
            elif data["type"] == "get_status":
                await manager.update_user_list()
    except WebSocketDisconnect:
        user_name = manager.disconnect(user_id)
        if user_name:
            logging.info(f"Użytkownik {user_name} odłączony przez WebSocketDisconnect")
            await manager.broadcast({"type": "message", "content": f"🚪 {user_name} wyszedł."})
            await manager.update_user_list()
    except Exception as e:
        logging.error(f"Błąd w websocket_endpoint: {str(e)}")

if __name__ == "__main__":
    public_url = ngrok.connect(8000)
    logging.info(f"Publiczny link: {public_url}")
    uvicorn.run(app, host="0.0.0.0", port=8000)