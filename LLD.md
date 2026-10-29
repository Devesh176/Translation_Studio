# Translation Studio — Low Level Design (LLD)

> **Version:** 1.0 | **Date:** October 2026  
> **Scope:** Module internals, class interfaces, database schemas, metric names, tracing spans, config contracts, and algorithm notes.

---

## 1. Repository Layout

```
translation_studio/
├── apps/
│   ├── api/
│   │   ├── main.py                   # FastAPI app, lifespan, middleware, routes, /metrics
│   │   ├── dependencies.py           # FastAPI Depends factories
│   │   ├── routes/
│   │   │   ├── documents.py          # Upload, translate, download, structure endpoints
│   │   │   ├── sections.py           # Node-level and selection prompt-edit endpoints
│   │   │   └── costs.py              # Cost ledger endpoint
│   │   └── schemas/
│   │       └── document.py           # Pydantic request/response models
│   └── worker/
│       └── tasks/
│           ├── pipeline.py           # DocumentTranslationPipeline (7 stages)
│           └── section_edit.py       # SectionEditPipeline
├── packages/
│   ├── core/
│   │   ├── domain/
│   │   │   ├── node.py               # DocumentIR, PageNode, DocumentNode, NodeStyle, …
│   │   │   └── version.py            # DocumentVersion
│   │   ├── config_loader.py          # YAML config loaders (routing, limits, prompts, glossary)
│   │   ├── events.py                 # Domain event stubs
│   │   └── exceptions.py            # CostLimitExceededError, InvalidPDFError, …
│   ├── document/
│   │   ├── parser/
│   │   │   ├── pymupdf_parser.py     # PyMuPDFParser — extract IR from PDF bytes
│   │   │   └── pdf_classifier.py    # PDFClassifier — DIGITAL / SCANNED / MIXED
│   │   └── ir/
│   │       └── serializer.py         # IRSerializer.to_json / from_json
│   ├── providers/
│   │   ├── base.py                   # TranslationProvider ABC, TranslationRequest/Response
│   │   ├── bodhan/
│   │   │   ├── client.py             # BodhanClient — httpx async REST client
│   │   │   ├── translation.py        # BodhanTranslationProvider
│   │   │   └── ocr.py               # BodhanOCRProvider
│   │   └── openrouter/
│   │       ├── client.py             # OpenRouterClient — OpenAI-compatible httpx client
│   │       └── translation.py        # OpenRouterTranslationProvider
│   ├── routing/
│   │   ├── translation_router.py     # TranslationRouter — config-driven routing
│   │   ├── language.py               # normalize_language_code, detect_unicode_script
│   │   ├── ocr_router.py             # OCR provider selection
│   │   └── policy.py                 # RoutingDecision dataclass
│   ├── translation/
│   │   ├── cost_guard.py             # CostGuard — script-aware pre-flight budget check
│   │   ├── chunker.py                # TranslationChunker — token-safe text splitting
│   │   ├── prompts.py                # PromptManager — YAML-backed template renderer
│   │   ├── normalizer.py             # TextNormalizer — whitespace/encoding cleanup
│   │   └── protected_content.py     # protect() / validate_and_restore()
│   ├── semantic/
│   │   ├── units.py                  # build_units() — STU grouping with GroupingConfig
│   │   ├── segments.py               # split_segments(), glossary_findings()
│   │   └── qa.py                     # check_unit(), llm_review()
│   ├── validation/
│   │   ├── invariants.py             # InvariantValidator
│   │   └── visual.py                 # VisualQAValidator
│   ├── rendering/
│   │   ├── pdf_renderer.py           # PDFRenderer — digital / overlay / mixed
│   │   ├── layout_engine.py          # LayoutEngine — font shrink + text wrap
│   │   ├── font_registry.py          # FontRegistry — script → Noto font mapping
│   │   └── text_measurement.py       # TextMeasurement — character-width wrap
│   ├── costs/
│   │   └── ledger.py                 # CostCollector, CostLedger, estimate_tokens
│   ├── editing/
│   │   ├── feasibility.py            # EditFeasibilityChecker
│   │   └── selection.py              # SelectionResolver — bbox / text selection
│   ├── storage/
│   │   ├── object_store/
│   │   │   └── local_store.py        # LocalFileObjectStore
│   │   ├── postgres/
│   │   │   ├── db.py                 # SQLAlchemy engine, init_db, get_db_session
│   │   │   └── models.py             # ORM models (Document, Version, …)
│   │   └── redis/
│   │       └── cache.py              # TranslationCache (Redis + memory fallback)
│   └── observability/
│       ├── __init__.py               # Public re-exports
│       ├── logging.py                # get_logger() — structlog configured logger
│       ├── tracing.py                # get_tracer() — OTel TracerProvider setup
│       ├── metrics.py                # All prometheus_client metric objects
│       ├── sentry.py                 # init_sentry(), before_send redaction hook
│       └── middleware.py             # MetricsMiddleware, RequestLoggingMiddleware
├── config/
│   ├── routing.yaml                  # Provider routing rules
│   ├── limits.yaml                   # Cost limits, token multipliers
│   ├── prompts.yaml                  # LLM prompt templates
│   ├── glossary/                     # Per-language glossary YAML files
│   ├── prometheus.yaml               # Prometheus scrape config
│   ├── loki.yaml                     # Loki configuration
│   ├── tempo.yaml                    # Tempo configuration
│   ├── otel-collector.yaml           # OTel Collector pipelines
│   ├── promtail.yaml                 # Promtail log scrape config
│   └── grafana/
│       ├── provisioning/
│       │   ├── datasources/datasources.yaml
│       │   └── dashboards/dashboards.yaml
│       └── dashboards/
│           └── translation_studio_overview.json
└── tests/                            # pytest unit + integration tests
```

---

## 2. Core Domain Models (`packages/core/domain/node.py`)

### 2.1 Enums

```python
class NodeType(str, Enum):
    DOCUMENT | PAGE | HEADER | FOOTER | HEADING | PARAGRAPH
    LIST_ITEM | CODE_BLOCK | TABLE | TABLE_ROW | TABLE_CELL
    TABLE_CAPTION | FIGURE | EQUATION | FOOTNOTE_REFERENCE | FOOTNOTE

class TranslationStatus(str, Enum):
    PENDING | IN_PROGRESS | TRANSLATED | EDITED | VALIDATED | FAILED | SKIPPED
```

### 2.2 Key Models

| Model | Key Fields | Notes |
|---|---|---|
| `BoundingBox` | `x0, y0, x1, y1: float` | PDF points; `.width`, `.height` properties |
| `NodeStyle` | `font_family, font_size, font_weight, is_italic, is_underline, color_rgb, line_height, alignment` | Defaults to NotoSans-Regular 11pt |
| `TextSpan` | `span_id, text, translated_text, bbox, style, is_bold, is_italic, link_url` | Sub-span rich text |
| `DocumentNode` | `node_id, parent_id, page_id, page_number, type, bbox, rotation, reading_order, style, source_text, translated_text, source_hash, translation_hash, language, target_language, confidence, z_index, spans, translation_status, validation_status, render_status, metadata, edit_history` | Core IR unit |
| `TableCellNode` | extends DocumentNode + `row_idx, col_idx, row_span, col_span, is_header` | |
| `TableNode` | extends DocumentNode + `num_rows, num_cols, cells: List[TableCellNode], caption` | |
| `FootnoteNode` | extends DocumentNode + `reference_id, footnote_number` | |
| `PageNode` | `page_id, page_number, width, height, rotation, is_scanned, ocr_confidence, nodes: List[DocumentNode]` | A4 default 595.276 × 841.890 pt |
| `DocumentIR` | `document_id, version_id, parent_version_id, title, source_language, target_language, total_pages, classification, pages, metadata` | Root IR object; `find_node(id)`, `get_all_nodes()` helpers |

---

## 3. PDF Parsing (`packages/document/parser/pymupdf_parser.py`)

### 3.1 Algorithm: `PyMuPDFParser.parse(pdf_bytes, document_id) → DocumentIR`

1. Open PDF bytes via `fitz.open(stream=pdf_bytes)`.
2. For each page:
   a. Extract all text blocks via `page.get_text("rawdict")`.
   b. Identify math font spans using `_MATH_FONT_RE` (CMR, STIX, LMMATH, CambriaMath, etc.) and fold adjacent math spans into `⟨MATH_ID⟩` marker tokens, saving the clip bbox for rendering.
   c. Classify each text block as `PARAGRAPH`, `HEADING`, `LIST_ITEM`, `CODE_BLOCK`, `TABLE`, `FOOTNOTE`, `HEADER`, or `FOOTER` based on font size, position, bullet characters, and numbering patterns.
   d. Cluster table spans into `TableCellNode` grids.
   e. Assign `reading_order` index using top→bottom, left→right sort.
   f. Detect script/language from Unicode block ranges.
3. Build and return `DocumentIR`.

### 3.2 Math Token Encoding

- Math font spans are replaced with `\ue000{id}\ue001` markers (Unicode Private Use Area).
- `metadata["math_regions"]` stores `{id, bbox, baseline, size}` for later rendering.
- `strip_math(text)` removes markers before cost/token estimation.

### 3.3 PDF Classifier

```python
class PDFClassifier:
    def classify(self, fitz_doc) -> str:
        # Returns "DIGITAL", "SCANNED", or "MIXED"
        # SCANNED: majority of pages have no extractable text blocks
        # MIXED: some pages are text, some are image-only
```

---

## 4. Protected Content Masking (`packages/translation/protected_content.py`)

### 4.1 `protect(text: str) → ProtectedText`

Applies inline regex patterns in priority order:
1. Whole-line CLI/YAML detection via `_CODE_LINE_RE` / `_YAML_LINE_RE`.
2. Inline patterns (URLs, emails, file paths, `key=value` pairs, `snake_case`, versioned identifiers).
3. Product name list (Docker, Python, NumPy, conda, pip, etc.).

Each match is replaced with `⟦P{N}⟧` and the original stored in a `mapping` dict.

### 4.2 `validate_and_restore(translated, mapping) → (str, List[str])`

- A "loose" regex `_LOOSE_TOKEN_RE` normalises slightly malformed tokens before validation.
- Checks each expected token appears exactly once in the translated text.
- Reports `PROTECTED_TOKEN_MISSING`, `PROTECTED_TOKEN_DUPLICATED`, `UNKNOWN_PLACEHOLDER`, `PLACEHOLDER_LEAK`.
- Restores all tokens in order.

---

## 5. Semantic Translation Units (`packages/semantic/units.py`)

### 5.1 `build_units(ir: DocumentIR, cfg: GroupingConfig) → List[List[DocumentNode]]`

For each page, iterates nodes sorted by `reading_order`. A node is eligible for grouping (`_groupable()`) if:
- `type == PARAGRAPH`
- Non-empty text
- Not math-only, code, or OCR-selected
- Not numeric-heavy (>15% digits/symbols)

Two adjacent nodes are merged into one STU if:
- Vertical gap ≤ `cfg.max_gap_factor × font_size`
- Left edges within `cfg.x_tolerance_factor × font_size`
- Font sizes within `cfg.size_tolerance` ratio
- Preceding node's text does not end in a terminal punctuation character (`.?!:;।॥…`)

Returns a list of runs where single-element runs are passed through as-is.

### 5.2 STU Metadata

Lead node gets `metadata["stu"] = {unit_id, role: "lead", member_ids: [...], union_bbox, grouping: [...]}`.  
Member nodes get `metadata["stu"] = {unit_id, role: "member", lead_id}` and are set to `TRANSLATED` immediately with empty `translated_text` (populated by splitting the lead's translated output proportionally).

---

## 6. Provider Routing (`packages/routing`)

### 6.1 `TranslationRouter.route(src, tgt, user_provider, circuit_open) → RoutingDecision`

```python
@dataclass
class RoutingDecision:
    source_language: str
    target_language: str
    provider: str
    model: Optional[str]
    reason: str   # "user_requested_provider" | "explicit_supported_language_pair" | "default_fallback" | "circuit_open_fallback"
    policy_version: str
```

Routing table is loaded once from `config/routing.yaml` at `__init__` time and stored as a `dict[provider, Set[Tuple[src, tgt]]]` for O(1) lookup.

### 6.2 Language Normalisation (`packages/routing/language.py`)

`normalize_language_code(code)` maps variants (e.g., `"hindi"`, `"Hindi"`, `"HI"`) to ISO 639-1 codes. `detect_unicode_script(text)` returns the dominant Unicode block (Devanagari, Tamil, Latin, etc.) by character frequency.

---

## 7. Translation Pipeline Node Processing

### 7.1 `_translate_node(node, document_id, src_lang, tgt_lang, …)`

```
1. Skip if node type is CODE_BLOCK or text is empty.
2. Check source_hash == translation_hash → skip (already translated, identical input).
3. protect(node.source_text or text_override) → ProtectedText
4. TranslationCache.get(cache_key) → cache hit → validate_and_restore → done
5. TranslationRouter.route() → RoutingDecision
6. ROUTING_DECISIONS_TOTAL.labels(provider, reason).inc()
7. dispatch to provider:
   - Bodhan: BodhanTranslationProvider.translate(request)
   - OpenRouter: OpenRouterTranslationProvider.translate(request)
8. TRANSLATION_LATENCY_SECONDS.labels(provider).observe(duration)
9. TRANSLATION_REQUESTS_TOTAL.labels(provider, src, tgt, status).inc()
10. validate_and_restore() → errors?
    - Some errors (MISSING/DUPLICATED): retry once, then mark FAILED
11. InvariantValidator.validate_numbers() + validate_urls_and_emails()
12. TranslationCache.set(cache_key, translated_text)
13. node.translated_text = translated_text
14. node.translation_status = TRANSLATED
15. costs.add(provider, model, input_tokens, output_tokens, cost_usd)
16. TRANSLATION_COST_USD_TOTAL.labels(provider).inc(cost_usd)
```

### 7.2 Retry Logic

- Up to 3 retries per node.
- Retry conditions: provider HTTP error (5xx), timeout, or protected token validation failure.
- `TRANSLATION_RETRIES_TOTAL.labels(provider).inc()` on each retry attempt.
- `TRANSLATION_PROVIDER_FAILURES_TOTAL.labels(provider, failure_code).inc()` on final failure.

---

## 8. Cost Tracking (`packages/costs/ledger.py`)

### 8.1 `CostCollector`

Accumulates `CostEntry` records during a single pipeline run:

```python
CostEntry = {
    kind: str,          # "translate" | "ocr" | "semantic_review"
    purpose: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,    # usd_for(in, out) or provider-reported
    estimated: bool,
}
```

`estimate_tokens(text)` uses word-count × 1.3 (BPE ratio) × 2.5 (Indic multiplier) as a conservative approximation.

### 8.2 `CostLedger`

Appended JSON array stored as `documents/{id}/costs.json` in the object store. Each entry adds `ts` (Unix timestamp) and `version_id`.

---

## 9. PDF Rendering (`packages/rendering/pdf_renderer.py`)

### 9.1 Digital Mode Algorithm

For each `DocumentNode` in `DocumentIR`:
1. Build HTML string with inline CSS (font-face, size, colour, weight, italic, alignment).
2. Inject math clip images at `⟨MATH_ID⟩` positions from saved crop bboxes.
3. Call `LayoutEngine.compute_layout_for_node()` → `(fitted_font_size, lines, needs_reflow)`.
4. If `needs_reflow` → record `LAYOUT_OVERFLOW_TOTAL.inc()`.
5. Create a PyMuPDF `Story` from the HTML, fit it into a rectangle matching the source bbox.
6. Draw the story onto a fresh PDF page layer.

**Glyph check:** after rendering, `FONT_MISSING_GLYPH_TOTAL.labels(script).inc()` if PyMuPDF reports missing glyphs.

### 9.2 Overlay Mode Algorithm

1. Stamp existing page as image background.
2. For each node, stamp translated text using `page.insert_htmlbox()` over the source bbox.
3. Transparency is applied to avoid covering background text.

### 9.3 `LayoutEngine.compute_layout_for_node()`

```
Tier 1 — In-place shrink:
  font_size := node.style.font_size
  while font_size >= min_font_size (= initial * 0.85):
      lines = TextMeasurement.wrap_text_to_width(text, bbox.width, font_size)
      required_height = len(lines) * (font_size * 1.25)
      if required_height <= bbox.height: return (font_size, lines, needs_reflow=False)
      font_size -= 0.5

Tier 2 — Cascade reflow (overflow):
  font_size = max(6.0, min_font_size)
  lines = wrap_text_to_width(text, bbox.width, font_size)
  return (font_size, lines, needs_reflow=True)
```

---

## 10. Visual QA (`packages/validation/visual.py`)

### 10.1 `VisualQAValidator.inspect_rendered_pdf(pdf_bytes, ir) → (bool, List[str], float)`

Checks (in order, scoring independently):

| Check | Penalty | Error Code |
|---|---|---|
| Boundary containment | per out-of-bounds node | `LAYOUT_OUT_OF_BOUNDS` |
| Blank page detection | if rendered page has <5 text chars but source had >50 | `BLANK_PAGE` |
| Glyph verification | if ASCII probe from translated text not found in extracted text | `MISSING_GLYPHS` |
| Sentinel leak | if `⟦`, `⟧`, `<<<`, `>>>` appear in extracted text | `SENTINEL_LEAK` |
| OCR confidence (scanned) | if mean OCR confidence < 0.70 | `LOW_OCR_CONFIDENCE` |

**Score formula:**
```
boundary_score = 1.0 - (out_of_bounds_count / total_node_count)
glyph_score    = 1.0 - (glyph_fail_count / sample_node_count)
composite_score = min(boundary_score, glyph_score)
# Cap at 0.5 if BLANK_PAGE or SENTINEL_LEAK present
```

---

## 11. Observability Package (`packages/observability/`)

### 11.1 `logging.py` — `get_logger(name) → BoundLogger`

Configures `structlog` with:
- `TimeStamper(fmt="iso")` — ISO 8601 timestamps.
- `add_log_level` — lowercase level string.
- `CallsiteParameterAdder` — file + line number.
- OTel context injector — injects `trace_id`, `span_id` from the active span.
- `JSONRenderer` — outputs compact JSON to stdout.

### 11.2 `tracing.py` — `get_tracer(name) → Tracer`

On first call, sets up a `TracerProvider` with:
- `Resource` attributes: `service.name`, `service.version`, `deployment.environment`.
- `OTLPSpanExporter` (HTTP) pointed at `OTEL_EXPORTER_OTLP_ENDPOINT` (default `http://otel-collector:4318`).
- `BatchSpanProcessor` with 5 s max export interval.
- Auto-instrumentation: FastAPI, httpx, SQLAlchemy, Redis.

Falls back to `NoOpTracer` if `OTEL_ENABLED=false` or if `opentelemetry` packages are absent.

### 11.3 `metrics.py` — Prometheus Metric Objects

| Metric Name | Type | Labels |
|---|---|---|
| `http_requests_total` | Counter | `method, endpoint, status_code` |
| `http_request_duration_seconds` | Histogram | `method, endpoint` |
| `http_errors_total` | Counter | `method, endpoint` |
| `active_jobs` | Gauge | — |
| `documents_processed_total` | Counter | `status` |
| `pipeline_duration_seconds` | Histogram | `status` |
| `translation_requests_total` | Counter | `provider, source_language, target_language, status` |
| `translation_latency_seconds` | Histogram | `provider` |
| `translation_provider_failures_total` | Counter | `provider, failure_code` |
| `translation_cost_usd_total` | Counter | `provider` |
| `translation_input_tokens_total` | Counter | `provider` |
| `translation_output_tokens_total` | Counter | `provider` |
| `translation_cache_hits_total` | Counter | — |
| `translation_cache_misses_total` | Counter | — |
| `translation_retries_total` | Counter | `provider` |
| `routing_decisions_total` | Counter | `provider, reason` |
| `ocr_pages_total` | Counter | `provider, status` |
| `ocr_latency_seconds` | Histogram | `provider` |
| `ocr_provider_failures_total` | Counter | `provider, failure_code` |
| `render_latency_seconds` | Histogram | — |
| `render_pages_total` | Counter | `status` |
| `render_failures_total` | Counter | `failure_code` |
| `layout_overflow_total` | Counter | — |
| `font_missing_glyph_total` | Counter | `script` |
| `visual_qa_score` | Histogram | — |
| `visual_qa_failures_total` | Counter | `failure_code` |
| `validation_failures_total` | Counter | `check_type` |

Histograms use default buckets. `visual_qa_score` uses `[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]`.

All metrics fall back to no-op stubs if `prometheus_client` is not installed.

### 11.4 `sentry.py` — `init_sentry()`

```python
def _before_send(event, hint):
    # Redacts sensitive fields from extra / request body:
    SENSITIVE_KEYS = {"pdf_bytes", "source_text", "translated_text", "api_key", "authorization"}
    # Recursively walks event dict and replaces values for sensitive keys with "[REDACTED]"
```

### 11.5 `middleware.py`

**`MetricsMiddleware`** (Starlette `BaseHTTPMiddleware`):
- Records `http_requests_total`, `http_request_duration_seconds` labels.
- Normalises path parameters: `/api/v1/documents/abc-123/translate` → `/api/v1/documents/{id}/translate`.

**`RequestLoggingMiddleware`**:
- Logs `request_started` (method, path, client_host) and `request_completed` (status_code, duration_ms).

---

## 12. OTel Trace Span Hierarchy

```
document_translation_pipeline              ← root span
  ├── parse_pdf
  │     attributes: document.id, page_count, classification
  ├── ocr_fallback
  │     attributes: empty_page_count
  ├── cost_guard
  ├── translate_document
  │     attributes: translatable_node_count
  │     └── translate_node  (per STU lead)
  │           attributes: node_id, provider, src_lang, tgt_lang, cached, retry_count
  ├── render_pdf
  │     attributes: is_overlay_mode, page_count
  ├── visual_qa
  │     attributes: qa_score, qa_valid
  └── store_artifacts
        attributes: version_id, ir_size_bytes, pdf_size_bytes
```

---

## 13. Database Schema (`packages/storage/postgres/models.py`)

### `documents` table

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Document identifier |
| `filename` | VARCHAR | Original uploaded filename |
| `status` | VARCHAR | `pending \| processing \| completed \| failed` |
| `source_language` | VARCHAR | ISO 639-1 |
| `target_language` | VARCHAR | ISO 639-1 |
| `page_count` | INT | |
| `classification` | VARCHAR | `DIGITAL \| SCANNED \| MIXED` |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

### `document_versions` table

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Version identifier |
| `document_id` | UUID FK → documents.id | |
| `parent_version_id` | UUID nullable | Enables version DAG |
| `ir_path` | VARCHAR | Object store key for IR JSON |
| `pdf_path` | VARCHAR | Object store key for translated PDF |
| `qa_score` | FLOAT | Visual QA composite score |
| `cost_usd` | FLOAT | Total translation cost |
| `created_at` | TIMESTAMP | |

---

## 14. Config Files Reference

### `config/routing.yaml`

```yaml
policy_version: "routing-v1"
routes:
  - source: en
    targets: [hi, ta, te, kn, ml, bn, mr, gu, pa]
    provider: bodhan
  - source: hi
    targets: [en]
    provider: bodhan
  - source: ta
    targets: [en]
    provider: bodhan
  - source: te
    targets: [en]
    provider: bodhan
default:
  provider: openrouter
  model: "meta-llama/llama-3.3-70b-instruct"
```

### `config/limits.yaml` (key fields)

```yaml
limits:
  max_translation_cost_usd: 1.00
  max_pdf_size_mb: 50
cost_estimation:
  cost_per_1k_input_tokens: 0.0007
  cost_per_1k_output_tokens: 0.0009
  script_token_multipliers:
    Latin: 1.0
    Devanagari: 2.5
    Tamil: 3.0
    Telugu: 3.0
    Kannada: 3.0
    Malayalam: 3.0
    Bengali: 2.8
    Gujarati: 2.8
    Gurmukhi: 2.8
    Default: 2.5
```

### `config/prompts.yaml` (structure)

```yaml
translation_v1:
  system: "You are a professional translator …"
  user: "Translate the following {source_language} text to {target_language}:\n{content}"

unit_translation_v1:
  system: "…"
  user: "…"

section_edit_v1:
  system: "…"
  user: "…"
```

---

## 15. Key Environment Variables

| Variable | Default | Used By |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./translation_studio.db` | `packages/storage/postgres/db.py` |
| `REDIS_URL` | `redis://localhost:6379/0` | `packages/storage/redis/cache.py` |
| `OBJECT_STORAGE_LOCAL_DIR` | `./data/storage` | `LocalFileObjectStore` |
| `BODHAN_API_KEY` | — | `packages/providers/bodhan/client.py` |
| `BODHAN_BASE_URL` | — | `packages/providers/bodhan/client.py` |
| `OPENROUTER_API_KEY` | — | `packages/providers/openrouter/client.py` |
| `OTEL_ENABLED` | `true` | `packages/observability/tracing.py` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | `packages/observability/tracing.py` |
| `SERVICE_NAME` | `translation-studio-api` | OTel resource attribute |
| `SENTRY_DSN` | _(empty)_ | `packages/observability/sentry.py` |
| `LOG_LEVEL` | `INFO` | `packages/observability/logging.py` |
| `MAX_TRANSLATION_COST_USD` | `1.00` | `CostGuard` |
| `STU_GROUPING` | `1` | `packages/semantic/units.py` |

---

## 16. Testing Strategy

### Test Organisation (`tests/`)

```
tests/
├── test_protected_content.py     # protect() / validate_and_restore() edge cases
├── test_cost_guard.py            # CostGuard threshold + multiplier logic
├── test_router.py                # TranslationRouter routing decisions
├── test_parser.py                # PyMuPDFParser on fixture PDFs
├── test_pipeline_integration.py  # End-to-end pipeline with mock providers
└── conftest.py                   # Shared fixtures, mock providers
```

### Key Fixtures

- **MockBodhanProvider:** Returns canned Hindi translation without HTTP.
- **MockOpenRouterProvider:** Returns canned translation with token usage data.
- **InMemoryObjectStore:** Implements the same `put_object/get_object` interface as `LocalFileObjectStore`.
- **Sample PDFs:** Fixture PDFs in `tests/fixtures/` covering digital, scanned, table-heavy, and math-heavy documents.

### Running Tests

```bash
# From workspace root
PYTHONPATH="" .venv/bin/pytest tests -v
```

All 10 tests must pass before merging any pipeline changes.
