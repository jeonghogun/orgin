from celery import Celery, Task
from app.config.settings import settings
from app.utils.trace_id import trace_id_var

class ContextTask(Task):
    def __call__(self, *args, **kwargs):
        # If a trace_id is passed in kwargs, set it in the context variable
        # for the duration of this task.
        trace_id = kwargs.get("trace_id")
        if trace_id:
            trace_id_var.set(trace_id)
        return super().__call__(*args, **kwargs)

celery_app = Celery(
    "tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.review_tasks", "app.tasks.persona_tasks"],
    Task=ContextTask,  # Use the custom task class
)

from kombu import Queue

celery_app.conf.update(  # type: ignore
    task_track_started=True,
    result_extended=True,
    task_queues=(
        Queue("default", routing_key="task.default"),
        Queue("high_priority", routing_key="task.high_priority"),
        Queue("low_priority", routing_key="task.low_priority"),
    ),
    task_default_queue="default",
    task_default_exchange="tasks",
    task_default_routing_key="task.default",
)

def route_task(name, args, kwargs, options, task=None, **kw):
    if name == 'app.tasks.review_tasks.run_initial_panel_turn':
        return {'queue': 'high_priority', 'routing_key': 'task.high_priority'}
    if name == 'app.tasks.review_tasks.generate_consolidated_report':
        return {'queue': 'low_priority', 'routing_key': 'task.low_priority'}
    return {'queue': 'default', 'routing_key': 'task.default'}

celery_app.conf.task_routes = (route_task,)
