import click
import requests
import time
from urllib.parse import urljoin

# Configuration
API_BASE_URL = "http://localhost:5000"
TIMEOUT = 5  # seconds

def make_api_url(endpoint):
    """Construct full API URL"""
    return urljoin(API_BASE_URL, endpoint)

def print_response(response):
    """Print API response in a readable format"""
    try:
        data = response.json()
        if isinstance(data, dict):
            for key, value in data.items():
                click.echo(f"{key.capitalize()}: {value}")
        elif isinstance(data, list):
            for item in data:
                click.echo(item)
        else:
            click.echo(data)
    except ValueError:
        click.echo(f"Raw response: {response.text}")

def check_api_health():
    """Check if API server is reachable"""
    try:
        response = requests.get(make_api_url('/'), timeout=TIMEOUT)
        if response.status_code == 200:
            return True
    except requests.exceptions.RequestException:
        return False
    return False

@click.group()
def cli():
    """Distributed Systems Cluster Simulation CLI"""
    if not check_api_health():
        click.secho("⚠️  API server is not responding", fg='red')
        click.echo(f"Please ensure the API server is running at {API_BASE_URL}")
        click.echo("Start it with: python api/server.py")

@cli.command()
@click.option('--cpu-cores', required=True, type=int, help='Number of CPU cores for the node')
def add_node(cpu_cores):
    """Add a new node to the cluster"""
    if cpu_cores <= 0:
        click.secho("❌ CPU cores must be a positive number", fg='red')
        return

    try:
        click.echo("⏳ Adding node to cluster...")
        start_time = time.time()
        
        response = requests.post(
            make_api_url('/nodes'),
            json={"cpu_cores": cpu_cores},
            timeout=TIMEOUT
        )
        
        duration = time.time() - start_time
        click.echo(f"✅ Request completed in {duration:.2f}s")
        
        if response.status_code == 201:
            click.secho("✔ Node added successfully", fg='green')
            print_response(response)
        else:
            click.secho(f"❌ Error adding node: {response.status_code}", fg='red')
            print_response(response)
            
    except requests.exceptions.ConnectionError:
        click.secho("❌ Failed to connect to API server", fg='red')
        click.echo(f"Please check if the server is running at {API_BASE_URL}")
    except requests.exceptions.Timeout:
        click.secho("❌ Request timed out", fg='red')
        click.echo("The API server is not responding in a timely manner")
    except Exception as e:
        click.secho(f"❌ Unexpected error: {str(e)}", fg='red')

@cli.command()
def list_nodes():
    """List all nodes in the cluster with details"""
    try:
        click.echo("⏳ Fetching cluster nodes...")
        response = requests.get(make_api_url('/nodes'), timeout=TIMEOUT)
        
        if response.status_code == 200:
            nodes = response.json()
            if not nodes:
                click.echo("ℹ No nodes found in the cluster")
                return
                
            click.secho("\n🏗 Cluster Node Summary", fg='blue', bold=True)
            click.echo(f"Total Nodes: {len(nodes)}")
            click.secho("="*50, fg='blue')
            
            for node_id, node_data in nodes.items():
                click.secho(f"\n🆔 Node ID: {node_id}", fg='yellow')
                click.echo(f"🔧 Status: {node_data.get('status', 'unknown')}")
                click.echo(f"💻 CPU Cores: {node_data.get('cpu', 'N/A')}")
                click.echo(f"🆓 Available CPU: {node_data.get('available_cpu', 'N/A')}")
                click.echo(f"📦 Pods Running: {len(node_data.get('pods', []))}")
                click.echo(f"❤️ Last Heartbeat: {node_data.get('last_heartbeat', 'N/A')}")
                if node_data.get('is_simulated', False):
                    click.secho("⚠ Note: This is a simulated node", fg='cyan')
                
            click.secho("\n" + "="*50, fg='blue')
        else:
            click.secho(f"❌ Error fetching nodes: {response.status_code}", fg='red')
            print_response(response)
            
    except requests.exceptions.ConnectionError:
        click.secho("❌ Failed to connect to API server", fg='red')
    except requests.exceptions.Timeout:
        click.secho("❌ Request timed out", fg='red')
    except Exception as e:
        click.secho(f"❌ Unexpected error: {str(e)}", fg='red')

@cli.command()
@click.option('--cpu-required', required=True, type=int, help='CPU cores required for the pod')
def launch_pod(cpu_required):
    """Launch a new pod in the cluster"""
    if cpu_required <= 0:
        click.secho("❌ CPU requirement must be positive", fg='red')
        return

    try:
        click.echo(f"⏳ Launching pod with {cpu_required} CPU cores...")
        response = requests.post(
            make_api_url('/pods'),
            json={"cpu_required": cpu_required},
            timeout=TIMEOUT
        )
        
        if response.status_code == 201:
            click.secho("✔ Pod launched successfully", fg='green')
            print_response(response)
        else:
            click.secho(f"❌ Error launching pod: {response.status_code}", fg='red')
            print_response(response)
            
    except requests.exceptions.RequestException as e:
        click.secho(f"❌ Network error: {str(e)}", fg='red')

if __name__ == '__main__':
    cli()