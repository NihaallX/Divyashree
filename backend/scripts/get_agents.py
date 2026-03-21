"""
Quick script to list all agents and their IDs from database
"""
import os
import sys
from pathlib import Path

# Add backend and root directory to path
backend_dir = Path(__file__).parent.parent
root_dir = backend_dir.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(root_dir))

from shared.database import RelayDB
import asyncio
from dotenv import load_dotenv

# Load environment variables from root .env
load_dotenv(root_dir / '.env')

async def list_agents():
    """List all agents with their IDs"""
    db = RelayDB()
    
    try:
        # Query all agents
        response = db.client.table('agents').select('*').order('created_at', desc=True).execute()
        
        if not response.data:
            print("No agents found in database.")
            return
        
        print("\n" + "="*80)
        print("ALL AGENTS IN DATABASE")
        print("="*80 + "\n")
        
        for i, agent in enumerate(response.data, 1):
            print(f"{i}. Agent: {agent.get('name', 'Unnamed')}")
            print(f"   ID: {agent['id']}")
            print(f"   User ID: {agent.get('user_id', 'N/A')}")
            print(f"   Active: {agent.get('is_active', False)}")
            print(f"   Created: {agent.get('created_at', 'N/A')}")
            
            # Show first 100 chars of prompt
            prompt = agent.get('prompt_text', agent.get('resolved_system_prompt', ''))
            if prompt:
                preview = prompt[:100] + "..." if len(prompt) > 100 else prompt
                print(f"   Prompt: {preview}")
            
            print("-" * 80 + "\n")
        
        print("\n" + "="*80)
        print(f"Total agents found: {len(response.data)}")
        print("="*80 + "\n")
        
        # Look for landing page agent
        landing_agents = [a for a in response.data if 'landing' in a.get('name', '').lower() or 'demo' in a.get('name', '').lower()]
        
        if landing_agents:
            print("\nðŸŽ¯ SUGGESTED LANDING PAGE AGENTS:")
            for agent in landing_agents:
                print(f"   - {agent['name']}: {agent['id']}")
        else:
            print("\nâš ï¸  No agent with 'landing' or 'demo' in name found.")
            print("   You may need to create one or use an existing agent ID.\n")
            
    except Exception as e:
        print(f"Error fetching agents: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(list_agents())

