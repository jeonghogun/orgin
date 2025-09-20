"""
Health check endpoints for monitoring and load balancing.
"""
import logging
from fastapi import APIRouter, HTTPException
from redis.exceptions import RedisError

from app.services.database_service import get_database_service
from app.config.settings import Settings, get_effective_redis_url
from app.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Basic health check endpoint.
    Returns 200 if the service is running.
    """
    return {"status": "healthy", "service": "origin-api"}

@router.get("/health/detailed")
async def detailed_health_check():
    """
    Detailed health check that verifies database connectivity.
    """
    health_status = {
        "status": "healthy",
        "service": "origin-api",
        "components": {}
    }
    
    # Check database connectivity
    try:
        db_service = get_database_service()
        # Simple query to test connection
        result = db_service.execute_query("SELECT 1 as test", ())
        if result and result[0]["test"] == 1:
            health_status["components"]["database"] = "healthy"
        else:
            health_status["components"]["database"] = "unhealthy"
            health_status["status"] = "degraded"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["components"]["database"] = "unhealthy"
        health_status["status"] = "unhealthy"
    
    # Check Redis connectivity (if configured)
    redis_url = get_effective_redis_url()
    if redis_url:
        try:
            import redis

            redis_client = redis.from_url(redis_url, decode_responses=True)
            redis_client.ping()
            health_status["components"]["redis"] = "healthy"
        except (RedisError, Exception) as e:
            logger.warning(f"Redis health check failed: {e}")
            health_status["components"]["redis"] = "unhealthy"
            # Redis failure doesn't make the service unhealthy, just degraded
            if health_status["status"] == "healthy":
                health_status["status"] = "degraded"
    else:
        health_status["components"]["redis"] = "disabled"

    # Check Celery worker availability
    try:
        inspector = celery_app.control.inspect(timeout=1)
        ping_result = inspector.ping() if inspector else None
        if ping_result:
            health_status["components"]["celery"] = "healthy"
        else:
            health_status["components"]["celery"] = "unavailable"
            if health_status["status"] == "healthy":
                health_status["status"] = "degraded"
    except Exception as celery_error:
        logger.warning(f"Celery health check failed: {celery_error}")
        health_status["components"]["celery"] = "unhealthy"
        if health_status["status"] == "healthy":
            health_status["status"] = "degraded"

    # Verify required configuration secrets are present
    settings = Settings()
    missing_secrets = []
    if not settings.DB_ENCRYPTION_KEY:
        missing_secrets.append("DB_ENCRYPTION_KEY")
    if not settings.DATABASE_URL:
        missing_secrets.append("DATABASE_URL")

    if missing_secrets:
        health_status["components"]["configuration"] = f"missing: {', '.join(missing_secrets)}"
        if health_status["status"] == "healthy":
            health_status["status"] = "degraded"
    else:
        health_status["components"]["configuration"] = "healthy"

    # Return appropriate HTTP status
    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=health_status)
    
    return health_status

@router.get("/ready")
async def readiness_check():
    """
    Readiness check for Kubernetes deployments.
    Returns 200 when the service is ready to accept traffic.
    """
    # For now, same as health check
    # In the future, could check if migrations are complete, etc.
    return await health_check()
