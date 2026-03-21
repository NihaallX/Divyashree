from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List, Dict
from datetime import datetime, timedelta, timezone
from loguru import logger
from shared.database import get_db, RelayDB
from auth import get_current_user_id

router = APIRouter()

# ==================== ROUTES ====================

@router.get("/stats")
async def get_stats(db: RelayDB = Depends(get_db)):
    """Get system statistics for dashboard"""
    try:
        agents = await db.list_agents()
        calls = await db.list_calls()
        
        # Cleanup stale calls (older than 10 minutes in active status)
        stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=10)
        for call in calls:
            if call.get("status") in ["initiated", "in-progress"]:
                try:
                    call_time_str = call.get("created_at")
                    if call_time_str:
                        # Parse ISO format with timezone
                        call_time = datetime.fromisoformat(call_time_str.replace("Z", "+00:00"))
                        if call_time < stale_threshold:
                            await db.update_call(call["id"], status="failed")
                            logger.info(f"Auto-cleaned stale call: {call['id']}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup stale call {call.get('id')}: {e}")
        
        # Get active calls from voice gateway
        import httpx
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                vg_response = await client.get("http://localhost:8001/")
                vg_data = vg_response.json()
                active_calls = vg_data.get("active_calls", 0)
        except:
            active_calls = 0
        
        return {
            "total_agents": len(agents),
            "total_calls": len(calls),
            "active_calls": active_calls,
            "calls_completed": len([c for c in calls if c.get("status") == "completed"]),
            "calls_failed": len([c for c in calls if c.get("status") == "failed"]),
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {"total_agents": 0, "total_calls": 0, "active_calls": 0}


@router.get("/dashboard/stats")
async def get_dashboard_stats(
    user_id: str = Depends(get_current_user_id),
    db: RelayDB = Depends(get_db)
):
    """Get aggregated dashboard statistics for the current user"""
    try:
        # Fetch all user's calls
        response = db.client.table("calls")\
            .select("id, status, created_at, duration")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(100)\
            .execute()
        
        calls = response.data if response.data else []
        
        # Fetch all call analyses for these calls
        call_ids = [call["id"] for call in calls]
        analyses = {}
        if call_ids:
            analysis_response = db.client.table("call_analysis")\
                .select("call_id, outcome, user_sentiment")\
                .in_("call_id", call_ids)\
                .execute()
            
            for analysis in (analysis_response.data or []):
                analyses[analysis["call_id"]] = analysis
        
        # Calculate stats
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_calls = 0
        interested_count = 0
        not_interested_count = 0
        confidence_sum = 0.0
        confidence_count = 0
        
        for call in calls:
            # Count today's calls
            if call.get("created_at"):
                call_date = datetime.fromisoformat(call["created_at"].replace("Z", "+00:00"))
                if call_date >= today:
                    today_calls += 1
            
            # Get analysis data if exists
            call_id = call["id"]
            analysis = analyses.get(call_id)
            
            if analysis:
                outcome = analysis.get("outcome", "").lower()
                sentiment = analysis.get("user_sentiment", "").lower()
                
                # Count interested/not interested based on outcome
                if outcome == "interested":
                    interested_count += 1
                elif outcome == "not_interested":
                    not_interested_count += 1
                
                # Calculate confidence based on outcome clarity
                if outcome in ["interested", "not_interested"]:
                    confidence_sum += 1.0  # High confidence for clear outcomes
                    confidence_count += 1
                elif outcome in ["call_later", "needs_more_info"]:
                    confidence_sum += 0.7  # Medium confidence
                    confidence_count += 1
                elif outcome == "other":
                    confidence_sum += 0.3  # Low confidence
                    confidence_count += 1
        
        return {
            "totalCalls": len(calls),
            "interestedCalls": interested_count,
            "notInterestedCalls": not_interested_count,
            "avgConfidence": confidence_sum / confidence_count if confidence_count > 0 else 0,
            "todayCalls": today_calls
        }
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {e}")
        return {
            "totalCalls": 0,
            "interestedCalls": 0,
            "notInterestedCalls": 0,
            "avgConfidence": 0,
            "todayCalls": 0
        }


@router.get("/analytics")
async def get_analytics(
    days: int = 7,
    user_id: str = Depends(get_current_user_id),
    db: RelayDB = Depends(get_db)
):
    """
    Get analytics data for charts and visualizations.
    """
    try:
        # Clamp days to valid range
        days = min(max(days, 7), 90)
        
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # Fetch calls within date range
        response = db.client.table("calls")\
            .select("id, status, created_at, duration")\
            .eq("user_id", user_id)\
            .gte("created_at", start_date.isoformat())\
            .order("created_at", desc=False)\
            .execute()
        
        calls = response.data if response.data else []
        
        # Fetch all call analyses for these calls
        call_ids = [call["id"] for call in calls]
        analyses = {}
        if call_ids:
            analysis_response = db.client.table("call_analysis")\
                .select("call_id, outcome, user_sentiment")\
                .in_("call_id", call_ids)\
                .execute()
            
            for analysis in (analysis_response.data or []):
                analyses[analysis["call_id"]] = analysis
        
        # Initialize data structures
        daily_counts = {}
        hourly_counts = [0] * 24
        outcome_distribution = {
            "interested": 0,
            "notInterested": 0,
            "noAnswer": 0,
            "other": 0
        }
        total_duration = 0
        duration_count = 0
        completed_count = 0
        
        for call in calls:
            # Parse date
            created_at_str = call.get("created_at", "")
            if not created_at_str:
                continue
                
            try:
                call_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except:
                continue
            
            # Daily aggregation
            date_key = call_dt.strftime("%Y-%m-%d")
            if date_key not in daily_counts:
                daily_counts[date_key] = {"date": date_key, "count": 0, "completed": 0, "failed": 0}
            daily_counts[date_key]["count"] += 1
            
            status = call.get("status", "")
            if status == "completed":
                daily_counts[date_key]["completed"] += 1
                completed_count += 1
            elif status == "failed":
                daily_counts[date_key]["failed"] += 1
            
            # Hourly aggregation
            hour = call_dt.hour
            hourly_counts[hour] += 1
            
            # Duration tracking
            duration = call.get("duration")
            if duration and isinstance(duration, (int, float)) and duration > 0:
                total_duration += duration
                duration_count += 1
            
            # Outcome distribution from call_analysis table
            call_id = call["id"]
            analysis = analyses.get(call_id)
            
            if status == "completed":
                if analysis:
                    outcome = analysis.get("outcome", "").lower()
                    
                    if outcome == "interested":
                        outcome_distribution["interested"] += 1
                    elif outcome == "not_interested":
                        outcome_distribution["notInterested"] += 1
                    elif outcome in ["no_answer", "busy"]:
                        outcome_distribution["noAnswer"] += 1
                    else:
                        outcome_distribution["other"] += 1
                else:
                    # No analysis yet - mark as other
                    outcome_distribution["other"] += 1
            elif status in ["no-answer", "busy"]:
                outcome_distribution["noAnswer"] += 1
        
        # Fill in missing dates with zeros
        daily_calls = []
        current = start_date
        while current <= end_date:
            date_key = current.strftime("%Y-%m-%d")
            if date_key in daily_counts:
                daily_calls.append(daily_counts[date_key])
            else:
                daily_calls.append({"date": date_key, "count": 0, "completed": 0, "failed": 0})
            current += timedelta(days=1)
        
        # Format hourly breakdown
        hourly_breakdown = [{"hour": h, "count": hourly_counts[h]} for h in range(24)]
        
        # Calculate metrics
        total_calls = len(calls)
        success_rate = (completed_count / total_calls * 100) if total_calls > 0 else 0
        avg_duration = (total_duration / duration_count) if duration_count > 0 else 0
        
        return {
            "dailyCalls": daily_calls,
            "outcomeDistribution": outcome_distribution,
            "hourlyBreakdown": hourly_breakdown,
            "averageDuration": round(avg_duration, 1),
            "successRate": round(success_rate, 1),
            "totalCalls": total_calls,
            "completedCalls": completed_count,
            "dateRange": {
                "start": start_date.strftime("%Y-%m-%d"),
                "end": end_date.strftime("%Y-%m-%d"),
                "days": days
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        return {
            "dailyCalls": [],
            "outcomeDistribution": {"interested": 0, "notInterested": 0, "noAnswer": 0, "other": 0},
            "hourlyBreakdown": [],
            "averageDuration": 0,
            "successRate": 0,
            "totalCalls": 0,
            "completedCalls": 0,
            "dateRange": {"start": "", "end": "", "days": days}
        }

