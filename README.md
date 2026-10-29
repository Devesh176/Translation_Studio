# Translation Studio

> **Production-grade Structure-Preserving Document Translation Platform for Indic Languages**

Translation Studio accepts PDF documents, parses them into a high-fidelity **Document Intermediate Representation (IR)**, routes translation deterministically to Bodhan AI (for Indic pairs) or OpenRouter (general LLMs), validates linguistic and layout invariants, and re-renders structure-preserving PDFs with HarfBuzz OpenType Complex Text Layout (CTL) shaping.

---

## Key Features

| Feature | Description |
|---|---|
| **Structure-Preserving** | Headings, paragraphs, multi-column layouts, tables, footnotes, and links remain intact with bounding-box accuracy. |
| **Indic Script CTL** | True ligature, conjunct (*yuktakshar*), and vowel-sign (*matra*) shaping via Google Noto fonts + HarfBuzz. |
| **Deterministic Routing** | Config-driven provider routing with automatic circuit-breaker fallback (Bodhan → OpenRouter). |
| **Script-Aware Cost Guard** | Pre-flight budget enforcement with per-script token multipliers (Devanagari ×2.5, Tamil/Telugu/Kannada/Malayalam ×3.0). |
| **Semantic Translation Units** | Adjacent paragraph nodes grouped before LLM dispatch to eliminate mid-sentence layout breaks. |
| **Protected Content** | CLI commands, URLs, file paths, product names masked with placeholder tokens before LLM; verified and restored after. |
| **Prompt-Edit Sections** | Refine individual nodes or bounding-box selections with natural language prompts without re-running the full pipeline. |
| **Visual QA** | Post-render boundary containment, glyph, and sentinel-leak validation with a composite score (target ≥ 0.80). |
| **Full Observability** | Structured JSON logs, distributed traces (OTel → Tempo), Prometheus metrics, Sentry exceptions — all correlated via `trace_id`. |
| **Zero-Dependency Local Stack** | SQLite fallback, in-memory cache, local file store — runs without any cloud services. |

---

## System Architecture

```
[PDF Upload]
     │
     ▼
[PDF Classifier]  ──►  DIGITAL / SCANNED / MIXED
     │
     ▼
[PyMuPDF Parser]  ──►  Document IR (pages × nodes × bboxes × styles)
     │
     ├── [OCR Fallback]  Bodhan OCR → fill empty scanned pages
     │
     ├── [Cost Guard]    Script-aware token estimation → budget check
     │
     ├── [STU Grouper]   Adjacent paragraph nodes → semantic units
     │
     ├── [Protected Content]  mask URLs / code / product names
     │
     ├── [Translation Router]  routing.yaml → Bodhan or OpenRouter
     │         │
     │         ├── [Bodhan MT]      Indic language pairs
     │         └── [OpenRouter LLM] General / fallback
     │
     ├── [Invariant QA]  numbers, URLs, email preservation
     │
     ├── [Semantic QA]   length anomaly, untranslated text, repetition
     │
     ├── [PDF Renderer]  HarfBuzz CTL → translated PDF
     │
     └── [Visual QA]     boundary containment + glyph verification
```

---

## Supported Language Pairs

| Source | Targets | Provider |
|---|---|---|
| English (`en`) | Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi | Bodhan AI |
| Hindi, Tamil, Telugu (`hi`, `ta`, `te`) | English | Bodhan AI |
| Any other pair | Any | OpenRouter (meta-llama/llama-3.3-70b) |

---

## Quickstart

### Prerequisites

- Docker & Docker Compose
- (Optional) `BODHAN_API_KEY` and `OPENROUTER_API_KEY` for live translation

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env — set BODHAN_API_OCR_KEY, BODHAN_API_TRANSLATION_KEY, OPENROUTER_API_KEY
```

### 2. Start the Full Stack

```bash
docker compose up --build
```

This starts **10 services**: `api`, `worker`, `redis`, `postgres`, `loki`, `tempo`, `otel-collector`, `promtail`, `prometheus`, `grafana`.

| Service | URL | Purpose |
|---|---|---|
| API Gateway | http://localhost:8000 | FastAPI REST |
| API Docs | http://localhost:8000/docs | Interactive OpenAPI UI |
| Grafana | http://localhost:3000 | Dashboards (no login in dev) |
| Prometheus | http://localhost:9090 | Metrics browser |
| Prometheus Metrics | http://localhost:8000/metrics | Raw scrape endpoint |

### 3. Translate a PDF

```bash
# 1. Upload
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@sample.pdf" \
  | jq .

# 2. Translate (Hindi)
curl -X POST http://localhost:8000/api/v1/documents/{document_id}/translate \
  -H "Content-Type: application/json" \
  -d '{"target_language": "hi"}' \
  | jq .

# 3. Download
curl -o translated.pdf \
  http://localhost:8000/api/v1/documents/{document_id}/versions/{version_id}/pdf
```

---

## Local Development (without Docker)

```bash
# Create virtual environment
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set minimal env vars
export DATABASE_URL="sqlite+aiosqlite:///./translation_studio.db"
export REDIS_URL="redis://localhost:6379/0"
export OTEL_ENABLED="false"

# Run API server
uvicorn apps.api.main:app --reload --port 8000
```

SQLite is used automatically when PostgreSQL is unavailable. Redis falls back to in-memory cache when unavailable.

---

## API Reference

### Documents

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/healthz` | Health check |
| `GET` | `/metrics` | Prometheus scrape endpoint |
| `POST` | `/api/v1/documents/upload` | Upload PDF — returns `document_id` |
| `POST` | `/api/v1/documents/{id}/translate` | Start translation — returns `version_id`, `qa_score`, `cost_usd` |
| `GET` | `/api/v1/documents/{id}/versions/{vid}/pdf` | Download translated PDF |
| `GET` | `/api/v1/documents/{id}/versions/{vid}/structure` | Inspect Document IR as JSON |
| `GET` | `/api/v1/documents/{id}/costs` | Cost ledger summary |

### Translate Request Body

```json
{
  "target_language": "hi",
  "source_language": "en",
  "provider": "bodhan"
}
```

`source_language` and `provider` are optional. If omitted, language is inferred from the document and the router selects the provider automatically.

### Section Editing

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/documents/{id}/nodes/{node_id}/edit` | Prompt-edit a single paragraph/heading |
| `POST` | `/api/v1/documents/{id}/edit` | Prompt-edit a bounding-box or text selection |

**Edit request body:**
```json
{
  "instruction": "Make this paragraph more formal and concise"
}
```

Returns a new `version_id` and the `edited_translation`.

---

## Repository Structure

```
translation_studio/
├── apps/
│   ├── api/                    # FastAPI gateway, routes, middleware, schemas
│   ├── web/                    # Static web frontend
│   └── worker/                 # Pipeline and section-edit task runners
├── config/
│   ├── routing.yaml            # Provider routing rules (edit without code changes)
│   ├── limits.yaml             # Cost limits & token multipliers
│   ├── prompts.yaml            # LLM prompt templates
│   ├── glossary/               # Per-language terminology YAML files
│   ├── prometheus.yaml
│   ├── loki.yaml
│   ├── tempo.yaml
│   ├── otel-collector.yaml
│   ├── promtail.yaml
│   └── grafana/                # Auto-provisioned datasources & dashboards
├── docker/                     # Multi-stage Dockerfiles (HarfBuzz + Noto fonts)
├── fonts/                      # Google Noto font TTF files
├── packages/
│   ├── core/                   # Document IR models, exceptions, config loaders
│   ├── document/               # PyMuPDF parser, PDF classifier, IR serialiser
│   ├── providers/              # Bodhan (OCR + MT) and OpenRouter adapters
│   ├── routing/                # Deterministic router, language normalisation
│   ├── translation/            # Cost guard, chunker, prompts, protected content
│   ├── semantic/               # STU grouping, segments, QA checks
│   ├── validation/             # Invariant and Visual QA validators
│   ├── rendering/              # HarfBuzz layout engine, font registry, PDF renderer
│   ├── editing/                # Selection resolver, feasibility checker
│   ├── costs/                  # Cost collector and ledger
│   ├── storage/                # PostgreSQL, Redis, local object store
│   └── observability/          # structlog, OTel, prometheus-client, Sentry
└── tests/                      # pytest unit & integration tests
```

---

## Configuration Reference

All routing, cost, and prompt configuration lives in YAML files under `config/` and can be tuned **without touching Python code**.

### Routing (`config/routing.yaml`)

Add new language pairs or switch providers:

```yaml
routes:
  - source: en
    targets: [hi, ta, te, kn, ml, bn, mr, gu, pa]
    provider: bodhan
default:
  provider: openrouter
  model: "meta-llama/llama-3.3-70b-instruct"
```

### Cost Limits (`config/limits.yaml`)

```yaml
limits:
  max_translation_cost_usd: 1.00   # Per-document hard cap
  max_pdf_size_mb: 50
cost_estimation:
  script_token_multipliers:
    Devanagari: 2.5
    Tamil: 3.0
    Latin: 1.0
```

### Prompt Templates (`config/prompts.yaml`)

All LLM prompts are stored here. Change the system/user templates to adjust translation style without code changes.

---

## Observability

Translation Studio ships a full production observability stack covering all four pillars.

### Architecture

```
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
        │                                   Prometheus ◄── Grafana
        │
        └─── Sentry SDK ───────────────► Sentry (exceptions)
```

Every trace span, log record, and metric is correlated via `trace_id` — click from a Grafana panel → log stream → Tempo trace waterfall in a single click.

### Observability Services

| Service | Image | URL | Purpose |
|---|---|---|---|
| `grafana` | `grafana/grafana:10.4.2` | http://localhost:3000 | Unified dashboards (no login in dev) |
| `prometheus` | `prom/prometheus:v2.52.0` | http://localhost:9090 | Metrics storage & query |
| `loki` | `grafana/loki:3.0.0` | — | Log aggregation |
| `tempo` | `grafana/tempo:2.4.2` | — | Distributed trace storage |
| `otel-collector` | `otel/opentelemetry-collector-contrib:0.100.0` | :4318 OTLP HTTP | Receives OTel, routes to Tempo |
| `promtail` | `grafana/promtail:3.0.0` | — | Tails container logs → Loki |

### Grafana Dashboard

The **Translation Studio — Overview** dashboard is auto-provisioned at startup and contains five sections:

| Section | Key Panels |
|---|---|
| HTTP / API | Request rate, error rate (5xx), p50/p95/p99 latency, active jobs |
| Translation Providers | Requests/s by provider & status, p95 latency, cumulative cost (USD), cache hit rate |
| OCR | Pages/s by status, p95 latency, failures |
| Rendering & Visual QA | Render latency, layout overflow events, QA score gauge |
| Validation | Failures by check type, pipeline duration p50/p95 |

### Structured Logging

All log output is JSON (structlog), written to stdout and collected by Promtail → Loki. Every record includes `trace_id` and `span_id` when an OTel span is active.

```json
{
  "event": "pipeline_completed",
  "service": "translation-studio-api",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "document_id": "abc-123",
  "qa_score": 0.94,
  "cost_usd": 0.0021,
  "duration_ms": 8342.5,
  "level": "info",
  "timestamp": "2026-10-24T18:12:00.000000Z"
}
```

```python
from packages.observability.logging import get_logger
logger = get_logger(__name__)
logger.info("ocr_completed", page=3, confidence=0.97, provider="bodhan")
```

### Distributed Tracing

Auto-instrumented: FastAPI, httpx (Bodhan / OpenRouter calls), SQLAlchemy, Redis. Manual spans wrap every major pipeline stage:

```
document_translation_pipeline
  ├── parse_pdf
  ├── ocr_fallback
  ├── cost_guard
  ├── translate_document
  │     └── translate_node  (per STU unit)
  ├── render_pdf
  ├── visual_qa
  └── store_artifacts
```

### Metrics Reference

All metrics exposed at `GET /metrics`.

| Metric | Type | Labels | Description |
|---|---|---|---|
| `http_requests_total` | Counter | method, endpoint, status_code | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | method, endpoint | Request duration |
| `http_errors_total` | Counter | method, endpoint | 5xx responses |
| `active_jobs` | Gauge | — | Running translation jobs |
| `documents_processed_total` | Counter | status | Documents completed |
| `pipeline_duration_seconds` | Histogram | status | End-to-end pipeline duration |
| `translation_requests_total` | Counter | provider, source_language, target_language, status | Translation dispatches |
| `translation_latency_seconds` | Histogram | provider | Per-request latency |
| `translation_provider_failures_total` | Counter | provider, failure_code | Provider-side failures |
| `translation_cost_usd_total` | Counter | provider | Cumulative cost |
| `translation_cache_hits_total` | Counter | — | Redis/memory cache hits |
| `translation_retries_total` | Counter | provider | Retry attempts |
| `routing_decisions_total` | Counter | provider, reason | Routing policy decisions |
| `ocr_pages_total` | Counter | provider, status | Pages sent to OCR |
| `ocr_latency_seconds` | Histogram | provider | OCR round-trip latency |
| `render_latency_seconds` | Histogram | — | PDF render duration |
| `render_failures_total` | Counter | failure_code | Render failures |
| `layout_overflow_total` | Counter | — | Text overflow events |
| `font_missing_glyph_total` | Counter | script | Missing glyph events |
| `visual_qa_score` | Histogram | — | QA score distribution (target ≥ 0.80) |
| `visual_qa_failures_total` | Counter | failure_code | Visual QA failure types |
| `pipeline_duration_seconds` | Histogram | status | End-to-end pipeline duration |
| `validation_failures_total` | Counter | check_type | Invariant validation failures |

### Exception Tracking (Sentry)

Set `SENTRY_DSN` in `.env` to enable. Sensitive data (`pdf_bytes`, `source_text`, `translated_text`, API keys) is redacted by a `before_send` hook before any payload is transmitted.

### Observability Configuration

| Variable | Default | Description |
|---|---|---|
| `OTEL_ENABLED` | `false` | Enable OTel tracing export |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | OTLP HTTP collector endpoint |
| `SENTRY_DSN` | _(empty)_ | Sentry project DSN (leave blank to disable) |
| `LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `SERVICE_NAME` | `translation-studio-api` | OTel `service.name` resource attribute |

> **Local dev without Docker Compose:** Set `OTEL_ENABLED=false` to disable trace export. Structured logging and `/metrics` remain active regardless.

---

## Testing

```bash
# Run all tests
PYTHONPATH="" .venv/bin/pytest tests -v

# Run a specific test file
PYTHONPATH="" .venv/bin/pytest tests/test_protected_content.py -v
```

All tests use mock providers and in-memory storage — no API keys or Docker required.

---

## Documentation

| Document | Description |
|---|---|
| [HLD.md](HLD.md) | High Level Design — architecture, components, data flows, NFRs |
| [LLD.md](LLD.md) | Low Level Design — module internals, class interfaces, DB schema, metrics, spans |
| [README.md](README.md) | This file — quickstart, API reference, observability guide |

---

## Visual QA Score

The **Visual QA score** is a composite float in `[0.0, 1.0]` computed after every translation:

- **Boundary score** = 1 − (out-of-bounds node count / total node count)
- **Glyph score** = 1 − (glyph-verification failures / sampled nodes)
- **Composite** = `min(boundary_score, glyph_score)`
- Capped at **0.5** if any critical error is detected (`BLANK_PAGE`, `SENTINEL_LEAK`)

A score **≥ 0.80** = PASS. The score is returned in the translate API response and recorded in the `VISUAL_QA_SCORE` Prometheus histogram.
