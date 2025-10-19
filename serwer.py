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
    "current_action": None,  # {"type": "human_speak"/"bot_speak"/"ggwave_send"/"ggwave_receive", "instance_id": str}
    "action_queue": [],  # Queue of pending actions
    "current_sender": None  # Current GGWave sender
}

# Action types
ACTION_HUMAN_SPEAK = "human_speak"
ACTION_BOT_SPEAK = "bot_speak"
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
        return jsonify({"role": server_state["instances"][instance_id]["role"]})
    return jsonify({"error": "instance not found"}), 404

@app.route("/request_action", methods=["POST"])
def request_action():
    data = request.json
    instance_id = data["instance_id"]
    action_type = data["action_type"]  # e.g., human_speak, bot_speak, ggwave_send, ggwave_receive
    if instance_id not in server_state["instances"]:
        return jsonify({"error": "instance not found"}), 404
    
    server_state["instances"][instance_id]["last_active"] = time.time()
    
    # If no action is currently active, assign immediately
    if not server_state["current_action"]:
        server_state["current_action"] = {"type": action_type, "instance_id": instance_id}
        logger.info(f"🎮 Assigned action {action_type} to {instance_id}")
        return jsonify({"status": "approved", "action": action_type})
    
    # If action is pending, add to queue
    server_state["action_queue"].append({"type": action_type, "instance_id": instance_id})
    logger.info(f"⏳ Queued action {action_type} for {instance_id}")
    return jsonify({"status": "queued"})

@app.route("/complete_action", methods=["POST"])
def complete_action():
    data = request.json
    instance_id = data["instance_id"]
    if (server_state["current_action"] and 
        server_state["current_action"]["instance_id"] == instance_id):
        completed_action = server_state["current_action"]["type"]
        server_state["current_action"] = None
        logger.info(f"✅ Completed action {completed_action} by {instance_id}")
        
        # Assign the next action from the queue
        if server_state["action_queue"]:
            next_action = server_state["action_queue"].pop(0)
            server_state["current_action"] = next_action
            logger.info(f"🎮 Assigned next action {next_action['type']} to {next_action['instance_id']}")
            
            # If the next action is GGWave-related, ensure role consistency
            if next_action["type"] == ACTION_GGWAVE_SEND:
                if server_state["current_sender"] != next_action["instance_id"]:
                    server_state["current_sender"] = next_action["instance_id"]
                    server_state["instances"][next_action["instance_id"]]["role"] = "sender"
                    for iid in server_state["instances"]:
                        if iid != next_action["instance_id"]:
                            server_state["instances"][iid]["role"] = "receiver"
                    logger.info(f"🔄 Updated sender to {next_action['instance_id']}")
        
        return jsonify({"status": "completed"})
    return jsonify({"error": "no active action for this instance"}), 400

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
            logger.info(f"🔄 Switched sender to {server_state['current_sender']}")
        else:
            server_state["current_sender"] = None
            server_state["instances"][instance_id]["role"] = "receiver"
    return jsonify({"status": "roles updated"})

if __name__ == "__main__":
    public_url = ngrok.connect(5000).public_url
    logger.info(f"🌐 Flask server available at: {public_url}")
    app.run(host="0.0.0.0", port=5000)