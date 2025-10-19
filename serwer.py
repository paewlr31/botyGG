from flask import Flask, request, jsonify
from pyngrok import ngrok
import logging
import time

# Konfiguracja logowania
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger()

app = Flask(__name__)
server_state = {
    "instances": {},  # {instance_id: {"role": "sender"/"receiver", "bot_name": str, "last_active": float}}
    "current_sender": None
}

@app.route("/register", methods=["POST"])
def register_instance():
    data = request.json
    instance_id = data["instance_id"]
    bot_name = data["bot_name"]
    server_state["instances"][instance_id] = {
        "role": "receiver",
        "bot_name": bot_name,
        "last_active": time.time()
    }
    if not server_state["current_sender"]:
        server_state["current_sender"] = instance_id
        server_state["instances"][instance_id]["role"] = "sender"
    logger.info(f"📝 Zarejestrowano instancję: {instance_id} ({bot_name})")
    return jsonify({"status": "registered", "role": server_state["instances"][instance_id]["role"]})

@app.route("/get_role", methods=["POST"])
def get_role():
    data = request.json
    instance_id = data["instance_id"]
    if instance_id in server_state["instances"]:
        server_state["instances"][instance_id]["last_active"] = time.time()
        # Czyszczenie nieaktywnych instancji
        for iid in list(server_state["instances"].keys()):
            if time.time() - server_state["instances"][iid]["last_active"] > 60:
                del server_state["instances"][iid]
                if server_state["current_sender"] == iid:
                    server_state["current_sender"] = None
                    # Wybierz nowego nadawcę, jeśli możliwe
                    active_instances = list(server_state["instances"].keys())
                    if active_instances:
                        server_state["current_sender"] = active_instances[0]
                        server_state["instances"][active_instances[0]]["role"] = "sender"
        return jsonify({"role": server_state["instances"][instance_id]["role"]})
    return jsonify({"error": "instance not found"}), 404

@app.route("/switch_roles", methods=["POST"])
def switch_roles():
    data = request.json
    instance_id = data["instance_id"]
    if instance_id == server_state["current_sender"]:
        active_instances = [
            iid for iid, info in server_state["instances"].items()
            if info["last_active"] > time.time() - 30 and iid != instance_id
        ]
        if active_instances:
            server_state["current_sender"] = active_instances[0]
            server_state["instances"][server_state["current_sender"]]["role"] = "sender"
            server_state["instances"][instance_id]["role"] = "receiver"
            logger.info(f"🔄 Przełączono nadawcę na {server_state['current_sender']}")
        else:
            server_state["current_sender"] = None
            server_state["instances"][instance_id]["role"] = "receiver"
    return jsonify({"status": "roles updated"})

if __name__ == "__main__":
    public_url = ngrok.connect(5000).public_url
    logger.info(f"🌐 Serwer Flask dostępny pod: {public_url}")
    app.run(host="0.0.0.0", port=5000)