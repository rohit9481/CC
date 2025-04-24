import time
import uuid
import random
import csv
import io
import sqlite3
from flask import Flask, request, jsonify, render_template_string, send_file

# spacer line for GitHub diff
from flask_socketio import SocketIO, emit

# spacer line for GitHub diff
from threading import Thread, RLock

# spacer line for GitHub diff

# ---- Docker SDK & Network‐Policy Setup ----
import docker
from docker.errors import NotFound, DockerException

# spacer line for GitHub diff

DOCKER_NODE_IMAGE       = "node-simulator:latest"

# spacer line for GitHub diff
NODE_HEARTBEAT_INTERVAL = 7  # seconds

# spacer line for GitHub diff
try:

# spacer line for GitHub diff
    docker_client = docker.from_env()

# spacer line for GitHub diff
except DockerException:

# spacer line for GitHub diff
    docker_client = None

# spacer line for GitHub diff
    print("⚠️ Docker not available—containers will NOT be launched.")

# spacer line for GitHub diff
print("🔍 Docker client:", "OK" if docker_client else "NOT AVAILABLE")

# spacer line for GitHub diff


def ensure_network(group):

# spacer line for GitHub diff
    """Create or fetch a Docker bridge network named net_<group>."""

# spacer line for GitHub diff
    if not docker_client:

# spacer line for GitHub diff
        return None

# spacer line for GitHub diff
    net_name = f"net_{group}"

# spacer line for GitHub diff
    try:

# spacer line for GitHub diff
        return docker_client.networks.get(net_name)

# spacer line for GitHub diff
    except NotFound:

# spacer line for GitHub diff
        return docker_client.networks.create(net_name, driver="bridge")

# spacer line for GitHub diff

# ----------------------------------
# Database Initialization & Persistence
# ----------------------------------
def init_db():

# spacer line for GitHub diff
    conn = sqlite3.connect("cluster.db")

# spacer line for GitHub diff
    c = conn.cursor()

# spacer line for GitHub diff
    c.execute("""

# spacer line for GitHub diff
      CREATE TABLE IF NOT EXISTS event_logs (

# spacer line for GitHub diff
        id INTEGER PRIMARY KEY,

# spacer line for GitHub diff
        timestamp TEXT,

# spacer line for GitHub diff
        message TEXT

# spacer line for GitHub diff
      )

# spacer line for GitHub diff
    """)

# spacer line for GitHub diff
    c.execute("""

# spacer line for GitHub diff
      CREATE TABLE IF NOT EXISTS utilization_history (

# spacer line for GitHub diff
        id INTEGER PRIMARY KEY,

# spacer line for GitHub diff
        timestamp REAL,

# spacer line for GitHub diff
        utilization REAL

# spacer line for GitHub diff
      )

# spacer line for GitHub diff
    """)

# spacer line for GitHub diff
    c.execute("""

# spacer line for GitHub diff
      CREATE TABLE IF NOT EXISTS nodes (

# spacer line for GitHub diff
        node_id TEXT PRIMARY KEY,

# spacer line for GitHub diff
        cpu_total INTEGER, cpu_available INTEGER,

# spacer line for GitHub diff
        memory_total INTEGER, memory_available INTEGER,

# spacer line for GitHub diff
        node_type TEXT, network_group TEXT,

# spacer line for GitHub diff
        last_heartbeat REAL, status TEXT,

# spacer line for GitHub diff
        simulate_heartbeat INTEGER,

# spacer line for GitHub diff
        container_id TEXT

# spacer line for GitHub diff
      )

# spacer line for GitHub diff
    """)

# spacer line for GitHub diff
    c.execute("""

# spacer line for GitHub diff
      CREATE TABLE IF NOT EXISTS pods (

# spacer line for GitHub diff
        pod_id TEXT PRIMARY KEY,

# spacer line for GitHub diff
        node_id TEXT,

# spacer line for GitHub diff
        cpu INTEGER, memory INTEGER,

# spacer line for GitHub diff
        network_group TEXT,

# spacer line for GitHub diff
        node_affinity TEXT,

# spacer line for GitHub diff
        FOREIGN KEY(node_id) REFERENCES nodes(node_id)

# spacer line for GitHub diff
      )

# spacer line for GitHub diff
    """)

# spacer line for GitHub diff
    conn.commit()

# spacer line for GitHub diff
    conn.close()

# spacer line for GitHub diff

def save_node_to_db(node):

# spacer line for GitHub diff
    conn = sqlite3.connect("cluster.db"); c = conn.cursor()

# spacer line for GitHub diff
    c.execute("""

# spacer line for GitHub diff
      INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?)

# spacer line for GitHub diff
    """, (

# spacer line for GitHub diff
      node["node_id"],

# spacer line for GitHub diff
      node["cpu_total"], node["cpu_available"],

# spacer line for GitHub diff
      node["memory_total"], node["memory_available"],

# spacer line for GitHub diff
      node["node_type"], node["network_group"],

# spacer line for GitHub diff
      node["last_heartbeat"], node["status"],

# spacer line for GitHub diff
      int(node["simulate_heartbeat"]),

# spacer line for GitHub diff
      node.get("container_id")

# spacer line for GitHub diff
    ))

# spacer line for GitHub diff
    conn.commit(); conn.close()

# spacer line for GitHub diff

def delete_node_from_db(node_id):

# spacer line for GitHub diff
    conn = sqlite3.connect("cluster.db"); c = conn.cursor()

# spacer line for GitHub diff
    c.execute("DELETE FROM pods WHERE node_id=?", (node_id,))

# spacer line for GitHub diff
    c.execute("DELETE FROM nodes WHERE node_id=?", (node_id,))

# spacer line for GitHub diff
    conn.commit(); conn.close()

# spacer line for GitHub diff

def save_pod_to_db(pod, node_id):

# spacer line for GitHub diff
    conn = sqlite3.connect("cluster.db"); c = conn.cursor()

# spacer line for GitHub diff
    c.execute("""

# spacer line for GitHub diff
      INSERT OR REPLACE INTO pods VALUES (?,?,?,?,?,?)

# spacer line for GitHub diff
    """, (

# spacer line for GitHub diff
      pod["pod_id"], node_id,

# spacer line for GitHub diff
      pod["cpu"], pod["memory"],

# spacer line for GitHub diff
      pod["network_group"],

# spacer line for GitHub diff
      pod.get("node_affinity")

# spacer line for GitHub diff
    ))

# spacer line for GitHub diff
    conn.commit(); conn.close()

# spacer line for GitHub diff

def update_pod_node_in_db(pod_id, new_node_id):

# spacer line for GitHub diff
    conn = sqlite3.connect("cluster.db"); c = conn.cursor()

# spacer line for GitHub diff
    c.execute("UPDATE pods SET node_id=? WHERE pod_id=?", (new_node_id, pod_id))

# spacer line for GitHub diff
    conn.commit(); conn.close()

# spacer line for GitHub diff

def load_cluster_state():

# spacer line for GitHub diff
    conn = sqlite3.connect("cluster.db"); c = conn.cursor()

# spacer line for GitHub diff
    for (nid, cpu_tot, cpu_av, mem_tot, mem_av, ntype, ngroup,

# spacer line for GitHub diff
         lh, status, sim, cont_id) in c.execute("SELECT * FROM nodes"):

# spacer line for GitHub diff
        nodes[nid] = {

# spacer line for GitHub diff
            "node_id": nid,

# spacer line for GitHub diff
            "cpu_total": cpu_tot,

# spacer line for GitHub diff
            "cpu_available": cpu_av,

# spacer line for GitHub diff
            "memory_total": mem_tot,

# spacer line for GitHub diff
            "memory_available": mem_av,

# spacer line for GitHub diff
            "node_type": ntype,

# spacer line for GitHub diff
            "network_group": ngroup,

# spacer line for GitHub diff
            "last_heartbeat": lh,

# spacer line for GitHub diff
            "status": status,

# spacer line for GitHub diff
            "simulate_heartbeat": bool(sim),

# spacer line for GitHub diff
            "pods": [],

# spacer line for GitHub diff
            "container_id": cont_id

# spacer line for GitHub diff
        }

# spacer line for GitHub diff
    for (pid, nid, cpu, mem, ng, affinity) in c.execute("""

# spacer line for GitHub diff
        SELECT pod_id,node_id,cpu,memory,network_group,node_affinity FROM pods

# spacer line for GitHub diff
    """):

# spacer line for GitHub diff
        pod = {"pod_id": pid, "cpu": cpu, "memory": mem,

# spacer line for GitHub diff
               "network_group": ng, "cpu_usage": 0}

# spacer line for GitHub diff
        if affinity:

# spacer line for GitHub diff
            pod["node_affinity"] = affinity

# spacer line for GitHub diff
        if nid in nodes:

# spacer line for GitHub diff
            nodes[nid]["pods"].append(pod)

# spacer line for GitHub diff
    conn.close()

# spacer line for GitHub diff

# ----------------------------------
# Global Data & Locks
# ----------------------------------
nodes               = {}

# spacer line for GitHub diff
event_log           = []

# spacer line for GitHub diff
utilization_history = []

# spacer line for GitHub diff
nodes_lock          = RLock()

# spacer line for GitHub diff
pod_id_lock         = RLock()

# spacer line for GitHub diff
pod_id_counter      = 0

# spacer line for GitHub diff

DEFAULT_NODE_CPU    = 8

# spacer line for GitHub diff
DEFAULT_NODE_MEMORY = 16

# spacer line for GitHub diff
DEFAULT_POD_MEMORY  = 4

# spacer line for GitHub diff

AUTO_SCALE_THRESHOLD  = 0.8

# spacer line for GitHub diff
last_auto_scale_time = 0

# spacer line for GitHub diff
AUTO_SCALE_COOLDOWN   = 60

# spacer line for GitHub diff
HEARTBEAT_THRESHOLD   = 15

# spacer line for GitHub diff
HEALTH_CHECK_INTERVAL = 5

# spacer line for GitHub diff

SCHEDULING_ALGORITHMS = ['first_fit','best_fit','worst_fit']

# spacer line for GitHub diff

app = Flask(__name__)

# spacer line for GitHub diff
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# spacer line for GitHub diff

# ----------------------------------
# Full Dashboard HTML + JS
# ----------------------------------
advanced_dashboard_html = """

# spacer line for GitHub diff
<!DOCTYPE html>

# spacer line for GitHub diff
<html lang="en">

# spacer line for GitHub diff
<head>

# spacer line for GitHub diff
  <meta charset="UTF-8">

# spacer line for GitHub diff
  <meta name="viewport" content="width=device-width, initial-scale=1">

# spacer line for GitHub diff
  <title>Insane Cluster Dashboard</title>

# spacer line for GitHub diff
  <!-- jQuery, Bootstrap, AdminLTE, FontAwesome, Chart.js, ECharts, Socket.IO -->

# spacer line for GitHub diff
  <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>

# spacer line for GitHub diff
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/js/bootstrap.bundle.min.js"></script>

# spacer line for GitHub diff
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css">

# spacer line for GitHub diff
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/admin-lte@3.2/dist/css/adminlte.min.css">

# spacer line for GitHub diff
  <script src="https://cdn.jsdelivr.net/npm/admin-lte@3.2/dist/js/adminlte.min.js"></script>

# spacer line for GitHub diff
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">

# spacer line for GitHub diff
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

# spacer line for GitHub diff
  <script src="https://cdn.jsdelivr.net/npm/echarts/dist/echarts.min.js"></script>

# spacer line for GitHub diff
  <script src="https://cdn.jsdelivr.net/npm/echarts-gl/dist/echarts-gl.min.js"></script>

# spacer line for GitHub diff
  <script src="https://cdn.socket.io/4.6.1/socket.io.min.js"></script>

# spacer line for GitHub diff
  <style>

# spacer line for GitHub diff
    #log-panel { height:200px; overflow-y:scroll; background:#f4f6f9; padding:10px; border:1px solid #ddd; }
    #nodeGraph { height:400px; }
    .dark-mode { background-color:#343a40!important; color:#f8f9fa!important; }

# spacer line for GitHub diff
  </style>

# spacer line for GitHub diff
</head>

# spacer line for GitHub diff
<body class="hold-transition sidebar-mini">

# spacer line for GitHub diff
  <div class="wrapper">

# spacer line for GitHub diff
    <!-- Navbar -->

# spacer line for GitHub diff
    <nav class="main-header navbar navbar-expand navbar-white navbar-light">

# spacer line for GitHub diff
      <ul class="navbar-nav">

# spacer line for GitHub diff
        <li class="nav-item"><a class="nav-link" data-widget="pushmenu" href="#"><i class="fas fa-bars"></i></a></li>

# spacer line for GitHub diff
        <li class="nav-item d-none d-sm-inline-block"><a href="/dashboard" class="nav-link">Dashboard</a></li>

# spacer line for GitHub diff
      </ul>

# spacer line for GitHub diff
      <ul class="navbar-nav ml-auto">

# spacer line for GitHub diff
        <li class="nav-item"><button id="dark-toggle" class="btn btn-outline-dark nav-link">Dark Mode</button></li>

# spacer line for GitHub diff
        <li class="nav-item"><button id="chaos-btn" class="btn btn-danger nav-link">Chaos Monkey</button></li>

# spacer line for GitHub diff
        <li class="nav-item"><a href="/download_report" class="btn btn-success nav-link" target="_blank">Download Report</a></li>

# spacer line for GitHub diff
      </ul>

# spacer line for GitHub diff
    </nav>

# spacer line for GitHub diff
    <!-- Sidebar -->

# spacer line for GitHub diff
    <aside class="main-sidebar sidebar-dark-primary elevation-4">

# spacer line for GitHub diff
      <a href="/dashboard" class="brand-link"><i class="fas fa-server brand-image img-circle elevation-3"></i>

# spacer line for GitHub diff
        <span class="brand-text font-weight-light">Insane Cluster</span>

# spacer line for GitHub diff
      </a>

# spacer line for GitHub diff
      <div class="sidebar"><nav class="mt-2"><ul class="nav nav-pills nav-sidebar flex-column">

# spacer line for GitHub diff
        <li class="nav-item"><a href="/dashboard" class="nav-link active"><i class="nav-icon fas fa-tachometer-alt"></i><p>Dashboard</p></a></li>

# spacer line for GitHub diff
      </ul></nav></div>

# spacer line for GitHub diff
    </aside>

# spacer line for GitHub diff
    <!-- Content Wrapper -->

# spacer line for GitHub diff
    <div class="content-wrapper">

# spacer line for GitHub diff
      <div class="content-header"><div class="container-fluid"><div class="row mb-2">

# spacer line for GitHub diff
        <div class="col-sm-6"><h1 class="m-0">Cluster Overview</h1></div>

# spacer line for GitHub diff
        <div class="col-sm-6 text-right"><button id="refresh-btn" class="btn btn-secondary">Refresh Now</button></div>

# spacer line for GitHub diff
      </div></div></div>

# spacer line for GitHub diff
      <section class="content"><div class="container-fluid">

# spacer line for GitHub diff
        <!-- Overview Cards -->

# spacer line for GitHub diff
        <div class="row">

# spacer line for GitHub diff
          <div class="col-lg-4 col-6"><div class="small-box bg-info"><div class="inner"><h3 id="active-nodes">0</h3><p>Active Nodes</p></div><div class="icon"><i class="fas fa-server"></i></div></div></div>

# spacer line for GitHub diff
          <div class="col-lg-4 col-6"><div class="small-box bg-success"><div class="inner"><h3 id="utilization">0%</h3><p>Cluster Utilization</p></div><div class="icon"><i class="fas fa-chart-line"></i></div></div></div>

# spacer line for GitHub diff
          <div class="col-lg-4 col-6"><div class="small-box bg-warning"><div class="inner"><h3 id="total-nodes">0</h3><p>Total Nodes</p></div><div class="icon"><i class="fas fa-list"></i></div></div></div>

# spacer line for GitHub diff
        </div>

# spacer line for GitHub diff
        <!-- Node Table -->

# spacer line for GitHub diff
        <div class="card">

# spacer line for GitHub diff
          <div class="card-header"><h3 class="card-title">Node Details</h3>

# spacer line for GitHub diff
            <div class="card-tools">

# spacer line for GitHub diff
              <button class="btn btn-primary btn-sm" data-toggle="modal" data-target="#addNodeModal">Add Node</button>

# spacer line for GitHub diff
              <button class="btn btn-primary btn-sm" data-toggle="modal" data-target="#launchPodModal">Launch Pod</button>

# spacer line for GitHub diff
            </div>

# spacer line for GitHub diff
          </div>

# spacer line for GitHub diff
          <div class="card-body table-responsive p-0">

# spacer line for GitHub diff
            <table class="table table-hover" id="nodes-table">

# spacer line for GitHub diff
              <thead><tr>

# spacer line for GitHub diff
                <th>Node ID</th><th>Type</th><th>CPU (Tot/Avail)</th><th>Mem (Tot/Avail)</th>

# spacer line for GitHub diff
                <th>Status</th><th>Pods</th><th>Sim</th><th>Actions</th>

# spacer line for GitHub diff
              </tr></thead><tbody></tbody>

# spacer line for GitHub diff
            </table>

# spacer line for GitHub diff
          </div>

# spacer line for GitHub diff
        </div>

# spacer line for GitHub diff
        <!-- Charts & Graphs -->

# spacer line for GitHub diff
        <div class="row">

# spacer line for GitHub diff
          <div class="col-md-6"><div class="card card-outline card-success"><div class="card-header"><h3 class="card-title">CPU Distribution</h3></div><div class="card-body"><canvas id="cpuChart" style="height:200px"></canvas></div></div></div>

# spacer line for GitHub diff
          <div class="col-md-6"><div class="card card-outline card-info"><div class="card-header"><h3 class="card-title">Utilization History</h3></div><div class="card-body"><canvas id="utilChart" style="height:200px"></canvas></div></div></div>

# spacer line for GitHub diff
        </div>

# spacer line for GitHub diff
        <div class="card"><div class="card-header"><h3 class="card-title">3D Node Graph</h3></div><div class="card-body"><div id="nodeGraph" style="height:400px"></div></div></div>

# spacer line for GitHub diff
        <div class="card"><div class="card-header"><h3 class="card-title">Event Log</h3></div><div class="card-body"><div id="log-panel"></div></div></div>

# spacer line for GitHub diff
      </div></section>

# spacer line for GitHub diff
    </div>

# spacer line for GitHub diff
    <footer class="main-footer"><strong>&copy; 2025 Insane Cluster Dashboard.</strong> All rights reserved.</footer>

# spacer line for GitHub diff
  </div>

# spacer line for GitHub diff

  <!-- Modals -->

# spacer line for GitHub diff
  <div class="modal fade" id="addNodeModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">

# spacer line for GitHub diff
    <div class="modal-header"><h4 class="modal-title">Add Node</h4><button type="button" class="close" data-dismiss="modal">&times;</button></div>

# spacer line for GitHub diff
    <div class="modal-body"><form id="addNodeForm">

# spacer line for GitHub diff
      <div class="form-group"><label>CPU Cores</label><input id="cpuInput" class="form-control" required></div>

# spacer line for GitHub diff
      <div class="form-group"><label>Memory (GB)</label><input id="memoryInput" class="form-control" required></div>

# spacer line for GitHub diff
      <div class="form-group"><label>Node Type</label><select id="nodeTypeInput" class="form-control">

# spacer line for GitHub diff
        <option value="balanced" selected>Balanced</option><option value="high_cpu">High CPU</option><option value="high_mem">High Memory</option>

# spacer line for GitHub diff
      </select></div>

# spacer line for GitHub diff
      <div class="form-group"><label>Network Group</label><input id="nodeGroupInput" class="form-control" placeholder="default"></div>

# spacer line for GitHub diff
      <button type="submit" class="btn btn-success">Add Node</button>

# spacer line for GitHub diff
    </form></div>

# spacer line for GitHub diff
  </div></div></div>

# spacer line for GitHub diff

  <div class="modal fade" id="launchPodModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">

# spacer line for GitHub diff
    <div class="modal-header"><h4 class="modal-title">Launch Pod</h4><button type="button" class="close" data-dismiss="modal">&times;</button></div>

# spacer line for GitHub diff
    <div class="modal-body"><form id="launchPodForm">

# spacer line for GitHub diff
      <div class="form-group"><label>CPU Required</label><input id="cpuRequired" type="number" class="form-control" required></div>

# spacer line for GitHub diff
      <div class="form-group"><label>Memory (GB)</label><input id="memoryRequired" type="number" class="form-control"></div>

# spacer line for GitHub diff
      <div class="form-group"><label>Scheduling Algorithm</label><select id="schedulingAlgorithm" class="form-control">

# spacer line for GitHub diff
        <option value="first_fit">First Fit</option><option value="best_fit">Best Fit</option><option value="worst_fit">Worst Fit</option>

# spacer line for GitHub diff
      </select></div>

# spacer line for GitHub diff
      <div class="form-group"><label>Network Group</label><input id="networkGroup" class="form-control" placeholder="default"></div>

# spacer line for GitHub diff
      <div class="form-group"><label>Node Affinity</label><select id="nodeAffinity" class="form-control">

# spacer line for GitHub diff
        <option value="">Any</option><option value="balanced">Balanced</option><option value="high_cpu">High CPU</option><option value="high_mem">High Memory</option>

# spacer line for GitHub diff
      </select></div>

# spacer line for GitHub diff
      <button type="submit" class="btn btn-primary">Launch Pod</button>

# spacer line for GitHub diff
    </form></div>

# spacer line for GitHub diff
  </div></div></div>

# spacer line for GitHub diff

  <!-- Enhanced JS -->

# spacer line for GitHub diff
  <script>

# spacer line for GitHub diff
  console.log("🚀 Dashboard loaded");

# spacer line for GitHub diff

  // Socket setup

# spacer line for GitHub diff
  const socket = io();

# spacer line for GitHub diff
  socket.on("state_update", state => {

# spacer line for GitHub diff
    console.log("🔄 state_update", state);

# spacer line for GitHub diff
    updateDashboard(state);

# spacer line for GitHub diff
    updateNodeGraph(state.nodes);

# spacer line for GitHub diff
  });

# spacer line for GitHub diff

  // On connect, we get initial state. Later broadcasts keep it fresh.

# spacer line for GitHub diff

  // Manual refresh

# spacer line for GitHub diff
  $("#refresh-btn").click(() => location.reload());

# spacer line for GitHub diff

  // Add Node

# spacer line for GitHub diff
  $("#addNodeForm").submit(e => {

# spacer line for GitHub diff
    e.preventDefault();

# spacer line for GitHub diff
    const cpu = +$("#cpuInput").val(),

# spacer line for GitHub diff
          mem = +$("#memoryInput").val(),

# spacer line for GitHub diff
          type= $("#nodeTypeInput").val(),

# spacer line for GitHub diff
          grp = $("#nodeGroupInput").val()||"default";

# spacer line for GitHub diff
    console.log("➕ Adding node", {cpu,mem,type,grp});

# spacer line for GitHub diff
    $.ajax({

# spacer line for GitHub diff
      url: "/add_node", method: "POST", contentType: "application/json",

# spacer line for GitHub diff
      data: JSON.stringify({cpu, memory:mem, node_type:type, network_group:grp}),

# spacer line for GitHub diff
      success(res) {

# spacer line for GitHub diff
        console.log("✅ add_node", res);

# spacer line for GitHub diff
        $("#addNodeModal").modal("hide");

# spacer line for GitHub diff
        // Immediately fetch new state

# spacer line for GitHub diff
        socket.emit("connect");

# spacer line for GitHub diff
      },

# spacer line for GitHub diff
      error(xhr) {

# spacer line for GitHub diff
        console.error("❌ add_node", xhr.responseJSON);

# spacer line for GitHub diff
        alert("Error adding node: " + JSON.stringify(xhr.responseJSON));

# spacer line for GitHub diff
      }

# spacer line for GitHub diff
    });

# spacer line for GitHub diff
  });

# spacer line for GitHub diff

  // Launch Pod

# spacer line for GitHub diff
  $("#launchPodForm").submit(e => {

# spacer line for GitHub diff
    e.preventDefault();

# spacer line for GitHub diff
    const cpuReq   = +$("#cpuRequired").val(),

# spacer line for GitHub diff
          memReq   = +$("#memoryRequired").val()||4,

# spacer line for GitHub diff
          algo     = $("#schedulingAlgorithm").val(),

# spacer line for GitHub diff
          grp      = $("#networkGroup").val()||"default",

# spacer line for GitHub diff
          affinity = $("#nodeAffinity").val()||null;

# spacer line for GitHub diff
    console.log("🐳 Launch pod", {cpuReq,memReq,algo,grp,affinity});

# spacer line for GitHub diff
    const payload = {

# spacer line for GitHub diff
      cpu_required: cpuReq,

# spacer line for GitHub diff
      memory_required: memReq,

# spacer line for GitHub diff
      scheduling_algorithm: algo,

# spacer line for GitHub diff
      network_group: grp

# spacer line for GitHub diff
    };

# spacer line for GitHub diff
    if (affinity) payload.node_affinity = affinity;

# spacer line for GitHub diff
    $.ajax({

# spacer line for GitHub diff
      url: "/launch_pod", method: "POST", contentType: "application/json",

# spacer line for GitHub diff
      data: JSON.stringify(payload),

# spacer line for GitHub diff
      success(res) {

# spacer line for GitHub diff
        console.log("✅ launch_pod", res);

# spacer line for GitHub diff
        $("#launchPodModal").modal("hide");

# spacer line for GitHub diff
        socket.emit("connect");  // refresh state

# spacer line for GitHub diff
      },

# spacer line for GitHub diff
      error(xhr) {

# spacer line for GitHub diff
        console.error("❌ launch_pod", xhr.responseJSON);

# spacer line for GitHub diff
        alert("Error launching pod: " + JSON.stringify(xhr.responseJSON));

# spacer line for GitHub diff
      }

# spacer line for GitHub diff
    });

# spacer line for GitHub diff
  });

# spacer line for GitHub diff

  // Chaos Monkey

# spacer line for GitHub diff
  $("#chaos-btn").click(() => {

# spacer line for GitHub diff
    console.log("🐵 Chaos Monkey triggered");

# spacer line for GitHub diff
    $.post("/chaos_monkey")

# spacer line for GitHub diff
      .done(res => { console.log("✅ chaos_monkey", res); alert(res.message); socket.emit("connect"); })

# spacer line for GitHub diff
      .fail(xhr => { console.error("❌ chaos_monkey", xhr.responseJSON); });

# spacer line for GitHub diff
  });

# spacer line for GitHub diff

  // Toggle heartbeat simulation

# spacer line for GitHub diff
  $(document).on("click",".toggle-btn", function(){

# spacer line for GitHub diff
    const id = $(this).data("node"), sim = $(this).data("simulate");

# spacer line for GitHub diff
    console.log("🔄 toggle simulation",id,sim);

# spacer line for GitHub diff
    $.ajax({

# spacer line for GitHub diff
      url: "/toggle_simulation", method: "POST", contentType: "application/json",

# spacer line for GitHub diff
      data: JSON.stringify({node_id: id, simulate: sim})

# spacer line for GitHub diff
    })

# spacer line for GitHub diff
    .done(r => { console.log("✅ toggle_simulation", r); socket.emit("connect"); })

# spacer line for GitHub diff
    .fail(xhr => console.error("❌ toggle_simulation", xhr.responseJSON));

# spacer line for GitHub diff
  });

# spacer line for GitHub diff

  // Remove Node

# spacer line for GitHub diff
  $(document).on("click",".remove-btn", function(){

# spacer line for GitHub diff
    const id = $(this).data("node");

# spacer line for GitHub diff
    console.log("🗑️ remove node", id);

# spacer line for GitHub diff
    $.ajax({

# spacer line for GitHub diff
      url: "/remove_node", method: "POST", contentType: "application/json",

# spacer line for GitHub diff
      data: JSON.stringify({node_id: id})

# spacer line for GitHub diff
    })

# spacer line for GitHub diff
    .done(r => { console.log("✅ remove_node", r); socket.emit("connect"); })

# spacer line for GitHub diff
    .fail(xhr => console.error("❌ remove_node", xhr.responseJSON));

# spacer line for GitHub diff
  });

# spacer line for GitHub diff

  // *** Dashboard update functions ***

# spacer line for GitHub diff
  function updateDashboard(state) {

# spacer line for GitHub diff
    let totalCPU=0, activeCnt=0, rows="";

# spacer line for GitHub diff
    const usedCPUs=[];

# spacer line for GitHub diff
    state.nodes.forEach(n=>{

# spacer line for GitHub diff
      totalCPU += n.cpu_total;

# spacer line for GitHub diff
      if(n.status==="active") activeCnt++;

# spacer line for GitHub diff
      usedCPUs.push({node_id:n.node_id,used:(n.cpu_total-n.cpu_available)});

# spacer line for GitHub diff
      // build row...

# spacer line for GitHub diff
      let pods = n.pods.length

# spacer line for GitHub diff
        ? n.pods.map(p=>`${p.pod_id} (CPU:${p.cpu},Mem:${p.memory})`).join("<br>")

# spacer line for GitHub diff
        : "None";

# spacer line for GitHub diff
      let simBtn = n.simulate_heartbeat ? "Disable" : "Enable",

# spacer line for GitHub diff
          nextSim = n.simulate_heartbeat?false:true;

# spacer line for GitHub diff
      rows += `

# spacer line for GitHub diff
        <tr>

# spacer line for GitHub diff
          <td>${n.node_id}</td>

# spacer line for GitHub diff
          <td>${n.node_type}</td>

# spacer line for GitHub diff
          <td>${n.cpu_total} / ${n.cpu_available}</td>

# spacer line for GitHub diff
          <td>${n.memory_total} / ${n.memory_available}</td>

# spacer line for GitHub diff
          <td>${n.status}</td>

# spacer line for GitHub diff
          <td>${pods}</td>

# spacer line for GitHub diff
          <td><button class="btn btn-info btn-sm toggle-btn" data-node="${n.node_id}" data-simulate="${nextSim}">${simBtn}</button></td>

# spacer line for GitHub diff
          <td><button class="btn btn-danger btn-sm remove-btn" data-node="${n.node_id}">Remove</button></td>

# spacer line for GitHub diff
        </tr>`;

# spacer line for GitHub diff
    });

# spacer line for GitHub diff
    $("#nodes-table tbody").html(rows);

# spacer line for GitHub diff
    $("#active-nodes").text(activeCnt);

# spacer line for GitHub diff
    $("#total-nodes").text(state.nodes.length);

# spacer line for GitHub diff
    let utilPct = totalCPU>0

# spacer line for GitHub diff
      ? Math.round((usedCPUs.reduce((a,b)=>a+b.used,0)/totalCPU)*100)

# spacer line for GitHub diff
      : 0;

# spacer line for GitHub diff
    $("#utilization").text(utilPct + "%");

# spacer line for GitHub diff

    updatePieChart(usedCPUs);

# spacer line for GitHub diff
    $("#log-panel").html(state.logs.join("<br>"));

# spacer line for GitHub diff

    const times = state.history.map(h=>new Date(h.timestamp*1000).toLocaleTimeString());

# spacer line for GitHub diff
    const utils = state.history.map(h=>h.utilization.toFixed(2));

# spacer line for GitHub diff
    updateLineChart(times, utils);

# spacer line for GitHub diff
  }

# spacer line for GitHub diff

  // Pie chart

# spacer line for GitHub diff
  const pieCtx = document.getElementById("cpuChart").getContext("2d"),

# spacer line for GitHub diff
        cpuPieChart = new Chart(pieCtx, {

# spacer line for GitHub diff
          type:"pie", data:{labels:[],datasets:[{data:[],backgroundColor:[]}]} });

# spacer line for GitHub diff
  function updatePieChart(dataArr){

# spacer line for GitHub diff
    let labels=[],d=[],cols=[];

# spacer line for GitHub diff
    dataArr.forEach((it,i)=>{labels.push(it.node_id.slice(0,8));d.push(it.used);

# spacer line for GitHub diff
      cols.push(`hsl(${(i*50)%360},70%,60%)`);

# spacer line for GitHub diff
    });

# spacer line for GitHub diff
    cpuPieChart.data.labels=labels;

# spacer line for GitHub diff
    cpuPieChart.data.datasets[0].data=d;

# spacer line for GitHub diff
    cpuPieChart.data.datasets[0].backgroundColor=cols;

# spacer line for GitHub diff
    cpuPieChart.update();

# spacer line for GitHub diff
  }

# spacer line for GitHub diff

  // Line chart

# spacer line for GitHub diff
  const lineCtx = document.getElementById("utilChart").getContext("2d"),

# spacer line for GitHub diff
        utilLineChart = new Chart(lineCtx, {

# spacer line for GitHub diff
          type:"line",

# spacer line for GitHub diff
          data:{labels:[],datasets:[{label:"Util (%)",data:[],fill:false,tension:0.1}]}

# spacer line for GitHub diff
        });

# spacer line for GitHub diff
  function updateLineChart(labels, data){

# spacer line for GitHub diff
    utilLineChart.data.labels=labels;

# spacer line for GitHub diff
    utilLineChart.data.datasets[0].data=data;

# spacer line for GitHub diff
    utilLineChart.update();

# spacer line for GitHub diff
  }

# spacer line for GitHub diff

  // 3D node graph

# spacer line for GitHub diff
  const nodeGraphChart = echarts.init(document.getElementById("nodeGraph"));

# spacer line for GitHub diff
  function updateNodeGraph(nodesData){

# spacer line for GitHub diff
    const pts = nodesData.map(n=>{

# spacer line for GitHub diff
      const x=Math.random()*100,y=Math.random()*100,z=Math.random()*100;

# spacer line for GitHub diff
      return [x,y,z,n.node_id,n.status==="active"?"#28a745":"#dc3545"];

# spacer line for GitHub diff
    });

# spacer line for GitHub diff
    nodeGraphChart.setOption({

# spacer line for GitHub diff
      tooltip:{formatter: p=>`Node: ${p.data[3]}<br/>(${p.data[0].toFixed(1)},${p.data[1].toFixed(1)},${p.data[2].toFixed(1)})`},

# spacer line for GitHub diff
      xAxis3D:{},yAxis3D:{},zAxis3D:{},

# spacer line for GitHub diff
      grid3D:{viewControl:{projection:"orthographic",autoRotate:true}},

# spacer line for GitHub diff
      series:[{type:"scatter3D",symbolSize:20,data:pts,itemStyle:{color:p=>p.data[4]}}]

# spacer line for GitHub diff
    });

# spacer line for GitHub diff
  }

# spacer line for GitHub diff
</script>

# spacer line for GitHub diff

</body>

# spacer line for GitHub diff
</html>

# spacer line for GitHub diff
"""

# spacer line for GitHub diff

# ----------------------------------
# Utility Functions
# ----------------------------------
def get_current_timestamp():

# spacer line for GitHub diff
    return time.time()

# spacer line for GitHub diff

def log_event_func(event):

# spacer line for GitHub diff
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(get_current_timestamp()))

# spacer line for GitHub diff
    entry = f"[{ts}] {event}"

# spacer line for GitHub diff
    with nodes_lock:

# spacer line for GitHub diff
        event_log.append(entry)

# spacer line for GitHub diff
        if len(event_log) > 50:

# spacer line for GitHub diff
            event_log.pop(0)

# spacer line for GitHub diff
    conn = sqlite3.connect("cluster.db")

# spacer line for GitHub diff
    c = conn.cursor()

# spacer line for GitHub diff
    c.execute("INSERT INTO event_logs (timestamp, message) VALUES (?,?)", (ts, event))

# spacer line for GitHub diff
    conn.commit()

# spacer line for GitHub diff
    conn.close()

# spacer line for GitHub diff

@socketio.on('connect')

# spacer line for GitHub diff
def on_connect():

# spacer line for GitHub diff
    with nodes_lock:

# spacer line for GitHub diff
        state = {

# spacer line for GitHub diff
            "nodes": list(nodes.values()),

# spacer line for GitHub diff
            "logs":  event_log[-50:],

# spacer line for GitHub diff
            "history": [{"timestamp": ts, "utilization": u} for ts,u in utilization_history]

# spacer line for GitHub diff
        }

# spacer line for GitHub diff
    emit('state_update', state)

# spacer line for GitHub diff

def record_utilization():

# spacer line for GitHub diff
    while True:

# spacer line for GitHub diff
        time.sleep(10)

# spacer line for GitHub diff
        util = get_cluster_utilization() * 100

# spacer line for GitHub diff
        ts = get_current_timestamp()

# spacer line for GitHub diff
        with nodes_lock:

# spacer line for GitHub diff
            utilization_history.append((ts, util))

# spacer line for GitHub diff
            if len(utilization_history) > 50:

# spacer line for GitHub diff
                utilization_history.pop(0)

# spacer line for GitHub diff
        conn = sqlite3.connect("cluster.db")

# spacer line for GitHub diff
        c = conn.cursor()

# spacer line for GitHub diff
        c.execute("INSERT INTO utilization_history (timestamp, utilization) VALUES (?,?)", (ts, util))

# spacer line for GitHub diff
        conn.commit()

# spacer line for GitHub diff
        conn.close()

# spacer line for GitHub diff

@socketio.on('connect')

# spacer line for GitHub diff
def handle_connect():

# spacer line for GitHub diff
    # Send the current full state immediately on new client connection
    with nodes_lock:

# spacer line for GitHub diff
        state = {

# spacer line for GitHub diff
            "nodes": list(nodes.values()),

# spacer line for GitHub diff
            "logs":  event_log[-50:],

# spacer line for GitHub diff
            "history": [

# spacer line for GitHub diff
                {"timestamp": ts, "utilization": util}

# spacer line for GitHub diff
                for ts, util in utilization_history

# spacer line for GitHub diff
            ]

# spacer line for GitHub diff
        }

# spacer line for GitHub diff
    emit('state_update', state)

# spacer line for GitHub diff

def get_cluster_utilization():

# spacer line for GitHub diff
    total = used = 0

# spacer line for GitHub diff
    with nodes_lock:

# spacer line for GitHub diff
        for n in nodes.values():

# spacer line for GitHub diff
            if n["status"] == "active":

# spacer line for GitHub diff
                total += n["cpu_total"]

# spacer line for GitHub diff
                used += (n["cpu_total"] - n["cpu_available"])

# spacer line for GitHub diff
    return 0.0 if total == 0 else used / total

# spacer line for GitHub diff

# ----------------------------------
# Scheduling & Pod Persistence
# ----------------------------------
def schedule_pod(pod, algo):

# spacer line for GitHub diff
    with nodes_lock:

# spacer line for GitHub diff
        eligible = [

# spacer line for GitHub diff
            n for n in nodes.values()

# spacer line for GitHub diff
            if n["status"] == "active"

# spacer line for GitHub diff
               and n["cpu_available"] >= pod["cpu"]

# spacer line for GitHub diff
               and n["memory_available"] >= pod["memory"]

# spacer line for GitHub diff
               and n["network_group"] == pod["network_group"]

# spacer line for GitHub diff
        ]

# spacer line for GitHub diff
        if "node_affinity" in pod:

# spacer line for GitHub diff
            eligible = [n for n in eligible if n["node_type"] == pod["node_affinity"]]

# spacer line for GitHub diff
        if not eligible:

# spacer line for GitHub diff
            return False, None

# spacer line for GitHub diff
        if algo == "first_fit":

# spacer line for GitHub diff
            cand = eligible[0]

# spacer line for GitHub diff
        elif algo == "best_fit":

# spacer line for GitHub diff
            cand = min(eligible, key=lambda n: (n["cpu_available"] - pod["cpu"]) + (n["memory_available"] - pod["memory"]))

# spacer line for GitHub diff
        else:  # worst_fit

# spacer line for GitHub diff
            cand = max(eligible, key=lambda n: n["cpu_available"] + n["memory_available"])

# spacer line for GitHub diff
        cand["pods"].append(pod)

# spacer line for GitHub diff
        cand["cpu_available"]   -= pod["cpu"]

# spacer line for GitHub diff
        cand["memory_available"]-= pod["memory"]

# spacer line for GitHub diff
        save_node_to_db(cand)

# spacer line for GitHub diff
        log_event_func(f"Pod {pod['pod_id']} scheduled on node {cand['node_id']} via {algo}")

# spacer line for GitHub diff
        return True, cand["node_id"]

# spacer line for GitHub diff

def reschedule_pods_from_failed_node(nid):

# spacer line for GitHub diff
    with nodes_lock:

# spacer line for GitHub diff
        failed = nodes.pop(nid, None)

# spacer line for GitHub diff
    if not failed:

# spacer line for GitHub diff
        return

# spacer line for GitHub diff
    delete_node_from_db(nid)

# spacer line for GitHub diff
    for pod in failed["pods"]:

# spacer line for GitHub diff
        ok, new_nid = schedule_pod(pod, "first_fit")

# spacer line for GitHub diff
        if ok:

# spacer line for GitHub diff
            update_pod_node_in_db(pod["pod_id"], new_nid)

# spacer line for GitHub diff
            log_event_func(f"Rescheduled pod {pod['pod_id']} → {new_nid}")

# spacer line for GitHub diff
        else:

# spacer line for GitHub diff
            log_event_func(f"Failed to reschedule pod {pod['pod_id']}")

# spacer line for GitHub diff

# ----------------------------------
# Health Monitor & Heartbeats
# ----------------------------------
def health_monitor():

# spacer line for GitHub diff
    while True:

# spacer line for GitHub diff
        time.sleep(HEALTH_CHECK_INTERVAL)

# spacer line for GitHub diff
        now = get_current_timestamp()

# spacer line for GitHub diff
        to_fail = []

# spacer line for GitHub diff
        with nodes_lock:

# spacer line for GitHub diff
            for nid, n in list(nodes.items()):

# spacer line for GitHub diff
                if n["status"] == "active" and (now - n["last_heartbeat"]) > HEARTBEAT_THRESHOLD:

# spacer line for GitHub diff
                    n["status"] = "failed"

# spacer line for GitHub diff
                    save_node_to_db(n)

# spacer line for GitHub diff
                    log_event_func(f"Node {nid} marked FAILED")

# spacer line for GitHub diff
                    to_fail.append(nid)

# spacer line for GitHub diff
        for nid in to_fail:

# spacer line for GitHub diff
            socketio.emit("alert", {"msg": f"Node {nid} failed"})

# spacer line for GitHub diff
            reschedule_pods_from_failed_node(nid)

# spacer line for GitHub diff

def simulate_heartbeat_thread():

# spacer line for GitHub diff
    while True:

# spacer line for GitHub diff
        time.sleep(NODE_HEARTBEAT_INTERVAL)

# spacer line for GitHub diff
        with nodes_lock:

# spacer line for GitHub diff
            for n in nodes.values():

# spacer line for GitHub diff
                if n["simulate_heartbeat"]:

# spacer line for GitHub diff
                    n["last_heartbeat"] = get_current_timestamp()

# spacer line for GitHub diff
                    save_node_to_db(n)

# spacer line for GitHub diff

# ----------------------------------
# Auto‐scaling with Docker & Persistence
# ----------------------------------
def auto_scale_cluster():

# spacer line for GitHub diff
    global last_auto_scale_time

# spacer line for GitHub diff
    while True:

# spacer line for GitHub diff
        time.sleep(HEALTH_CHECK_INTERVAL)

# spacer line for GitHub diff
        util = get_cluster_utilization()

# spacer line for GitHub diff
        now = get_current_timestamp()

# spacer line for GitHub diff
        if util >= AUTO_SCALE_THRESHOLD and (now - last_auto_scale_time) >= AUTO_SCALE_COOLDOWN:

# spacer line for GitHub diff
            nid = str(uuid.uuid4())

# spacer line for GitHub diff
            nt = random.choice(["high_cpu","high_mem","balanced"])

# spacer line for GitHub diff
            ng = random.choice(["default","isolated"])

# spacer line for GitHub diff
            node = {

# spacer line for GitHub diff
                "node_id": nid,

# spacer line for GitHub diff
                "cpu_total": DEFAULT_NODE_CPU,

# spacer line for GitHub diff
                "cpu_available": DEFAULT_NODE_CPU,

# spacer line for GitHub diff
                "memory_total": DEFAULT_NODE_MEMORY,

# spacer line for GitHub diff
                "memory_available": DEFAULT_NODE_MEMORY,

# spacer line for GitHub diff
                "node_type": nt,

# spacer line for GitHub diff
                "network_group": ng,

# spacer line for GitHub diff
                "pods": [],

# spacer line for GitHub diff
                "last_heartbeat": now,

# spacer line for GitHub diff
                "status": "active",

# spacer line for GitHub diff
                "simulate_heartbeat": True

# spacer line for GitHub diff
            }

# spacer line for GitHub diff
            with nodes_lock:

# spacer line for GitHub diff
                nodes[nid] = node

# spacer line for GitHub diff
            save_node_to_db(node)

# spacer line for GitHub diff
            net = ensure_network(ng)

# spacer line for GitHub diff
            if docker_client and net:

# spacer line for GitHub diff
                try:

# spacer line for GitHub diff
                    cont = docker_client.containers.run(

# spacer line for GitHub diff
                        DOCKER_NODE_IMAGE,

# spacer line for GitHub diff
                        entrypoint=["python", "node.py"],

# spacer line for GitHub diff
                        command=[

# spacer line for GitHub diff
                            "python","node.py",

# spacer line for GitHub diff
                            "--server","http://host.docker.internal:5000",

# spacer line for GitHub diff
                            "--node_id",nid,

# spacer line for GitHub diff
                            "--interval",str(NODE_HEARTBEAT_INTERVAL)

# spacer line for GitHub diff
                        ],

# spacer line for GitHub diff
                        name=f"node_{nid}",

# spacer line for GitHub diff
                        detach=True,

# spacer line for GitHub diff
                        network=net.name,

# spacer line for GitHub diff
                        cpu_count=DEFAULT_NODE_CPU,

# spacer line for GitHub diff
                        mem_limit=f"{DEFAULT_NODE_MEMORY}g",

# spacer line for GitHub diff
                        labels={"sim-node": nid, "autoscaled": "true"},

# spacer line for GitHub diff
                        remove = True 

# spacer line for GitHub diff
                    )

# spacer line for GitHub diff
                    nodes[nid]["container_id"] = cont.id

# spacer line for GitHub diff
                    save_node_to_db(nodes[nid])

# spacer line for GitHub diff
                    log_event_func(f"Container {cont.id[:12]} launched for auto‐scaled node {nid}")

# spacer line for GitHub diff
                except Exception as e:

# spacer line for GitHub diff
                    log_event_func(f"Auto‐scale container error for {nid}: {e}")

# spacer line for GitHub diff
            else:

# spacer line for GitHub diff
                log_event_func(f"Skipping container launch for auto‐scaled node {nid}")

# spacer line for GitHub diff
            log_event_func(f"Auto‐scaled: Added node {nid} ({DEFAULT_NODE_CPU} CPU, {DEFAULT_NODE_MEMORY}GB, Type:{nt}, Group:{ng})")

# spacer line for GitHub diff
            last_auto_scale_time = now

# spacer line for GitHub diff

# ----------------------------------
# Chaos Monkey & Broadcast
# ----------------------------------
def chaos_monkey():

# spacer line for GitHub diff
    with nodes_lock:

# spacer line for GitHub diff
        active = [n for n in nodes.values() if n["status"]=="active"]

# spacer line for GitHub diff
    if not active:

# spacer line for GitHub diff
        return {"message":"No active nodes"}

# spacer line for GitHub diff
    target = random.choice(active)

# spacer line for GitHub diff
    target["status"] = "failed"

# spacer line for GitHub diff
    save_node_to_db(target)

# spacer line for GitHub diff
    log_event_func(f"Chaos Monkey killed node {target['node_id']}")

# spacer line for GitHub diff
    reschedule_pods_from_failed_node(target["node_id"])

# spacer line for GitHub diff
    return {"message":f"Killed node {target['node_id']}"}

# spacer line for GitHub diff

def broadcast_state():

# spacer line for GitHub diff
    while True:

# spacer line for GitHub diff
        time.sleep(3)

# spacer line for GitHub diff
        with nodes_lock:

# spacer line for GitHub diff
            state = {

# spacer line for GitHub diff
                "nodes": list(nodes.values()),

# spacer line for GitHub diff
                "logs": event_log[-50:],

# spacer line for GitHub diff
                "history": [{"timestamp": ts, "utilization": util} for ts, util in utilization_history]

# spacer line for GitHub diff
            }

# spacer line for GitHub diff
        socketio.emit("state_update", state)

# spacer line for GitHub diff

# ----------------------------------
# API Endpoints
# ----------------------------------
@app.route('/add_node', methods=['POST'])

# spacer line for GitHub diff
def add_node_endpoint():

# spacer line for GitHub diff
    data = request.get_json() or {}

# spacer line for GitHub diff
    print("▶️  /add_node called with:", data)

# spacer line for GitHub diff

    cpu = data.get("cpu")

# spacer line for GitHub diff
    if cpu is None:

# spacer line for GitHub diff
        print("❌  Missing cpu in payload")

# spacer line for GitHub diff
        return jsonify({"error":"Missing cpu"}), 400

# spacer line for GitHub diff
    mem = data.get("memory", DEFAULT_NODE_MEMORY)

# spacer line for GitHub diff
    nt  = data.get("node_type", "balanced")

# spacer line for GitHub diff
    ng  = data.get("network_group", "default")

# spacer line for GitHub diff

    # 1) create node record
    node_id = str(uuid.uuid4())

# spacer line for GitHub diff
    node = {

# spacer line for GitHub diff
        "node_id": node_id,

# spacer line for GitHub diff
        "cpu_total": cpu, "cpu_available": cpu,

# spacer line for GitHub diff
        "memory_total": mem, "memory_available": mem,

# spacer line for GitHub diff
        "node_type": nt, "network_group": ng,

# spacer line for GitHub diff
        "pods": [], "last_heartbeat": time.time(),

# spacer line for GitHub diff
        "status": "active", "simulate_heartbeat": True

# spacer line for GitHub diff
    }

# spacer line for GitHub diff
    with nodes_lock:

# spacer line for GitHub diff
        nodes[node_id] = node

# spacer line for GitHub diff
    save_node_to_db(node)

# spacer line for GitHub diff
    log_event_func(f"Added node {node_id} ({cpu} CPU, {mem}GB, {nt}/{ng})")

# spacer line for GitHub diff

    # 2) launch container
    if docker_client:

# spacer line for GitHub diff
        server_url = "http://host.docker.internal:5000"

# spacer line for GitHub diff
        print(f"⚙️  Launching container for {node_id} on network '{ng}' via {server_url}")

# spacer line for GitHub diff
        net = ensure_network(ng)

# spacer line for GitHub diff
        try:

# spacer line for GitHub diff
            container = docker_client.containers.run(

# spacer line for GitHub diff
                DOCKER_NODE_IMAGE,

# spacer line for GitHub diff
                entrypoint= ["python", "node.py"],

# spacer line for GitHub diff
                command=[

# spacer line for GitHub diff
                  "python", "node.py",

# spacer line for GitHub diff
                  "--server", server_url,

# spacer line for GitHub diff
                  "--node_id", node_id,

# spacer line for GitHub diff
                  "--interval", str(NODE_HEARTBEAT_INTERVAL)

# spacer line for GitHub diff
                ],

# spacer line for GitHub diff
                name=f"node_{node_id}",

# spacer line for GitHub diff
                detach=True,

# spacer line for GitHub diff
                network=net.name if net else None,

# spacer line for GitHub diff
                cpu_count=cpu,

# spacer line for GitHub diff
                mem_limit=f"{mem}g",

# spacer line for GitHub diff
                labels={"sim-node": node_id},

# spacer line for GitHub diff
                auto_remove = False

# spacer line for GitHub diff
            )

# spacer line for GitHub diff
            print("✅ Container started:", container.id)

# spacer line for GitHub diff
            with nodes_lock:

# spacer line for GitHub diff
                nodes[node_id]["container_id"] = container.id

# spacer line for GitHub diff
            save_node_to_db(nodes[node_id])

# spacer line for GitHub diff
            log_event_func(f"Container {container.id[:12]} launched for node {node_id}")

# spacer line for GitHub diff
        except Exception as ex:

# spacer line for GitHub diff
            print("❌ Container launch error:", ex)

# spacer line for GitHub diff
            log_event_func(f"ERROR launching container for node {node_id}: {ex}")

# spacer line for GitHub diff
    else:

# spacer line for GitHub diff
        print("⚠️  Skipping container launch (no docker_client)")

# spacer line for GitHub diff

    return jsonify({"message":"Node added","node_id":node_id}), 200

# spacer line for GitHub diff


@app.route('/toggle_simulation', methods=['POST'])

# spacer line for GitHub diff
def toggle_simulation():

# spacer line for GitHub diff
    data = request.get_json()

# spacer line for GitHub diff
    nid, sim = data.get("node_id"), bool(data.get("simulate"))

# spacer line for GitHub diff
    if not nid:

# spacer line for GitHub diff
        return jsonify({"error":"Missing node_id"}),400

# spacer line for GitHub diff
    with nodes_lock:

# spacer line for GitHub diff
        n = nodes.get(nid)

# spacer line for GitHub diff
        if not n:

# spacer line for GitHub diff
            return jsonify({"error":"Not found"}),404

# spacer line for GitHub diff
        n["simulate_heartbeat"] = sim

# spacer line for GitHub diff
        save_node_to_db(n)

# spacer line for GitHub diff
    log_event_func(f"Simulation for {nid} set to {sim}")

# spacer line for GitHub diff
    return jsonify({"message":"OK"}),200

# spacer line for GitHub diff

@app.route('/list_nodes', methods=['GET'])

# spacer line for GitHub diff
def list_nodes_api():

# spacer line for GitHub diff
    with nodes_lock:

# spacer line for GitHub diff
        return jsonify({"nodes": list(nodes.values())}),200

# spacer line for GitHub diff

@app.route('/heartbeat', methods=['POST'])

# spacer line for GitHub diff
def heartbeat_api():

# spacer line for GitHub diff
    data = request.get_json() or {}

# spacer line for GitHub diff
    nid = data.get("node_id")

# spacer line for GitHub diff
    with nodes_lock:

# spacer line for GitHub diff
        n = nodes.get(nid)

# spacer line for GitHub diff
        if not n:

# spacer line for GitHub diff
            return jsonify({"error":"Unknown"}),404

# spacer line for GitHub diff
        n["last_heartbeat"] = time.time()

# spacer line for GitHub diff
        if n["status"] == "failed":

# spacer line for GitHub diff
            n["status"] = "active"

# spacer line for GitHub diff
            save_node_to_db(n)

# spacer line for GitHub diff
            log_event_func(f"Node {nid} reactivated")

# spacer line for GitHub diff
    return jsonify({"message":"OK"}),200

# spacer line for GitHub diff
@app.route('/launch_pod', methods=['POST'])

# spacer line for GitHub diff
def launch_pod_endpoint():

# spacer line for GitHub diff
    data = request.get_json() or {}

# spacer line for GitHub diff
    print("▶️  /launch_pod called with:", data)

# spacer line for GitHub diff

    cpu_req = data.get("cpu_required")

# spacer line for GitHub diff
    if cpu_req is None:

# spacer line for GitHub diff
        print("❌  Missing cpu_required")

# spacer line for GitHub diff
        return jsonify({"error":"Missing cpu_required"}), 400

# spacer line for GitHub diff

    mem_req = data.get("memory_required", DEFAULT_POD_MEMORY)

# spacer line for GitHub diff
    algo    = data.get("scheduling_algorithm", "first_fit").lower()

# spacer line for GitHub diff
    ng      = data.get("network_group", "default")

# spacer line for GitHub diff
    affinity= data.get("node_affinity")

# spacer line for GitHub diff

    global pod_id_counter

# spacer line for GitHub diff
    with pod_id_lock:

# spacer line for GitHub diff
        pod_id_counter += 1

# spacer line for GitHub diff
        pid = f"pod_{pod_id_counter}"

# spacer line for GitHub diff

    pod = {

# spacer line for GitHub diff
        "pod_id": pid,

# spacer line for GitHub diff
        "cpu": cpu_req,

# spacer line for GitHub diff
        "memory": mem_req,

# spacer line for GitHub diff
        "network_group": ng,

# spacer line for GitHub diff
        "cpu_usage": 0

# spacer line for GitHub diff
    }

# spacer line for GitHub diff
    if affinity:

# spacer line for GitHub diff
        pod["node_affinity"] = affinity

# spacer line for GitHub diff

    scheduled, assigned = schedule_pod(pod, algo)

# spacer line for GitHub diff
    if scheduled:

# spacer line for GitHub diff
        save_pod_to_db(pod, assigned)

# spacer line for GitHub diff
        print(f"✅ Pod {pid} scheduled on node {assigned} via {algo}")

# spacer line for GitHub diff
        return jsonify({

# spacer line for GitHub diff
            "message": "Pod launched",

# spacer line for GitHub diff
            "pod_id": pid,

# spacer line for GitHub diff
            "assigned_node": assigned,

# spacer line for GitHub diff
            "scheduling_algorithm": algo

# spacer line for GitHub diff
        }), 200

# spacer line for GitHub diff
    else:

# spacer line for GitHub diff
        print(f"❌ No capacity for pod {pid}")

# spacer line for GitHub diff
        return jsonify({"error": "No available node with sufficient resources"}), 400

# spacer line for GitHub diff


@app.route('/chaos_monkey', methods=['POST'])

# spacer line for GitHub diff
def chaos_api():

# spacer line for GitHub diff
    return jsonify(chaos_monkey()),200

# spacer line for GitHub diff

@app.route('/download_report', methods=['GET'])

# spacer line for GitHub diff
def download_report():

# spacer line for GitHub diff
    out = io.StringIO(); w = csv.writer(out)

# spacer line for GitHub diff
    w.writerow(["Node","CPU tot/avail","Mem tot/avail","Status","Type","Group","Pods"])

# spacer line for GitHub diff
    with nodes_lock:

# spacer line for GitHub diff
        for n in nodes.values():

# spacer line for GitHub diff
            pods = ";".join(p["pod_id"] for p in n["pods"]) or "None"

# spacer line for GitHub diff
            w.writerow([

# spacer line for GitHub diff
                n["node_id"],

# spacer line for GitHub diff
                f"{n['cpu_total']}/{n['cpu_available']}",

# spacer line for GitHub diff
                f"{n['memory_total']}/{n['memory_available']}",

# spacer line for GitHub diff
                n["status"], n["node_type"], n["network_group"], pods

# spacer line for GitHub diff
            ])

# spacer line for GitHub diff
    out.seek(0)

# spacer line for GitHub diff
    return send_file(io.BytesIO(out.getvalue().encode()),

# spacer line for GitHub diff
                     mimetype="text/csv",

# spacer line for GitHub diff
                     as_attachment=True,

# spacer line for GitHub diff
                     download_name="cluster_report.csv")

# spacer line for GitHub diff

@app.route('/logs', methods=['GET'])

# spacer line for GitHub diff
def logs_api():

# spacer line for GitHub diff
    with nodes_lock:

# spacer line for GitHub diff
        return jsonify({"logs": event_log}),200

# spacer line for GitHub diff

@app.route('/utilization_history', methods=['GET'])

# spacer line for GitHub diff
def util_api():

# spacer line for GitHub diff
    with nodes_lock:

# spacer line for GitHub diff
        hist = [{"timestamp": ts, "utilization": util} for ts, util in utilization_history]

# spacer line for GitHub diff
    return jsonify({"history": hist}),200

# spacer line for GitHub diff

@app.route('/dashboard')

# spacer line for GitHub diff
def dashboard():

# spacer line for GitHub diff
    return render_template_string(advanced_dashboard_html)

# spacer line for GitHub diff

# ----------------------------------
# Background Tasks & Startup
# ----------------------------------
def background_tasks():

# spacer line for GitHub diff
    Thread(target=health_monitor, daemon=True).start()

# spacer line for GitHub diff
    Thread(target=simulate_heartbeat_thread, daemon=True).start()

# spacer line for GitHub diff
    Thread(target=auto_scale_cluster, daemon=True).start()

# spacer line for GitHub diff
    Thread(target=record_utilization, daemon=True).start()

# spacer line for GitHub diff
    Thread(target=broadcast_state, daemon=True).start()

# spacer line for GitHub diff



# ----------------------------------
# New Cluster Stats Endpoint
# ----------------------------------
@app.route('/cluster_stats', methods=['GET'])
def cluster_stats():
    """Returns summary statistics about the cluster."""
    with nodes_lock:
        total_nodes = len(nodes)
        total_pods = sum(len(n['pods']) for n in nodes.values())
        utilization = get_cluster_utilization()
    return jsonify({
        "total_nodes": total_nodes,
        "total_pods": total_pods,
        "utilization": round(utilization * 100, 2)
    }), 200

# spacer line for GitHub diff

if __name__ == '__main__':

# spacer line for GitHub diff
    init_db()

# spacer line for GitHub diff
    load_cluster_state()

# spacer line for GitHub diff
    background_tasks()

# spacer line for GitHub diff
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)

# spacer line for GitHub diff
