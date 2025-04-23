import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

def init_supabase_tables():
    """Create Supabase tables if they don't exist."""
    # This function would typically use SQL to set up tables via the Supabase UI or API
    # For this project, we'll create tables through the Supabase interface directly
    
    # We'll just check if we can connect to Supabase
    try:
        response = supabase.table('nodes').select('*').limit(1).execute()
        print("✅ Successfully connected to Supabase")
        return True
    except Exception as e:
        print("❌ Failed to connect to Supabase:", str(e))
        return False

def get_nodes():
    """Retrieve all nodes from Supabase."""
    try:
        response = supabase.table('nodes').select('*').execute()
        return response.data
    except Exception as e:
        print(f"Error retrieving nodes: {e}")
        return []

def get_pods():
    """Retrieve all pods from Supabase."""
    try:
        response = supabase.table('pods').select('*').execute()
        return response.data
    except Exception as e:
        print(f"Error retrieving pods: {e}")
        return []

def get_logs():
    """Retrieve event logs from Supabase."""
    try:
        response = supabase.table('event_logs').select('*').order('timestamp.desc').limit(50).execute()
        return response.data
    except Exception as e:
        print(f"Error retrieving logs: {e}")
        return []

def get_utilization_history():
    """Retrieve utilization history from Supabase."""
    try:
        response = supabase.table('utilization_history').select('*').order('timestamp.desc').limit(50).execute()
        return response.data
    except Exception as e:
        print(f"Error retrieving utilization history: {e}")
        return []

def save_node(node):
    """Save or update a node in Supabase."""
    try:
        response = supabase.table('nodes').upsert(node).execute()
        return response.data
    except Exception as e:
        print(f"Error saving node: {e}")
        return None

def delete_node(node_id):
    """Delete a node and its associated pods from Supabase."""
    try:
        # Delete pods associated with this node
        supabase.table('pods').delete().eq('node_id', node_id).execute()
        # Delete the node
        response = supabase.table('nodes').delete().eq('node_id', node_id).execute()
        return response.data
    except Exception as e:
        print(f"Error deleting node: {e}")
        return None

def save_pod(pod):
    """Save or update a pod in Supabase."""
    try:
        response = supabase.table('pods').upsert(pod).execute()
        return response.data
    except Exception as e:
        print(f"Error saving pod: {e}")
        return None

def update_pod_node(pod_id, new_node_id):
    """Update the node assignment for a pod."""
    try:
        response = supabase.table('pods').update({'node_id': new_node_id}).eq('pod_id', pod_id).execute()
        return response.data
    except Exception as e:
        print(f"Error updating pod node: {e}")
        return None

def log_event(message):
    """Log an event to Supabase."""
    import time
    try:
        event = {
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            'message': message
        }
        response = supabase.table('event_logs').insert(event).execute()
        return response.data
    except Exception as e:
        print(f"Error logging event: {e}")
        return None

def record_utilization(utilization_value):
    """Record cluster utilization to Supabase."""
    import time
    try:
        record = {
            'timestamp': time.time(),
            'utilization': utilization_value
        }
        response = supabase.table('utilization_history').insert(record).execute()
        return response.data
    except Exception as e:
        print(f"Error recording utilization: {e}")
        return None
  
if __name__ == "__main__":
    # Test connection
    init_supabase_tables() 