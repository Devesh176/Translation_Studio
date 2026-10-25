# Translation Studio V1

> **Production-grade Structure-Preserving Document Transformation & Indic Translation Platform**

Translation Studio is an API-first platform that accepts PDFs, parses them into a high-fidelity **Document Intermediate Representation (Document IR)**, routes translation deterministically to Bodhan (for Indic language pairs) or OpenRouter (for general LLMs), validates invariants and semantics, and re-renders structure-preserving PDFs with HarfBuzz Complex Text Layout (CTL) OpenType shaping.

---

## Key Features

1. **Structure-Preserving Translation:** Headings, paragraphs, multi-column reading orders, tables, footnotes, and links remain intact with layout coordinate accuracy.
2. **Prompt-Edit Specific Sections:** Refine any individual paragraph or heading with natural language prompts without corrupting or modifying unrelated pages/sections.
3. **Complex Text Layout (CTL) & Indic OpenType Shaping:** True Indic ligature, conjunct (*yuktakshar*), and vowel-sign (*matra*) glyph shaping using Google Noto fonts.
4. **Deterministic Provider Routing & Fallback:** Routes supported Indic pairs to Bodhan and general LLM workflows to OpenRouter with automatic circuit-breaker fallback.
5. **Cost Guard & Token Estimator:** Script-aware multi-byte token estimation protects API limits and budget allocations.
6. **Dual Storage & Task Runners:** Pluggable execution architecture supporting local in-memory/file storage and sync execution for development/testing, and S3/MinIO + Celery/Redis for production workloads.

---

## System Architecture

```text
[PDF Upload] 
     │
     ▼
[PDF Classification] (Digital vs Scanned)
     │
     ▼
[PyMuPDF / Bodhan OCR] ──► [Structured Document IR] ◄── [Span-Level Styles]
                                  │
                                  ▼
                        [Language Normalizer]
                                  │
                                  ▼
                     [Deterministic Policy Router]
                        │                    │
                        ▼                    ▼
                   [Bodhan MT]         [OpenRouter LLM]
                        │                    │
                        └─────────┬──────────┘
                                  │
                                  ▼
                         [Invariant QA & QA]
                                  │
                                  ▼
                       [Layout Engine (HarfBuzz)]
                                  │
                                  ▼
                         [PDF Render Worker]
                                  │
                                  ▼
                           [Translated PDF]
```

---

## Quickstart

### 1. Environment Configuration
Copy the `.env.example` file and set any API keys if available:
```bash
cp .env.example .env
```

### 2. Run Locally with Docker Compose
```bash
docker-compose up --build
```
The FastAPI Gateway will be available at `http://localhost:8000`.

Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

---

## API Endpoints

- **Health Check:** `GET /healthz`
- **Upload Document:** `POST /api/v1/documents/upload`
- **Translate Document:** `POST /api/v1/documents/{document_id}/translate`
- **Prompt-Edit Section:** `POST /api/v1/documents/{document_id}/nodes/{node_id}/edit`
- **Download Translated PDF:** `GET /api/v1/documents/{document_id}/versions/{version_id}/pdf`
- **Get Document Structure (IR):** `GET /api/v1/documents/{document_id}/versions/{version_id}/structure`

---

## Repository Structure

```text
translation-studio/
├── apps/
│   ├── api/                    # FastAPI application & REST endpoints
│   └── worker/                 # Task pipelines (translation, section editing)
├── config/                     # Languages, routing policies, prompts, fonts
├── docker/                     # Multi-stage Dockerfiles with HarfBuzz/Noto fonts
├── packages/
│   ├── core/                   # Document IR models, exceptions, domain events
│   ├── document/               # PyMuPDF parser, classifier, IR serialization
│   ├── providers/              # Bodhan (indic-ocr, indic-translate), OpenRouter adapters
│   ├── routing/                # Deterministic router & language normalizer
│   ├── translation/            # Cost guard, chunker, prompts, normalizer
│   ├── validation/             # Invariant, table, semantic & visual QA
│   ├── rendering/              # HarfBuzz layout engine, overlays, PDF renderer
│   └── storage/                # S3, Local, Memory, Redis & PostgreSQL
└── tests/                      # Unit & End-to-End integration test suite
```

---

## Observability

Translation Studio ships a full production observability stack covering all four pillars: **structured logging**, **distributed tracing**, **metrics**, and **exception tracking**.

### Architecture

```text
Application (API + Worker)
        │
        ├─── structlog JSON logs ──────────► stdout
        │                                       │
        │                                   Promtail
        │                                       │
        │                                       ▼
        │                                     Loki ◄──── Grafana
        │
        ├─── OTel SDK (traces) ────────► OTel Collector
        │                                       │
        │                                       ▼
        │                                     Tempo ◄─── Grafana
        │
        ├─── prometheus-client ────────► /metrics endpoint
        │                                       │
        │                                   Prometheus ◄─ Grafana
        │
        └─── Sentry SDK ───────────────► Sentry (exceptions)
```

Every trace span, log record, and metric is correlated via `trace_id` so you can jump from a Grafana panel → log stream → trace waterfall in a single click.

### Services

| Service | Image | Local URL | Purpose |
|---|---|---|---|
| `grafana` | `grafana/grafana:10.4.2` | http://localhost:3000 | Unified dashboards (no login in dev) |
| `prometheus` | `prom/prometheus:v2.52.0` | http://localhost:9090 | Metrics storage & query |
| `loki` | `grafana/loki:3.0.0` | http://localhost:3100 | Log aggregation |
| `tempo` | `grafana/tempo:2.4.2` | http://localhost:3200 | Distributed trace storage |
| `otel-collector` | `otel/opentelemetry-collector-contrib:0.100.0` | :4318 (OTLP HTTP) | Receives OTel, routes to Tempo |
| `promtail` | `grafana/promtail:3.0.0` | — | Tails container logs → Loki |

All services start automatically with:

```bash
docker compose up --build
```

### Grafana

Open **http://localhost:3000** — no login required in development.

Three datasources are pre-configured (Prometheus, Loki, Tempo) with cross-datasource correlation:

- **Metric → Trace:** click an exemplar point on any time-series panel to jump directly to the matching Tempo trace.
- **Log → Trace:** any log line containing `trace_id` renders a *"View Trace"* link to Tempo.
- **Trace → Log:** Tempo trace view shows a *"Logs for this trace"* button that queries Loki.

The **Translation Studio — Overview** dashboard is auto-provisioned at startup and contains five sections:

| Section | Key panels |
|---|---|
| HTTP / API | Request rate, error rate (5xx), p50/p95/p99 latency, active jobs |
| Translation Providers | Requests/s by provider & status, p95 latency, cumulative cost (USD), cache hit rate, provider failures |
| OCR | Pages/s by status, p95 latency, failures & retries |
| Rendering & Visual QA | Render latency, layout overflow/overlap/missing-glyph events, QA score gauge |
| Validation | Failures by check type (number mismatch, URL mismatch, sentinel leak, empty translation), pipeline duration p50/p95 |

### Structured Logging

All log output is **JSON** (structlog), written to stdout and collected by Promtail → Loki.
Every record includes `trace_id` and `span_id` when an OTel span is active.

```json
{
  "event": "pipeline_completed",
  "service": "translation-studio-api",
  "env": "development",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "document_id": "abc-123",
  "version_id": "v-456",
  "qa_score": 0.94,
  "cost_usd": 0.0021,
  "duration_ms": 8342.5,
  "level": "info",
  "timestamp": "2026-10-24T18:12:00.000000Z"
}
```

Use `get_logger` everywhere instead of `logging.getLogger`:

```python
from packages.observability.logging import get_logger

logger = get_logger(__name__)
logger.info("ocr_completed", page=3, confidence=0.97, provider="bodhan")
```

### Distributed Tracing

Traces are exported via **OTLP HTTP** to the OTel Collector, which forwards them to Tempo.
Auto-instrumented: FastAPI, httpx (Bodhan / OpenRouter calls), SQLAlchemy, Redis.

Manual spans wrap every major pipeline stage:

```
document_translation_pipeline
  ├── parse_pdf
  ├── ocr_fallback
  ├── cost_guard
  ├── translate_document
  │     └── translate_node  (per node)
  ├── render_pdf
  ├── visual_qa
  └── store_artifacts
```

Add spans in application code:

```python
from packages.observability.tracing import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("my_operation") as span:
    span.set_attribute("document.id", doc_id)
    span.set_attribute("provider", "bodhan")
    ...
```

### Metrics Reference

All metrics are exposed at `GET /metrics` (Prometheus scrape format).

| Metric | Type | Labels | Description |
|---|---|---|---|
| `http_requests_total` | Counter | method, endpoint, status_code | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | method, endpoint | Request duration |
| `http_errors_total` | Counter | method, endpoint | 5xx responses |
| `translation_requests_total` | Counter | provider, source_language, target_language, status | Translation node dispatches |
| `translation_latency_seconds` | Histogram | provider | Per-request translation latency |
| `translation_provider_failures_total` | Counter | provider, failure_code | Provider-side failures |
| `translation_cost_usd_total` | Counter | provider | Cumulative cost |
| `translation_cache_hits_total` | Counter | — | Redis / memory cache hits |
| `translation_retries_total` | Counter | provider | Retry attempts |
| `ocr_pages_total` | Counter | provider, status | Pages sent to OCR |
| `ocr_latency_seconds` | Histogram | provider | OCR round-trip latency |
| `ocr_confidence` | Histogram | provider | OCR confidence score distribution |
| `render_latency_seconds` | Histogram | — | PDF render duration |
| `render_failures_total` | Counter | failure_code | Render failures |
| `layout_overflow_total` | Counter | — | Text overflow events |
| `font_missing_glyph_total` | Counter | script | Missing glyph events |
| `visual_qa_score` | Histogram | — | QA score distribution (target ≥ 0.80) |
| `pipeline_duration_seconds` | Histogram | status | End-to-end pipeline duration |
| `active_jobs` | Gauge | — | Currently running translation jobs |
| `validation_failures_total` | Counter | check_type | Validation gate failures |
| `routing_decisions_total` | Counter | provider, reason | Routing policy decisions |

### Exception Tracking (Sentry)

Set `SENTRY_DSN` in `.env` to enable. The SDK captures all unhandled FastAPI exceptions and logs `ERROR`-level records as Sentry events. Sensitive data (API keys, PDF bytes, source/translated text) is redacted by a `before_send` hook before any payload is transmitted.

### Configuration

| Variable | Default | Description |
|---|---|---|
| `OTEL_ENABLED` | `true` | Enable OTel tracing export |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | OTLP HTTP collector endpoint |
| `SENTRY_DSN` | _(empty)_ | Sentry project DSN (leave blank to disable) |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `SERVICE_NAME` | `translation-studio-api` | OTel `service.name` resource attribute |

> **Local development without Docker Compose:**
> Set `OTEL_ENABLED=false` to disable trace export. Structured logging and the `/metrics` endpoint remain active regardless.
