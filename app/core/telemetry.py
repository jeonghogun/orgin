"""
Telemetry Configuration using OpenTelemetry.
"""
import logging
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from app.config.settings import settings

def setup_telemetry():
    """
    Configures OpenTelemetry for the application.
    If an OTLP endpoint is configured, it exports traces to that endpoint.
    Otherwise, it falls back to exporting to the console for local debugging.
    """
    resource = Resource(attributes={
        "service.name": "origin-project-api"
    })

    # --- Trace Configuration ---
    tracer_provider = TracerProvider(resource=resource)

    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        # Production-ready exporter
        span_exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
        logging.info(f"OpenTelemetry configured with OTLP exporter to endpoint: {settings.OTEL_EXPORTER_OTLP_ENDPOINT}")
    else:
        # Local debugging exporter
        span_exporter = ConsoleSpanExporter()
        logging.info("OpenTelemetry configured with Console exporter.")

    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    # --- Metrics Configuration (still exporting to console for this sample) ---
    metric_reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # --- Logging Configuration ---
    # This will automatically attach trace context to logs (trace_id, span_id)
    LoggingInstrumentor().instrument(set_logging_format=True)

def get_tracer(name: str):
    """Convenience function to get a tracer."""
    return trace.get_tracer(name)

def get_meter(name: str):
    """Convenience function to get a meter."""
    return metrics.get_meter(name)
