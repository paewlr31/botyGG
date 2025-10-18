from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pyngrok import ngrok
import uvicorn

app = FastAPI()

public_url = ngrok.connect(8000)
print(f"Publiczny link: {public_url}")

html = """
<!DOCTYPE html>
<html>
<head>
    <title>Grupowy czat</title>
    <style>
        body { font-family: Arial; background-color: #fafafa; }
        #messages { height: 300px; overflow-y: scroll; border: 1px solid #ccc; padding: 10px; }
        #inputArea { margin-top: 10px; }
        button { margin-left: 5px; }
    </style>
</head>
<body>
    <h2>Pokój czatu</h2>
    <div id="messages"></div>
    <div id="inputArea">
        <input id="messageText" placeholder="Napisz wiadomość..." />
        <button onclick="sendMessage()">Wyślij</button>
        <button onclick="addBot()">+ Bot</button>
        <button onclick="removeBot()">- Bot</button>
        <button onclick="closeRoom()">Zamknij pokój</button>
    </div>

    <script>
        let ws = new WebSocket(`ws://${location.host}/ws`);
        ws.onmessage = (event) => {
            let msgBox = document.getElementById("messages");
            msgBox.innerHTML += `<div>${event.data}</div>`;
            msgBox.scrollTop = msgBox.scrollHeight;
        };

        function sendMessage() {
            let input = document.getElementById("messageText");
            ws.send(input.value);
            input.value = "";
        }

        function addBot() { ws.send("/add_bot"); }
        function removeBot() { ws.send("/remove_bot"); }
        function closeRoom() { ws.send("/close_room"); }
    </script>
</body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(html)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.bots = 0

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        await self.broadcast(f"👋 Nowy użytkownik dołączył ({len(self.active_connections)} osób).")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for conn in self.active_connections:
            await conn.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "/add_bot":
                manager.bots += 1
                await manager.broadcast(f"🤖 Dodano bota. Liczba botów: {manager.bots}")
            elif data == "/remove_bot":
                if manager.bots > 0:
                    manager.bots -= 1
                await manager.broadcast(f"🧹 Usunięto bota. Liczba botów: {manager.bots}")
            elif data == "/close_room":
                await manager.broadcast("❌ Pokój został zamknięty.")
                for conn in manager.active_connections:
                    await conn.close()
                manager.active_connections.clear()
            else:
                await manager.broadcast(f"💬 {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(f"🚪 Użytkownik wyszedł ({len(manager.active_connections)} osób).")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
