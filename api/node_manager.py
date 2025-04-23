import time


# Constants
HEARTBEAT_INTERVAL = 5  # seconds
HEARTBEAT_TIMEOUT = 15  # seconds


class NodeManager:
    def __init__(self):
        self.nodes = {}  # {node_id: {cpu, available_cpu, pods, last_heartbeat, status}}

    def register_node(self, node_id, cpu_cores):
        self.nodes[node_id] = {
            "cpu": cpu_cores,
            "available_cpu": cpu_cores,
            "pods": [],
            "last_heartbeat": time.time(),
            "status": "healthy",
            "is_simulated": node_id.startswith("simulated_node_"),
        }
        return True

    def unregister_node(self, node_id):
        """Remove a node from the cluster"""
        if node_id in self.nodes:
            del self.nodes[node_id]

    def get_nodes(self):
        return self.nodes

    def node_exists(self, node_id):
        return node_id in self.nodes

    def update_heartbeat(self, node_id):
        if self.node_exists(node_id):
            self.nodes[node_id]["last_heartbeat"] = time.time()
            self.nodes[node_id]["status"] = "healthy"
            return True
        return False

    def check_node_health(self):
        current_time = time.time()
        nodes_to_remove = []

        for node_id, node_data in self.nodes.items():
            if current_time - node_data["last_heartbeat"] > HEARTBEAT_TIMEOUT:
                node_data["status"] = "unhealthy"
                # Mark for removal (actual removal should be handled carefully)
                nodes_to_remove.append(node_id)

        # Handle node removal (in a real system, you'd want to reschedule pods first)
        for node_id in nodes_to_remove:
            if node_id in self.nodes:
                del self.nodes[node_id]

    def remove_node(self, node_id):
        if self.node_exists(node_id):
            del self.nodes[node_id]
            return True
        return False
