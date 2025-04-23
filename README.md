# Cluster Simulation Framework

## Overview
The Cluster Simulation Framework is a Python-based tool designed to simulate a distributed computing cluster. It provides a Flask-based API server, a CLI client for interacting with the cluster, a node simulator for sending heartbeats, and an advanced web-based dashboard for real-time monitoring. The framework supports node management, pod scheduling with multiple algorithms, auto-scaling, health monitoring, and a Chaos Monkey feature to simulate failures.

## Features
- **Node Management**: Add, remove, and list nodes with specified CPU and memory capacities.
- **Pod Scheduling**: Launch pods with resource requirements and choose from `first_fit`, `best_fit`, or `worst_fit` scheduling algorithms.
- **Auto-Scaling**: Automatically adds nodes when CPU utilization exceeds 80%.
- **Health Monitoring**: Detects node failures via heartbeat timeouts and reschedules pods from failed nodes.
- **Chaos Monkey**: Randomly kills nodes to simulate failures.
- **Real-Time Dashboard**: Visualizes cluster state, node details, CPU distribution, utilization history, and a 3D node graph using ECharts.
- **Event Logging**: Logs events to an SQLite database and displays them in the dashboard.
- **Utilization Tracking**: Records and visualizes cluster utilization over time.
- **Network Groups and Node Affinity**: Supports network group isolation and node affinity for pod scheduling.

## Requirements
- Python 3.8+
- Docker (optional, for container-based node simulation)

## Quick Setup & Run

### 1. Install Dependencies:
```bash
pip install -r requirements.txt
```

### 2. Start the Server:
```bash
python server_2.py
```
The server runs on [http://localhost:5000](http://localhost:5000) by default.

### 3. Access the Dashboard:
Open a web browser and navigate to [http://localhost:5000/dashboard](http://localhost:5000/dashboard).

### 4. Use the CLI Client:
```bash
# Add a node with 8 CPU cores and 16GB memory
python client.py add_node --cpu 8 --memory 16

# Launch a pod requiring 2 CPU cores with first-fit scheduling
python client.py launch_pod --cpu_required 2 --scheduling_algorithm first_fit

# List all nodes and their details
python client.py list_nodes

# Trigger Chaos Monkey for random failure
python client.py chaos_monkey
```

## Docker Support
You can run nodes in Docker containers:

```bash
# Build the node simulator image
docker build -t node-simulator .

# The server will automatically launch containers for nodes
```

## Dashboard Features
- Monitor active/total nodes and cluster utilization
- Add nodes or launch pods via interactive forms
- View CPU distribution and utilization history charts
- Visualize nodes in a 3D network graph
- Monitor event logs in real-time
- Download cluster reports as CSV

## Architecture Overview
- `server_2.py`: Main server with API endpoints, dashboard, and background tasks
- `client.py`: CLI client for interacting with the cluster
- `node.py`: Node simulator for sending heartbeats
- The system uses SQLite for event logs and utilization history
- Socket.IO for real-time dashboard updates

## License
This project is licensed under the MIT License.
