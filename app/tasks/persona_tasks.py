from app.celery_app import celery_app

@celery_app.task
def generate_user_persona(user_id: str):
    """
    Placeholder task for generating user personas.
    """
    pass
