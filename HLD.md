# Translation Studio — High Level Design (HLD)

> **Version:** 1.0 | **Date:** October 2026

---

## 1. Executive Summary

Translation Studio is a **production-grade, structure-preserving document translation platform** designed for Indic and multilingual workflows. It accepts PDF documents, extracts a high-fidelity Document Intermediate Representation (IR), routes translation deterministically to specialised AI providers, validates linguistic and layout invariants, and re-renders pixel-accurate translated PDFs using OpenType Complex Text Layout (CTL) shaping.

---

## 2. Goals and Non-Goals

### Goals
- Accept arbitrary PDFs (digital, scanned, or mixed) and produce translated PDFs that preserve original layout, typography, and reading order.
- Support all major Indic scripts (Devanagari, Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati, Gurmukhi) via Bodhan AI APIs.
- Provide a prompt-edit interface for refining individual translated sections.
- Full observability stack (structured logs, distributed traces, Prometheus metrics, Sentry).
- Script-aware cost budgets per translation request.
- Single `docker compose up` local stack with no external dependencies.

### Non-Goals
- Real-time streaming translation (synchronous in v1).
- Non-PDF input formats (DOCX, PPTX) in v1.
- Multi-tenant authentication in v1.

---

## 3. System Context

```
              ┌──────────────────────────────────────┐
              │           External Clients           │
              │  (Browser / CLI / Integration Tests) │
              └────────────────┬─────────────────────┘
                               │ HTTP REST
              ┌────────────────▼─────────────────────┐
              │         Translation Studio           │
              │  ┌──────────┐  ┌───────────────────┐ │
              │  │  FastAPI │  │  Celery Worker    │ │
              │  │  Gateway │  │  (pipeline tasks) │ │
              │  └──────────┘  └───────────────────┘ │
              │  ┌──────────────────────────────────┐ │
              │  │       Observability Stack        │ │
              │  │  Loki · Tempo · Prometheus ·     │ │
              │  │  OTel Collector · Grafana        │ │
              │  └──────────────────────────────────┘ │
              └──────┬─────────────┬─────────────────┘
                     │             │
         ┌───────────▼──┐   ┌──────▼──────────┐
         │  Bodhan AI   │   │  OpenRouter API  │
         │  (OCR + MT)  │   │  (General LLMs)  │
         └──────────────┘   └─────────────────┘
```

---

## 4. Architecture Overview

| Tier | Components | Role |
|---|---|---|
| **Ingress** | FastAPI Gateway, REST routes | Request handling, serialisation |
| **Orchestration** | `DocumentTranslationPipeline`, `SectionEditPipeline` | Stage sequencing, span management, metrics |
| **Domain Packages** | `packages/*` | Pure business logic, dependency-injected I/O |
| **Infrastructure** | PostgreSQL, Redis, Object Store | Persistence, caching, artefacts |
| **Observability** | OTel SDK, structlog, prometheus-client, Sentry | Telemetry collection and export |

---

## 5. Major Components

### 5.1 API Gateway (`apps/api`)

Stateless FastAPI application. All heavy lifting delegated to the pipeline layer.

| Endpoint | Method | Purpose |
|---|---|---|
| `/healthz` | GET | Health probe |
| `/metrics` | GET | Prometheus scrape |
| `/api/v1/documents/upload` | POST | Accept PDF, classify, store original |
| `/api/v1/documents/{id}/translate` | POST | Trigger full translation pipeline |
| `/api/v1/documents/{id}/nodes/{node_id}/edit` | POST | Prompt-edit a single node |
| `/api/v1/documents/{id}/edit` | POST | Prompt-edit a selection |
| `/api/v1/documents/{id}/versions/{vid}/pdf` | GET | Download translated PDF |
| `/api/v1/documents/{id}/versions/{vid}/structure` | GET | Inspect Document IR as JSON |
| `/api/v1/documents/{id}/costs` | GET | Cost ledger summary |

Middleware stack (outer → inner):
1. **CORS** — allows cross-origin browser access in development.
2. **RequestLoggingMiddleware** — one structured JSON log per request.
3. **MetricsMiddleware** — `http_requests_total`, `http_request_duration_seconds` per normalised endpoint.

### 5.2 Document Translation Pipeline (`apps/worker/tasks/pipeline.py`)

Core orchestration; 7 sequential stages, each wrapped in an OTel span:

```
Stage 1 — Parse PDF → Document IR
Stage 2 — OCR Fallback (scanned/empty pages → Bodhan OCR)
Stage 3 — Cost Guard (pre-flight token budget check)
Stage 4 — Route & Translate (STU grouping → provider dispatch → invariant validation)
Stage 5 — Render (Document IR → PDF via PyMuPDF + HarfBuzz CTL)
Stage 6 — Visual QA (boundary containment + glyph verification)
Stage 7 — Store Artefacts (IR JSON + PDF → object store, cost ledger)
```

### 5.3 PDF Parser (`packages/document/parser`)

Uses **PyMuPDF** to extract text blocks with per-span bounding boxes, fonts, sizes, colours, reading order, rotation; math regions (CMR/STIX/LMMATH fonts); table cell grids; and footnotes. Key parsing features include:
- **Searchable Scanned PDF Detection:** In addition to text length, the parser inspects embedded images. If any image occupies > 20% of the page area, the page is recognized as containing scanned content, ensuring searchable scanned PDFs (scanned pages with an invisible OCR text layer) are classified as `MIXED` or `SCANNED` rather than purely digital.
- **Dynamic Typography Profiling:** Computes character-weighted body font size (`_body_size`) and dynamic, scale-independent heading thresholds (`max(12.5, doc_body * 1.15)`).
- **Spatial Alignment & Centering:** Evaluates horizontal alignment (`_aligned`) and center symmetry (`_same_center`) to bridge multi-line paragraphs across extraction blocks and flag centered headers/titles (`centered = True`).
- **Proportional Margins:** Header/footer bounds are dynamically computed based on page height (top 6% for headers, bottom 6% for footers) instead of fixed point offsets.

### 5.4 Document Intermediate Representation (IR)

Hierarchical Pydantic model:

```
DocumentIR
  └── PageNode[]
        └── DocumentNode[]  (PARAGRAPH, HEADING, TABLE, FIGURE, …)
              ├── BoundingBox (x0, y0, x1, y1 in PDF points)
              ├── NodeStyle   (font, size, weight, colour, alignment)
              ├── TextSpan[]  (sub-span rich text)
              ├── source_text / translated_text
              ├── translation_status / validation_status
              └── metadata    (math_regions, stu, protected_tokens, centered, …)
```

### 5.5 Semantic Translation Units (STU)

Adjacent layout nodes forming one paragraph are grouped before translation using vertical gap heuristics (gap ≤ font_size), horizontal alignment, and font-size compatibility thresholds — preventing mid-sentence layout breaks from degrading translation quality.

### 5.6 Protected Content Masking

`protect()` replaces CLI commands, URLs, email addresses, file paths, product names, `snake_case` identifiers, and version strings with Unicode bracket placeholders (`⟦P1⟧`) before LLM dispatch. `validate_and_restore()` verifies exact one-to-one restoration; aborts if any token is missing, duplicated, or leaked.

### 5.7 Provider Routing (`packages/routing`)

Deterministic config-driven router (`routing.yaml`):

```
Priority 1: User-requested provider (if circuit is closed)
Priority 2: Routing table match (source → target → provider)
Priority 3: Default fallback (OpenRouter + meta-llama/llama-3.3-70b)
```

| Provider | Pairs | API Type | Notes |
|---|---|---|---|
| **Bodhan** | en→{hi,ta,te,kn,ml,bn,mr,gu,pa} | Indic MT + OCR | Primary high-performance Indic MT pipeline |
| **OpenRouter** | All pairs | OpenAI-compatible chat | General multilingual LLM fallback |

> **Production Language Direction:** The verified high-quality production flow focuses on English to Indic language pairs. Indic-to-English translation is routed through general LLM fallback when enabled.

### 5.8 Cost Guard (`packages/translation/cost_guard`)

Pre-flight token budget check with script-aware multipliers (Devanagari ×2.5, Tamil/Telugu/Kannada/Malayalam ×3.0, Latin ×1.0). Raises `CostLimitExceededError` if projected spend exceeds the per-document limit (default $1.00, configurable in `limits.yaml`).

### 5.9 PDF Renderer (`packages/rendering`)

Three-path renderer on PyMuPDF:

| Mode | Trigger | Strategy |
|---|---|---|
| **Digital** | `DIGITAL` | Apply redaction annotations to clear source text layers; re-flow translated text at exact coordinates |
| **Overlay** | `SCANNED` or page image > 20% area | Contiguous spatial text masking over source text blocks; insert translated text story with white background |
| **Mixed** | `MIXED` | Digital reflow on pure text pages, overlay with white masking on scanned/image pages |

#### Overlay Mode & Scanned Document De-Ghosting
In scanned documents and searchable PDFs, standard PDF text redactions only remove invisible text layers, leaving the rasterized source text visible behind the translated text. The renderer resolves this via:
1. **Contiguous Text Masking:** Replaces redactions with opaque white rectangles (`color=(1, 1, 1), fill=(1, 1, 1), overlay=True`) directly over the detected source text boxes, leaving figures, stamps, and non-text visual elements untouched.
2. **Spatial Box Merging:** Adjacent bounding boxes in the same column (vertical gap ≤ 14pt, horizontal overlap > 40%) are spatially merged prior to masking to bridge synthetic OCR line gaps.
3. **Opaque Text Container:** Translated text HTML containers apply `background-color: #ffffff;` in overlay mode, ensuring zero raster bleed-through.
4. **Centering Preservation:** Retains centered alignment and bounds for titles and headings flagged during parsing.

`FontRegistry` selects Google Noto fonts per script. PyMuPDF HTML story renderer + HarfBuzz performs OpenType CTL shaping. `LayoutEngine` shrinks font up to 15% to fit translated text in source bounding box.

### 5.10 Validation Layer (`packages/validation`)

**InvariantValidator** (deterministic): numbers, URLs, email addresses must be preserved verbatim or in equivalent Indic numerals.

**VisualQAValidator** (PDF inspection): boundary containment, blank page detection, glyph verification, sentinel/placeholder leak detection.  
Score = `min(boundary_score, glyph_score)`, capped at 0.5 on critical errors. Score ≥ 0.80 = PASS.

### 5.11 Translation Cache (`packages/storage/redis`)

SHA-256 keyed on (source_text | src_lang | tgt_lang | provider | model | prompt_version). Two-tier: Redis primary (30-day TTL) → in-memory dict fallback.

### 5.12 Section & Selection Editing

Users refine individual nodes or arbitrary rectangular/text selections via natural language prompts without re-running the full pipeline. The edit pipeline loads IR, locates selected nodes, checks feasibility, dispatches refinement LLM call, validates output, saves a new version (parent→child version graph), and re-renders only affected pages.

#### Edit Feasibility & Soft-Gate (`packages/editing/feasibility.py`)
- **In-Text Formatting Support:** Prompts explicitly permit in-text structural adjustments (adding bullet points `•`, numbered lists, line breaks, rephrasing, simplification) as valid text rewrites (`feasible: true`, category `"ok"`).
- **Option 2 Soft-Gate:** If the initial triage LLM flags `layout` because of bulleting or list formatting, but the selection contains valid editable text nodes (paragraphs, list items, headings) and no locked content (math, code, images), the gate overrides the rejection (`soft_layout_gate`). Downstream HarfBuzz `LayoutEngine` dynamically fits and wraps the text, and `VisualQAValidator` verifies bounding-box containment.

### 5.13 Observability Stack

| Pillar | Technology | Path |
|---|---|---|
| Structured Logging | structlog JSON | stdout → Promtail → Loki |
| Distributed Tracing | OpenTelemetry SDK | OTLP HTTP → OTel Collector → Tempo |
| Metrics | prometheus-client | `/metrics` → Prometheus → Grafana |
| Exceptions | Sentry SDK | Direct HTTPS → sentry.io |

- **Metric Pre-seeding (`init_metrics()`):** Base metric series (`translation_requests_total`, `translation_cost_usd_total`, `ocr_pages_total`, etc.) are pre-initialized with default provider dimensions at startup, preventing missing series in Prometheus on fresh containers.
- **Zero-Failure PromQL Handling:** Failure and event panels in Grafana employ PromQL `or vector(0)` fallbacks to plot `0` rather than displaying `"No data"` when zero errors occur.
- **Relative Time Tracking:** Dashboards use relative time ranges (`from=now-15m&to=now` or `from=now-3h&to=now`) to continuously display live telemetry.
- **Trace-Log Correlation:** Every log record inside an active OTel span carries `trace_id` + `span_id` for one-click Grafana → Tempo correlation.

### 5.14 Web Studio Interface (`apps/web`)

Modern interactive web frontend providing:
- **Theme Toggle:** Dark and Light mode switching with local storage persistence (`ts_theme`).
- **Language Controls:** Source and target language selection with instant language swap button (`btnSwapLang`).
- **Interactive Stepper:** Live animated pipeline progress stepper (`pipeline-stepper`) showing active translation stages.
- **Cost Inspector:** Real-time cost indicator with tooltip breakdown for translation and prompt-edit spend in USD.
- **Selection Tools & History:** Side-by-side translated vs original preview, visual bounding box selection, quick prompt chips, and version history DAG navigation.

---

## 6. Data Flow: Document Translation

```
Client
  │  POST /api/v1/documents/upload
  ▼
API Gateway ──► PDFClassifier → store original → return document_id
  │
  │  POST /api/v1/documents/{id}/translate
  ▼
DocumentTranslationPipeline
  ├─[1] PyMuPDFParser ──► DocumentIR
  ├─[2] BodhanOCRProvider ──► fill empty pages
  ├─[3] CostGuard ──► abort if over budget
  ├─[4] STU Grouper → per run:
  │       ├── protect() → mask spans
  │       ├── TranslationCache.get() → cache hit? done
  │       ├── TranslationRouter.route() → RoutingDecision
  │       ├── Provider.translate()
  │       ├── validate_and_restore()
  │       ├── InvariantValidator
  │       ├── TranslationCache.set()
  │       └── SemanticQA.check_unit() + llm_review() (flagged units)
  ├─[5] PDFRenderer → rendered_pdf_bytes
  ├─[6] VisualQAValidator → (valid, errors, score)
  └─[7] ObjectStore.put(IR + PDF) + CostLedger.record()
              └── return {version_id, qa_score, cost_usd}
```

---

## 7. Data Flow: Section Edit

```
Client  POST /api/v1/documents/{id}/nodes/{node_id}/edit
  ▼
SectionEditPipeline
  ├── Load DocumentIR (current version)
  ├── Locate DocumentNode by node_id
  ├── protect() → PromptManager refinement prompt
  ├── OpenRouter.chat_completion()
  ├── validate_and_restore()
  ├── Save new IR version (parent → child)
  ├── Re-render affected pages
  └── return {version_id, edited_translation, status}
```

---

## 8. Deployment Architecture

```
┌─────────────────── docker-compose network ────────────────────┐
│                                                                │
│  api:8000 (FastAPI)    worker (Celery*)    redis:6379          │
│         └──────────────────┘                                   │
│                       postgres:5432                            │
│                                                                │
│  ─────────── Observability ──────────────────────────────────  │
│  otel-collector:4318   promtail (docker.sock)                 │
│       │                       │                               │
│  tempo:3200              loki:3100                            │
│       └──────────┬────────────┘                               │
│              grafana:3000          prometheus:9090             │
└────────────────────────────────────────────────────────────────┘
```

> `*` In v1, the pipeline executes synchronously inside the API process. Celery is wired for production scale-out.

---

## 9. Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| API Framework | FastAPI + Uvicorn | Async, OpenAPI, Pydantic v2 |
| PDF Parsing & Rendering | PyMuPDF (fitz) | Span extraction, math fonts, HarfBuzz CTL |
| Domain Models | Pydantic v2 | Fast, typed, serialisable IR |
| Task Queue | Celery + Redis | Distributed job queue |
| Database | PostgreSQL 16 / SQLite | Version metadata; SQLite fallback for local dev |
| Tracing | OpenTelemetry SDK | Vendor-neutral OTLP |
| Metrics | prometheus-client | Standard Prometheus scraping |
| Logging | structlog | Structured JSON records |
| Exceptions | Sentry SDK | Error aggregation |
| Log Backend | Loki + Promtail | Container stdout collection |
| Trace Backend | Tempo | TraceQL, Grafana-native |
| Dashboard | Grafana | Cross-datasource correlation |

---

## 10. Non-Functional Requirements

| Requirement | Target | Mechanism |
|---|---|---|
| Visual QA | score ≥ 0.80 | VisualQAValidator post-render |
| Cost control | ≤ $1.00/doc | CostGuard + `limits.yaml` |
| Availability | Provider circuit-breaker | Bodhan → OpenRouter fallback |
| Observability | Traces correlated to logs + metrics | OTel `trace_id` in all log records |
| Testability | All stages independently unit-testable | Constructor-injected dependencies |
| Portability | Zero external deps for local dev | SQLite, in-memory cache, local file store |

---

## 11. Security

- API keys loaded from env vars, never logged or returned in errors.
- Sentry `before_send` redacts `pdf_bytes`, `source_text`, `translated_text`, `api_key`.
- Protected content masking prevents prompt-injection leakage of code/URLs.
- PDF uploads capped at 50 MB; Pydantic v2 enforces request schemas.

---

## 12. Failure Modes

| Failure | Detection | Mitigation |
|---|---|---|
| Provider API timeout | httpx timeout | Retry ×3, then circuit-breaker |
| Protected token not restored | `validate_and_restore` errors | Retranslate; mark node FAILED |
| OCR API unavailable | Exception | Page marked scanned; fallback text |
| Redis connection loss | Socket timeout | Fallback to in-process memory cache |
| PostgreSQL unavailable | `init_db` exception | Auto-fallback to SQLite |
| PDF render failure | Exception in render stage | `RENDER_ERROR` metric; propagate |
| Visual QA failure | score < 0.80 | Logged as warning; document delivered with score |

---

## 13. Future Roadmap

- **Async Celery pipeline** — decouple long translation jobs from HTTP lifecycle.
- **S3/MinIO object store** — multi-instance cloud deployment.
- **Streaming progress API** — WebSocket per-page status updates.
- **User authentication** — JWT-based multi-tenant access.
- **Language auto-detection** — source language inference when not provided.
- **Glossary management API** — per-project terminology CRUD.
