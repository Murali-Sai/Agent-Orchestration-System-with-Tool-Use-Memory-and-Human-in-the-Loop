"""OpenTelemetry setup for the orchestration system.

Spans sit *underneath* the existing `trace_event()` timeline: `trace_event`
still drives the Trace Explorer UI, while OTel emits the same work as
standards-based spans that any collector (Jaeger, Tempo, Honeycomb) can read.

Export is opt-in, and that matters on a free-tier host:

- `OTEL_EXPORTER_OTLP_ENDPOINT=host:4317` → ship spans to a collector
- `OTEL_CONSOLE_EXPORT=true`              → print spans to stdout (local demo)
- neither                                → spans are created and dropped

The default is deliberate. A console exporter left on in production writes a
multi-line JSON blob per span into the platform log stream, which buries the
application's own structured logs. Dropping spans keeps the instrumentation
in place at near-zero cost until someone actually wants it.

If the opentelemetry packages aren't installed at all, this module degrades to
a no-op tracer so the rest of the system still boots — same graceful-degradation
contract as the Supabase and Redis layers.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in stripped envs
    _OTEL_AVAILABLE = False

SERVICE_NAME = "agent-orchestration-system"

_configured = False
_tracer = None


class _NoopSpan:
    """Stands in for a real span when OpenTelemetry isn't installed."""

    def set_attribute(self, *_args, **_kwargs) -> None:
        pass

    def record_exception(self, *_args, **_kwargs) -> None:
        pass

    def set_status(self, *_args, **_kwargs) -> None:
        pass


class _NoopTracer:
    @contextmanager
    def start_as_current_span(self, *_args, **_kwargs):
        yield _NoopSpan()


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def configure_tracing(service_name: str = SERVICE_NAME):
    """Initialise the global tracer provider. Safe to call more than once."""
    global _configured, _tracer

    if _configured:
        return _tracer

    if not _OTEL_AVAILABLE:
        _tracer = _NoopTracer()
        _configured = True
        return _tracer

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
            )
        except ImportError:
            # Endpoint configured but the OTLP exporter isn't installed —
            # fall through to a provider with no processor rather than crash.
            pass
    elif _truthy(os.getenv("OTEL_CONSOLE_EXPORT")):
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)
    _configured = True
    return _tracer


def get_tracer():
    """The shared tracer, configuring it on first use."""
    return _tracer if _configured else configure_tracing()


def instrument_fastapi(app) -> bool:
    """Attach FastAPI auto-instrumentation. Returns False if unavailable."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        return False

    try:
        FastAPIInstrumentor.instrument_app(app)
        return True
    except Exception:
        return False


tracer = configure_tracing()
