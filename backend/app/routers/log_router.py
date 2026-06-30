"""
log_router.py — API endpoints for model generation logs.

Provides:
- GET /api/logs — List generation logs with filtering
- GET /api/logs/stats — Get user statistics
- POST /api/logs/feedback — Submit user feedback
"""

import time
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List

from app.core.logging_service import LoggingService, get_logging_service

router = APIRouter(prefix="/api/logs", tags=["logs"])


# Request/Response models
class GenerationLogQuery(BaseModel):
    """Query parameters for generation logs."""
    user_id: str
    model: Optional[str] = None
    limit: int = 100
    offset: int = 0
    days: Optional[int] = None


class StatsQuery(BaseModel):
    """Query parameters for statistics."""
    user_id: str
    days: int = 30


class FeedbackRequest(BaseModel):
    """Feedback submission request."""
    log_id: str
    rating: int = Field(..., ge=1, le=5)
    score: Optional[float] = None


class StatsResponse(BaseModel):
    """Statistics response."""
    user_id: str
    total_generations: int
    total_tokens: int
    avg_generation_time_ms: float
    avg_feedback_score: Optional[float]
    last_generation_at: Optional[float]


class GenerationLogResponse(BaseModel):
    """Single generation log response."""
    id: str
    user_id: str
    conversation_id: str
    model_name: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    temperature: Optional[float]
    generation_time_ms: float
    feedback_rating: Optional[int]
    retry_count: int
    created_at: float


class GenerationLogListResponse(BaseModel):
    """List of generation logs response."""
    logs: List[GenerationLogResponse]
    total: int


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    query: StatsQuery = Depends(),
    logging_service: LoggingService = Depends(get_logging_service)
):
    """Get statistics for a user."""
    try:
        stats = logging_service.get_user_stats(query.user_id)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=GenerationLogListResponse)
async def get_logs(
    query: GenerationLogQuery = Depends(),
    logging_service: LoggingService = Depends(get_logging_service)
):
    """Get generation logs for a user."""
    try:
        logs = logging_service.get_user_generations(
            query.user_id,
            limit=query.limit,
            offset=query.offset
        )

        response_logs = [
            GenerationLogResponse(**log)
            for log in logs
        ]

        return GenerationLogListResponse(
            logs=response_logs,
            total=len(logs)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    logging_service: LoggingService = Depends(get_logging_service)
):
    """Submit feedback for a generation."""
    try:
        success = logging_service.log_feedback(
            log_id=request.log_id,
            rating=request.rating,
            score=request.score
        )
        if success:
            return {"message": "Feedback submitted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Log not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup")
async def cleanup_old_logs(
    days: int = Query(..., ge=1, le=365),
    logging_service: LoggingService = Depends(get_logging_service)
):
    """Delete logs older than specified days."""
    try:
        cutoff_time = time.time() - (days * 24 * 3600)

        conn = logging_service.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM model_generation_logs
            WHERE created_at < ?
        """, (cutoff_time,))

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return {"message": f"Deleted {affected} logs older than {days} days"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ["router"]
