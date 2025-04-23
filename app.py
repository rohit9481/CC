from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
from api.node_manager import NodeManager, HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT
from api.docker_utils import launch_node_container
import time
import threading
import logging

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = "your-secret-key-here"
socketio = SocketIO(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize components
node_manager = NodeManager()


# Routes for GUI
@app.route("/")
def dashboard():
    """Render the main dashboard page"""
    return render_template(
        "dashboard.html",
        nodes=node_manager.get_nodes(),
        node_count=len(node_manager.get_nodes()),
        title="Cluster Dashboard",
    )


@app.route("/nodes")
def nodes_view():
    """Render the nodes management page"""
    return render_template(
        "nodes.html", nodes=node_manager.get_nodes(), title="Node Management"
    )


# API Endpoints
@app.route("/api/nodes", methods=["GET", "POST"])
def nodes_api():
    """Handle node operations via API"""
    if request.method == "POST":
        data = request.get_json()
        cpu_cores = data.get("cpu_cores", 1)

        if cpu_cores <= 0:
            return jsonify({"error": "CPU cores must be positive"}), 400

        container_id = launch_node_container(cpu_cores)
        print(container_id)

        if not container_id:
            container_id = f"simulated_node_{int(time.time())}"
            print("Docker not available using simulated node")
            logger.warning("Docker not available - using simulated node")

        node_manager.register_node(container_id, cpu_cores)

        # Start heartbeat simulation
        threading.Thread(
            target=simulate_node_heartbeat,
            args=(container_id,),
            name=f"Heartbeat-{container_id[:8]}",
            daemon=True,
        ).start()

        socketio.emit("node_update", node_manager.get_nodes())
        return (
            jsonify(
                {"status": "success", "node_id": container_id, "cpu_cores": cpu_cores}
            ),
            201,
        )

    return jsonify(node_manager.get_nodes())


@app.route("/api/stats", methods=["GET"])
def cluster_stats():
    """Get cluster statistics"""
    nodes = node_manager.get_nodes()
    stats = {
        "total_nodes": len(nodes),
        "healthy_nodes": sum(1 for n in nodes.values() if n["status"] == "healthy"),
        "total_cpu": sum(n["cpu"] for n in nodes.values()),
        "available_cpu": sum(n["available_cpu"] for n in nodes.values()),
        "total_pods": sum(len(n["pods"]) for n in nodes.values()),
    }
    return jsonify(stats)


# delete nodes


@app.route("/api/nodes/<node_id>", methods=["DELETE"])
def delete_node(node_id):
    """Delete or stop a node by its ID"""
    if not node_manager.node_exists(node_id):
        return jsonify({"error": "Node not found"}), 404

    # Optionally stop Docker container (if running with Docker)
    try:
        from api.docker_utils import stop_node_container

        stop_node_container(node_id)
    except Exception as e:
        logger.warning(f"Could not stop Docker container {node_id}: {e}")

    # Remove from node manager
    node_manager.unregister_node(node_id)

    socketio.emit("node_update", node_manager.get_nodes())
    return jsonify({"status": "success", "message": f"Node {node_id} deleted"}), 200


# Background tasks
def simulate_node_heartbeat(node_id):
    """Simulate periodic heartbeats from a node"""
    while node_manager.node_exists(node_id):
        try:
            time.sleep(HEARTBEAT_INTERVAL)
            node_manager.update_heartbeat(node_id)
            socketio.emit("heartbeat", {"node_id": node_id})
        except Exception as e:
            logger.error(f"Heartbeat error for node {node_id}: {str(e)}")
            break


def health_monitor():
    """Background thread to monitor node health"""
    while True:
        try:
            time.sleep(HEARTBEAT_INTERVAL)
            node_manager.check_node_health()
            socketio.emit("health_update", node_manager.get_nodes())
        except Exception as e:
            logger.error(f"Health monitor error: {str(e)}")


if __name__ == "__main__":
    # Start background services
    threading.Thread(target=health_monitor, name="HealthMonitor", daemon=True).start()

    # Start Flask server with SocketIO
    logger.info("Starting Cluster Simulation GUI on http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
