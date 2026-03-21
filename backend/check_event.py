"""Test if event was created in database"""
import asyncio
import os
from shared.database import RelayDB

async def check_event():
    db = RelayDB(database_url=os.getenv("DATABASE_URL"))
    
    # Get the most recent event
    result = db.client.table("scheduled_events").select("*").order("created_at", desc=True).limit(1).execute()
    
    if result.data:
        event = result.data[0]
        print(f"âœ… Found event:")
        print(f"   ID: {event['id']}")
        print(f"   Title: {event['title']}")
        print(f"   Scheduled: {event['scheduled_at']}")
        print(f"   Contact: {event['contact_name'] or 'None'} ({event['contact_phone']})")
        print(f"   User ID: {event['user_id']}")
        print(f"   Call ID: {event['call_id']}")
        print(f"   Status: {event['status']}")
        print(f"   Created Auto: {event['created_automatically']}")
    else:
        print("âŒ No events found in database")

asyncio.run(check_event())

