document.addEventListener("DOMContentLoaded", function () {
  const socket = io();

  const ctx = document.getElementById("resourceChart").getContext("2d");
  const chart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Used CPU", "Available CPU"],
      datasets: [
        {
          data: [0, 0],
          backgroundColor: ["#ff6384", "#36a2eb"],
        },
      ],
    },
  });

  document
    .getElementById("addNodeForm")
    .addEventListener("submit", function (e) {
      e.preventDefault();
      const cpuCores = parseInt(document.getElementById("cpuCores").value);

      fetch("/api/nodes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cpu_cores: cpuCores }),
      })
        .then((response) => response.json())
        .then((data) => {
          if (data.status === "success") {
            alert(`Node added: ${data.node_id}`);
          }
        });
    });

  socket.on("node_update", function (nodes) {
    updateNodeTable(nodes);
    updateChart(nodes);
    document.getElementById("node-count").textContent =
      Object.keys(nodes).length;
  });

  socket.on("heartbeat", function (data) {
    console.log(`Heartbeat from node: ${data.node_id}`);
  });

  function updateNodeTable(nodes) {
    const tbody = document.getElementById("nodeTableBody");
    tbody.innerHTML = "";

    for (const [node_id, node] of Object.entries(nodes)) {
      const row = document.createElement("tr");
      row.setAttribute("data-node-id", node_id);

      row.innerHTML = `
        <td>${node_id.substring(0, 8)}...</td>
        <td><span class="badge bg-${node.status === "healthy" ? "success" : "danger"}">${node.status}</span></td>
        <td>${node.cpu}</td>
        <td>${node.available_cpu}</td>
        <td>${node.pods.length}</td>
        <td>${node.last_heartbeat.toFixed(2)}</td>
        <td><button class="btn btn-danger btn-sm delete-node-btn">Delete</button></td>
      `;

      tbody.appendChild(row);
    }

    document.querySelectorAll(".delete-node-btn").forEach((button) => {
      button.addEventListener("click", function () {
        const row = this.closest("tr");
        const nodeId = row.getAttribute("data-node-id");

        if (confirm(`Are you sure you want to delete node ${nodeId}?`)) {
          fetch(`/api/nodes/${nodeId}`, {
            method: "DELETE",
          })
            .then((response) => response.json())
            .then((data) => {
              alert(data.message || "Node deleted");
              row.remove();
            });
        }
      });
    });
  }

  function updateChart(nodes) {
    let usedCPU = 0;
    let availableCPU = 0;

    Object.values(nodes).forEach((node) => {
      usedCPU += node.cpu - node.available_cpu;
      availableCPU += node.available_cpu;
    });

    chart.data.datasets[0].data = [usedCPU, availableCPU];
    chart.update();
  }
});
