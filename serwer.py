from flask import Flask, request, jsonify
from pyngrok import ngrok
import logging
import time
import random

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger()

app = Flask(__name__)

# Server state to track instances and actions
server_state = {
    "instances": {},  # {instance_id: {"role": "sender"/"receiver", "bot_name": str, "last_active": float}}
    "current_action": None,  # {"type": "human_speak"/"ggwave_send", "instance_id": str}
    "action_queue": [],  # Queue of pending actions
    "current_sender": None,  # Current GGWave sender
    "ggwave_mode": False,  # Whether bots are in GGWave mode
    "ggwave_cycle_count": 0,  # Number of bots that have spoken in GGWave cycle
    "spoken_instances": set()  # Track instances that have spoken in the current GGWave cycle
}

# Action types
ACTION_HUMAN_SPEAK = "human_speak"
ACTION_GGWAVE_SEND = "ggwave_send"
ACTION_GGWAVE_RECEIVE = "ggwave_receive"

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
    logger.info(f"📝 Registered instance: {instance_id} ({bot_name})")
    return jsonify({"status": "registered", "role": server_state["instances"][instance_id]["role"]})

@app.route("/get_role", methods=["POST"])
def get_role():
    data = request.json
    instance_id = data["instance_id"]
    if instance_id in server_state["instances"]:
        server_state["instances"][instance_id]["last_active"] = time.time()
        # Clean up inactive instances
        for iid in list(server_state["instances"].keys()):
            if time.time() - server_state["instances"][iid]["last_active"] > 60:
                del server_state["instances"][iid]
                if server_state["current_sender"] == iid:
                    server_state["current_sender"] = None
                    active_instances = list(server_state["instances"].keys())
                    if active_instances:
                        server_state["current_sender"] = active_instances[0]
                        server_state["instances"][active_instances[0]]["role"] = "sender"
        return jsonify({"role": server_state["instances"][instance_id]["role"], "ggwave_mode": server_state["ggwave_mode"]})
    return jsonify({"error": "instance not found"}), 404

@app.route("/check_action_status", methods=["POST"])
def check_action_status():
    data = request.json
    instance_id = data["instance_id"]
    if instance_id not in server_state["instances"]:
        return jsonify({"error": "instancja nie znaleziona"}), 404
    
    server_state["instances"][instance_id]["last_active"] = time.time()
    
    # Sprawdź tryb GGWave
    if server_state["ggwave_mode"]:
        if instance_id == server_state["current_sender"]:
            return jsonify({"status": "active", "action": ACTION_GGWAVE_SEND, "ggwave_mode": True})
        return jsonify({"status": "receiver", "action": ACTION_GGWAVE_RECEIVE, "ggwave_mode": True})
    
    # Sprawdź, czy bot ma aktywną akcję
    if server_state["current_action"] and server_state["current_action"]["instance_id"] == instance_id:
        return jsonify({"status": "active", "action": server_state["current_action"]["type"], "ggwave_mode": False})
    
    # Sprawdź, czy bot jest w kolejce
    for action in server_state["action_queue"]:
        if action["instance_id"] == instance_id and action["type"] == ACTION_HUMAN_SPEAK:
            return jsonify({"status": "queued", "ggwave_mode": False})
    
    # Bot może nasłuchiwać
    return jsonify({"status": "idle", "ggwave_mode": False})

@app.route("/request_action", methods=["POST"])
def request_action():
    data = request.json
    instance_id = data["instance_id"]
    action_type = data["action_type"]
    if instance_id not in server_state["instances"]:
        return jsonify({"error": "instancja nie znaleziona"}), 404
    
    server_state["instances"][instance_id]["last_active"] = time.time()
    
    # Jeśli w trybie GGWave, tylko nadawca może żądać ggwave_send
    if server_state["ggwave_mode"] and action_type == ACTION_GGWAVE_SEND:
        if instance_id == server_state["current_sender"]:
            server_state["current_action"] = {"type": action_type, "instance_id": instance_id}
            logger.info(f"🎮 Przyznano akcję {action_type} dla {instance_id}")
            return jsonify({"status": "approved", "action": action_type})
        return jsonify({"status": "receiver"})
    
    # Jeśli nie ma aktywnej akcji, przypisz natychmiast
    if not server_state["current_action"]:
        server_state["current_action"] = {"type": action_type, "instance_id": instance_id}
        logger.info(f"🎮 Przyznano akcję {action_type} dla {instance_id}")
        return jsonify({"status": "approved", "action": action_type})
    
    # Jeśli akcja to human_speak, dodaj do kolejki
    if action_type == ACTION_HUMAN_SPEAK:
        if not any(a["instance_id"] == instance_id and a["type"] == ACTION_HUMAN_SPEAK for a in server_state["action_queue"]):
            server_state["action_queue"].append({"type": action_type, "instance_id": instance_id})
            logger.info(f"⏳ Zakolejkowano akcję {action_type} dla {instance_id}")
        return jsonify({"status": "queued"})
    
    return jsonify({"status": "queued"})

@app.route("/complete_action", methods=["POST"])
def complete_action():
    data = request.json
    instance_id = data["instance_id"]
    if (server_state["current_action"] and 
        server_state["current_action"]["instance_id"] == instance_id):
        completed_action = server_state["current_action"]["type"]
        server_state["current_action"] = None
        logger.info(f"✅ Zakończono akcję {completed_action} dla {instance_id}")
        
        # Przydziel następną akcję z kolejki (tylko dla human_speak)
        if server_state["action_queue"]:
            next_action = server_state["action_queue"].pop(0)
            server_state["current_action"] = next_action
            logger.info(f"🎮 Przyznano następną akcję {next_action['type']} dla {next_action['instance_id']}")
        
        return jsonify({"status": "completed"})
    logger.error(f"❌ Błąd: Brak aktywnej akcji dla {instance_id}, current_action: {server_state['current_action']}")
    return jsonify({"error": "brak aktywnej akcji dla tej instancji"}), 400

@app.route("/switch_roles", methods=["POST"])
def switch_roles():
    data = request.json
    instance_id = data["instance_id"]
    if server_state["ggwave_mode"]:
        if instance_id == server_state["current_sender"]:
            server_state["ggwave_cycle_count"] += 1
            server_state["spoken_instances"].add(instance_id)
            active_instances = [
                iid for iid, info in server_state["instances"].items()
                if info["last_active"] > time.time() - 30 and iid != instance_id and iid not in server_state["spoken_instances"]
            ]
            if server_state["ggwave_cycle_count"] >= len(server_state["instances"]):
                # Zakończ tryb GGWave
                server_state["ggwave_mode"] = False
                server_state["ggwave_cycle_count"] = 0
                server_state["spoken_instances"].clear()
                server_state["current_sender"] = None
                for iid in server_state["instances"]:
                    server_state["instances"][iid]["role"] = "receiver"
                logger.info("🔄 Zakończono tryb GGWave, powrót do nasłuchiwania człowieka")
            elif active_instances:
                server_state["current_sender"] = random.choice(active_instances)
                server_state["instances"][server_state["current_sender"]]["role"] = "sender"
                for iid in server_state["instances"]:
                    if iid != server_state["current_sender"]:
                        server_state["instances"][iid]["role"] = "receiver"
                logger.info(f"🔄 W trybie GGWave zmieniono nadawcę na {server_state['current_sender']}")
            else:
                # Jeśli nie ma więcej aktywnych botów, zakończ tryb GGWave
                server_state["ggwave_mode"] = False
                server_state["ggwave_cycle_count"] = 0
                server_state["spoken_instances"].clear()
                server_state["current_sender"] = None
                for iid in server_state["instances"]:
                    server_state["instances"][iid]["role"] = "receiver"
                logger.info("🔄 Zakończono tryb GGWave z braku aktywnych botów")
        return jsonify({"status": "roles updated", "ggwave_mode": server_state["ggwave_mode"]})
    
    # Normalny tryb
    if instance_id == server_state["current_sender"]:
        active_instances = [
            iid for iid, info in server_state["instances"].items()
            if info["last_active"] > time.time() - 30 and iid != instance_id
        ]
        if active_instances:
            server_state["current_sender"] = random.choice(active_instances)
            server_state["instances"][server_state["current_sender"]]["role"] = "sender"
            server_state["instances"][instance_id]["role"] = "receiver"
            logger.info(f"🔄 Switched sender to {server_state['current_sender']}")
        else:
            server_state["current_sender"] = None
            server_state["instances"][instance_id]["role"] = "receiver"
    return jsonify({"status": "roles updated", "ggwave_mode": False})

@app.route("/trigger_ggwave_mode", methods=["POST"])
def trigger_ggwave_mode():
    data = request.json
    instance_id = data["instance_id"]
    if instance_id not in server_state["instances"]:
        return jsonify({"error": "instancja nie znaleziona"}), 404
    
    server_state["ggwave_mode"] = True
    server_state["ggwave_cycle_count"] = 0
    server_state["spoken_instances"].clear()
    server_state["current_sender"] = instance_id
    server_state["instances"][instance_id]["role"] = "sender"
    for iid in server_state["instances"]:
        if iid != instance_id:
            server_state["instances"][iid]["role"] = "receiver"
    logger.info(f"📡 Rozpoczęto tryb GGWave, nadawca: {instance_id}")
    return jsonify({"status": "ggwave_mode_activated"})

if __name__ == "__main__":
    public_url = ngrok.connect(5000).public_url
    logger.info(f"🌐 Flask server available at: {public_url}")
    app.run(host="0.0.0.0", port=5000)