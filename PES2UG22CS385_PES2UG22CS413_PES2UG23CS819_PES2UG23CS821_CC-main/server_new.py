import time
import uuid
import random
import csv
import io
import os
from flask import Flask, request, jsonify, render_template, send_file, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from threading import Thread, RLock
from supabase_init import (
    init_supabase_tables, get_nodes, get_pods, get_logs, 
    get_utilization_history, save_node, delete_node, save_pod, 
    update_pod_node, log_event, record_utilization
)

# ---- Docker SDK & Network-Policy Setup ----
import docker
from docker.errors import NotFound, DockerException

DOCKER_NODE_IMAGE = "node-simulator:latest"
NODE_HEARTBEAT_INTERVAL = 7  # seconds
try:
    docker_client = docker.from_env()
except DockerException:
    docker_client = None
    print("⚠️ Docker not available—containers will NOT be launched.")
print("🔍 Docker client:", "OK" if docker_client else "NOT AVAILABLE")

def ensure_network(group):
    """Create or fetch a Docker bridge network named net_<group>."""
    if not docker_client:
        return None
    net_name = f"net_{group}"
    try:
        return docker_client.networks.get(net_name)
    except NotFound:
        return docker_client.networks.create(net_name, driver="bridge")

# ----------------------------------
# Global Data & Locks
# ----------------------------------
nodes = {}  # In-memory cache of nodes
event_log = []  # In-memory cache of recent events
utilization_history = []  # In-memory cache of utilization history
nodes_lock = RLock()
pod_id_lock = RLock()
pod_id_counter = 0

DEFAULT_NODE_CPU = 8
DEFAULT_NODE_MEMORY = 16
DEFAULT_POD_MEMORY = 4

AUTO_SCALE_THRESHOLD = 0.8
last_auto_scale_time = 0
AUTO_SCALE_COOLDOWN = 60
HEARTBEAT_THRESHOLD = 15
HEALTH_CHECK_INTERVAL = 5

SCHEDULING_ALGORITHMS = ['first_fit', 'best_fit', 'worst_fit']

app = Flask(__name__, static_folder="./static")
CORS(app)  # Enable CORS for all routes
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ----------------------------------
# Utility Functions
# ----------------------------------
def get_current_timestamp():
    return time.time()

def log_event_func(event):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(get_current_timestamp()))
    entry = f"[{ts}] {event}"
    with nodes_lock:
        event_log.append(entry)
        if len(event_log) > 50:
            event_log.pop(0)
    # Log to Supabase
    log_event(event)

def load_cluster_state():
    """Load cluster state from Supabase."""
    global nodes, pod_id_counter
    
    # Get nodes from Supabase
    supabase_nodes = get_nodes()
    
    # Get pods from Supabase
    supabase_pods = get_pods()
    
    # Process nodes
    with nodes_lock:
        nodes.clear()
        for node_data in supabase_nodes:
            node_id = node_data["node_id"]
            nodes[node_id] = {
                "node_id": node_id,
                "cpu_total": node_data["cpu_total"],
                "cpu_available": node_data["cpu_available"],
                "memory_total": node_data["memory_total"],
                "memory_available": node_data["memory_available"],
                "node_type": node_data["node_type"],
                "network_group": node_data["network_group"],
                "last_heartbeat": node_data["last_heartbeat"],
                "status": node_data["status"],
                "simulate_heartbeat": bool(node_data["simulate_heartbeat"]),
                "pods": [],
                "container_id": node_data.get("container_id")
            }
        
        # Process pods
        max_pod_id = 0
        for pod_data in supabase_pods:
            pod_id = pod_data["pod_id"]
            node_id = pod_data["node_id"]
            
            # Extract numeric part of pod_id to update pod_id_counter
            if pod_id.startswith("pod_"):
                try:
                    pod_num = int(pod_id.split("_")[1])
                    max_pod_id = max(max_pod_id, pod_num)
                except:
                    pass
                
            pod = {
                "pod_id": pod_id,
                "cpu": pod_data["cpu"],
                "memory": pod_data["memory"],
                "network_group": pod_data["network_group"],
                "cpu_usage": 0
            }
            if pod_data.get("node_affinity"):
                pod["node_affinity"] = pod_data["node_affinity"]
                
            if node_id in nodes:
                nodes[node_id]["pods"].append(pod)
        
        # Update pod_id_counter
        pod_id_counter = max_pod_id

@socketio.on('connect')
def on_connect():
    with nodes_lock:
        state = {
            "nodes": list(nodes.values()),
            "logs": event_log[-50:],
            "history": [{"timestamp": record["timestamp"], "utilization": record["utilization"]} 
                        for record in get_utilization_history()]
        }
    emit('state_update', state)

def record_utilization_thread():
    while True:
        time.sleep(10)
        util = get_cluster_utilization() * 100
        ts = get_current_timestamp()
        with nodes_lock:
            utilization_history.append((ts, util))
            if len(utilization_history) > 50:
                utilization_history.pop(0)
        # Save to Supabase
        record_utilization(util)

def get_cluster_utilization():
    total = used = 0
    with nodes_lock:
        for n in nodes.values():
            if n["status"] == "active":
                total += n["cpu_total"]
                used += (n["cpu_total"] - n["cpu_available"])
    return 0.0 if total == 0 else used / total

# ----------------------------------
# Scheduling & Pod Persistence
# ----------------------------------
def schedule_pod(pod, algo):
    with nodes_lock:
        eligible = [
            n for n in nodes.values()
            if n["status"] == "active"
               and n["cpu_available"] >= pod["cpu"]
               and n["memory_available"] >= pod["memory"]
               and n["network_group"] == pod["network_group"]
        ]
        if "node_affinity" in pod:
            eligible = [n for n in eligible if n["node_type"] == pod["node_affinity"]]
        if not eligible:
            return False, None
        if algo == "first_fit":
            cand = eligible[0]
        elif algo == "best_fit":
            cand = min(eligible, key=lambda n: (n["cpu_available"] - pod["cpu"]) + (n["memory_available"] - pod["memory"]))
        else:  # worst_fit
            cand = max(eligible, key=lambda n: n["cpu_available"] + n["memory_available"])
        cand["pods"].append(pod)
        cand["cpu_available"] -= pod["cpu"]
        cand["memory_available"] -= pod["memory"]
        save_node(cand)
        log_event_func(f"Pod {pod['pod_id']} scheduled on node {cand['node_id']} via {algo}")
        return True, cand["node_id"]

def reschedule_pods_from_failed_node(nid):
    with nodes_lock:
        failed = nodes.pop(nid, None)
    if not failed:
        return
    delete_node(nid)
    for pod in failed["pods"]:
        ok, new_nid = schedule_pod(pod, "first_fit")
        if ok:
            update_pod_node(pod["pod_id"], new_nid)
            log_event_func(f"Rescheduled pod {pod['pod_id']} → {new_nid}")
        else:
            log_event_func(f"Failed to reschedule pod {pod['pod_id']}")

# ----------------------------------
# Health Monitor & Heartbeats
# ----------------------------------
def health_monitor():
    while True:
        time.sleep(HEALTH_CHECK_INTERVAL)
        now = get_current_timestamp()
        to_fail = []
        with nodes_lock:
            for nid, n in list(nodes.items()):
                if n["status"] == "active" and (now - n["last_heartbeat"]) > HEARTBEAT_THRESHOLD:
                    n["status"] = "failed"
                    save_node(n)
                    log_event_func(f"Node {nid} marked FAILED")
                    to_fail.append(nid)
        for nid in to_fail:
            socketio.emit("alert", {"msg": f"Node {nid} failed"})
            reschedule_pods_from_failed_node(nid)

def simulate_heartbeat_thread():
    while True:
        time.sleep(NODE_HEARTBEAT_INTERVAL)
        with nodes_lock:
            for n in nodes.values():
                if n["simulate_heartbeat"]:
                    n["last_heartbeat"] = get_current_timestamp()
                    save_node(n)

# ----------------------------------
# Auto‐scaling with Docker & Persistence
# ----------------------------------
def auto_scale_cluster():
    global last_auto_scale_time
    while True:
        time.sleep(HEALTH_CHECK_INTERVAL)
        util = get_cluster_utilization()
        now = get_current_timestamp()
        if util >= AUTO_SCALE_THRESHOLD and (now - last_auto_scale_time) >= AUTO_SCALE_COOLDOWN:
            nid = str(uuid.uuid4())
            nt = random.choice(["high_cpu", "high_mem", "balanced"])
            ng = random.choice(["default", "isolated"])
            node = {
                "node_id": nid,
                "cpu_total": DEFAULT_NODE_CPU,
                "cpu_available": DEFAULT_NODE_CPU,
                "memory_total": DEFAULT_NODE_MEMORY,
                "memory_available": DEFAULT_NODE_MEMORY,
                "node_type": nt,
                "network_group": ng,
                "pods": [],
                "last_heartbeat": now,
                "status": "active",
                "simulate_heartbeat": True
            }
            with nodes_lock:
                nodes[nid] = node
            save_node(node)
            net = ensure_network(ng)
            if docker_client and net:
                try:
                    cont = docker_client.containers.run(
                        DOCKER_NODE_IMAGE,
                        command=[
                            "--server", "http://host.docker.internal:5000",
                            "--node_id", nid,
                            "--interval", str(NODE_HEARTBEAT_INTERVAL)
                        ],
                        name=f"node_{nid}",
                        detach=True,
                        network=net.name,
                        cpu_count=DEFAULT_NODE_CPU,
                        mem_limit=f"{DEFAULT_NODE_MEMORY}g",
                        labels={"sim-node": nid, "autoscaled": "true"},
                        remove=True
                    )
                    nodes[nid]["container_id"] = cont.id
                    save_node(nodes[nid])
                    log_event_func(f"Container {cont.id[:12]} launched for auto‐scaled node {nid}")
                except Exception as e:
                    log_event_func(f"Auto‐scale container error for {nid}: {e}")
            else:
                log_event_func(f"Skipping container launch for auto‐scaled node {nid}")
            log_event_func(f"Auto‐scaled: Added node {nid} ({DEFAULT_NODE_CPU} CPU, {DEFAULT_NODE_MEMORY}GB, Type:{nt}, Group:{ng})")
            last_auto_scale_time = now

# ----------------------------------
# Chaos Monkey & Broadcast
# ----------------------------------
def chaos_monkey():
    with nodes_lock:
        active = [n for n in nodes.values() if n["status"] == "active"]
    if not active:
        return {"message": "No active nodes"}
    target = random.choice(active)
    target["status"] = "failed"
    save_node(target)
    log_event_func(f"Chaos Monkey killed node {target['node_id']}")
    reschedule_pods_from_failed_node(target["node_id"])
    return {"message": f"Killed node {target['node_id']}"}

def broadcast_state():
    while True:
        time.sleep(3)
        with nodes_lock:
            state = {
                "nodes": list(nodes.values()),
                "logs": event_log[-50:],
                "history": [{"timestamp": ts, "utilization": util} for ts, util in utilization_history]
            }
        socketio.emit("state_update", state)

# ----------------------------------
# API Endpoints
# ----------------------------------
@app.route('/api/add_node', methods=['POST'])
def add_node_endpoint():
    data = request.get_json() or {}
    print("▶️  /add_node called with:", data)

    cpu = data.get("cpu")
    if cpu is None:
        print("❌  Missing cpu in payload")
        return jsonify({"error": "Missing cpu"}), 400
    mem = data.get("memory", DEFAULT_NODE_MEMORY)
    nt = data.get("node_type", "balanced")
    ng = data.get("network_group", "default")

    # 1) create node record
    node_id = str(uuid.uuid4())
    node = {
        "node_id": node_id,
        "cpu_total": cpu, "cpu_available": cpu,
        "memory_total": mem, "memory_available": mem,
        "node_type": nt, "network_group": ng,
        "pods": [], "last_heartbeat": time.time(),
        "status": "active", "simulate_heartbeat": True
    }
    with nodes_lock:
        nodes[node_id] = node
    save_node(node)
    log_event_func(f"Added node {node_id} ({cpu} CPU, {mem}GB, {nt}/{ng})")

    # 2) launch container
    if docker_client:
        server_url = "http://host.docker.internal:5000"
        print(f"⚙️  Launching container for {node_id} on network '{ng}' via {server_url}")
        net = ensure_network(ng)
        try:
            container = docker_client.containers.run(
                DOCKER_NODE_IMAGE,
                command=[
                    "--server", server_url,
                    "--node_id", node_id,
                    "--interval", str(NODE_HEARTBEAT_INTERVAL)
                ],
                name=f"node_{node_id}",
                detach=True,
                network=net.name if net else None,
                cpu_count=cpu,
                mem_limit=f"{mem}g",
                labels={"sim-node": node_id},
                auto_remove=False
            )
            print("✅ Container started:", container.id)
            with nodes_lock:
                nodes[node_id]["container_id"] = container.id
            save_node(nodes[node_id])
            log_event_func(f"Container {container.id[:12]} launched for node {node_id}")
        except Exception as ex:
            print("❌ Container launch error:", ex)
            log_event_func(f"ERROR launching container for node {node_id}: {ex}")
    else:
        print("⚠️  Skipping container launch (no docker_client)")

    return jsonify({"message": "Node added", "node_id": node_id}), 200

@app.route('/api/toggle_simulation', methods=['POST'])
def toggle_simulation():
    data = request.get_json()
    nid, sim = data.get("node_id"), bool(data.get("simulate"))
    if not nid:
        return jsonify({"error": "Missing node_id"}), 400
    with nodes_lock:
        n = nodes.get(nid)
        if not n:
            return jsonify({"error": "Not found"}), 404
        n["simulate_heartbeat"] = sim
        save_node(n)
    log_event_func(f"Simulation for {nid} set to {sim}")
    return jsonify({"message": "OK"}), 200

@app.route('/api/remove_node', methods=['POST'])
def remove_node_endpoint():
    data = request.get_json()
    nid = data.get("node_id")
    if not nid:
        return jsonify({"error": "Missing node_id"}), 400
    
    with nodes_lock:
        if nid not in nodes:
            return jsonify({"error": "Node not found"}), 404
        
        # Check if this node has a container running
        container_id = nodes[nid].get("container_id")
        if container_id and docker_client:
            try:
                container = docker_client.containers.get(container_id)
                container.stop()
                log_event_func(f"Container {container_id[:12]} stopped for node {nid}")
            except Exception as e:
                log_event_func(f"Error stopping container for node {nid}: {e}")
        
        # Remove node and reschedule pods
        reschedule_pods_from_failed_node(nid)
    
    return jsonify({"message": f"Node {nid} removed"}), 200

@app.route('/api/list_nodes', methods=['GET'])
def list_nodes_api():
    with nodes_lock:
        return jsonify({"nodes": list(nodes.values())}), 200

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat_api():
    data = request.get_json() or {}
    nid = data.get("node_id")
    with nodes_lock:
        n = nodes.get(nid)
        if not n:
            return jsonify({"error": "Unknown"}), 404
        n["last_heartbeat"] = time.time()
        if n["status"] == "failed":
            n["status"] = "active"
            save_node(n)
            log_event_func(f"Node {nid} reactivated")
    return jsonify({"message": "OK"}), 200

@app.route('/api/launch_pod', methods=['POST'])
def launch_pod_endpoint():
    data = request.get_json() or {}
    print("▶️  /launch_pod called with:", data)

    cpu_req = data.get("cpu_required")
    if cpu_req is None:
        print("❌  Missing cpu_required")
        return jsonify({"error": "Missing cpu_required"}), 400

    mem_req = data.get("memory_required", DEFAULT_POD_MEMORY)
    algo = data.get("scheduling_algorithm", "first_fit").lower()
    ng = data.get("network_group", "default")
    affinity = data.get("node_affinity")

    global pod_id_counter
    with pod_id_lock:
        pod_id_counter += 1
        pid = f"pod_{pod_id_counter}"

    pod = {
        "pod_id": pid,
        "cpu": cpu_req,
        "memory": mem_req,
        "network_group": ng,
        "cpu_usage": 0,
        "node_id": None  # Will be assigned during scheduling
    }
    if affinity:
        pod["node_affinity"] = affinity

    scheduled, assigned = schedule_pod(pod, algo)
    if scheduled:
        pod["node_id"] = assigned
        save_pod(pod)
        print(f"✅ Pod {pid} scheduled on node {assigned} via {algo}")
        return jsonify({
            "message": "Pod launched",
            "pod_id": pid,
            "assigned_node": assigned,
            "scheduling_algorithm": algo
        }), 200
    else:
        print(f"❌ No capacity for pod {pid}")
        return jsonify({"error": "No available node with sufficient resources"}), 400

@app.route('/api/chaos_monkey', methods=['POST'])
def chaos_api():
    return jsonify(chaos_monkey()), 200

@app.route('/api/download_report', methods=['GET'])
def download_report():
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(["Node", "CPU tot/avail", "Mem tot/avail", "Status", "Type", "Group", "Pods"])
    with nodes_lock:
        for n in nodes.values():
            pods = ";".join(p["pod_id"] for p in n["pods"]) or "None"
            w.writerow([
                n["node_id"],
                f"{n['cpu_total']}/{n['cpu_available']}",
                f"{n['memory_total']}/{n['memory_available']}",
                n["status"], n["node_type"], n["network_group"], pods
            ])
    out.seek(0)
    return send_file(io.BytesIO(out.getvalue().encode()),
                     mimetype="text/csv",
                     as_attachment=True,
                     download_name="cluster_report.csv")

@app.route('/api/logs', methods=['GET'])
def logs_api():
    logs = get_logs()
    return jsonify({"logs": logs}), 200

@app.route('/api/utilization_history', methods=['GET'])
def util_api():
    history = get_utilization_history()
    return jsonify({"history": history}), 200

# Serve the React app
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

# ----------------------------------
# Background Tasks & Startup
# ----------------------------------
def background_tasks():
    Thread(target=health_monitor, daemon=True).start()
    Thread(target=simulate_heartbeat_thread, daemon=True).start()
    Thread(target=auto_scale_cluster, daemon=True).start()
    Thread(target=record_utilization_thread, daemon=True).start()
    Thread(target=broadcast_state, daemon=True).start()

if __name__ == '__main__':
    # Initialize Supabase tables
    init_supabase_tables()
    
    # Load state from Supabase
    load_cluster_state()
    
    # Start background tasks
    background_tasks()
    
    # Start server
    socketio.run(app, host="0.0.0.0", port=5000, debug=True) 