import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from config import TRACING

logger = logging.getLogger(__name__)

_tracer = None


def get_tracer():
    global _tracer
    if _tracer is not None:
        return _tracer

    if not TRACING.enabled:
        # No-op tracer: start_as_current_span still works, just produces no output.
        _tracer = trace.get_tracer(TRACING.service_name)
        return _tracer

    provider = TracerProvider(resource=Resource.create({"service.name": TRACING.service_name}))

    if TRACING.otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter(endpoint=TRACING.otlp_endpoint, insecure=True)
        logger.info("OpenTelemetry exporting to OTLP endpoint %s", TRACING.otlp_endpoint)
    else:
        exporter = ConsoleSpanExporter()
        logger.info("OpenTelemetry exporting to console (set OTEL_EXPORTER_OTLP_ENDPOINT for a real backend)")

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(TRACING.service_name)
    return _tracer
