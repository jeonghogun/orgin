"""
Review-related API endpoints
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request

from app.services.storage_service import storage_service
from app.utils.helpers import generate_id, get_current_timestamp, create_success_response
from app.models.schemas import CreateReviewRequest, ReviewMeta

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["reviews"])

# Dependency for authentication (will be imported from main)
auth_dependency: Any = None

def set_auth_dependency(auth_dep: Any) -> None:
    """Set authentication dependency from main app"""
    global auth_dependency
    auth_dependency = auth_dep

@router.post("")
async def create_review(
    request: Request,
    user_info: Dict[str, str] = auth_dependency
):
    """Create a new review"""
    try:
        body = await request.json()
        review_request = CreateReviewRequest(**body)
        
        # Generate review ID
        review_id = generate_id()
        
        # Create review metadata
        review_meta = ReviewMeta(
            review_id=review_id,
            room_id=review_request.topic,  # Using topic as room_id for now
            topic=review_request.topic,
            status="in_progress",
            total_rounds=len(review_request.rounds),
            current_round=0,
            created_at=get_current_timestamp()
        )
        
        # Save review metadata
        await storage_service.save_review_meta(review_meta)
        
        return create_success_response(
            data={"review_id": review_id},
            message="Review created successfully"
        )
    except Exception as e:
        logger.error(f"Error creating review: {e}")
        raise HTTPException(status_code=500, detail="Failed to create review")

@router.get("/{review_id}")
async def get_review(review_id: str, user_info: Dict[str, str] = auth_dependency):
    """Get review information"""
    try:
        review = await storage_service.get_review_meta(review_id)
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        return create_success_response(data=review.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting review {review_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get review")

@router.get("/{review_id}/report")
async def get_review_report(review_id: str, user_info: Dict[str, str] = auth_dependency):
    """Get review report"""
    try:
        report = await storage_service.get_consolidated_report(review_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        
        return create_success_response(data=report.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting report for review {review_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get report")
