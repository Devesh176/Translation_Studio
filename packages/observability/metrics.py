"""
Prometheus metrics registry for Translation Studio.

All metric objects are module-level singletons so they can be imported and
incremented from anywhere without passing instances around.

Categories (mirrors §51 of the implementation plan):
    - HTTP / API
    - Translation
    - OCR
    - Rendering
    - Visual QA
    - Pipeline / documents
    - Validation
    - Provider routing
"""

try:
    from prometheus_client import Counter, Gauge, Histogram
    _PROMETHEUS_AVAILABLE = True
except (ImportError, Exception):
    _PROMETHEUS_AVAILABLE = False

    class _NoOpMetric:
        def __init__(self, *args, **kwargs):
            pass

        def inc(self, *args, **kwargs):
            pass

        def dec(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

    Counter = _NoOpMetric  # type: ignore[misc, assignment]
    Gauge = _NoOpMetric  # type: ignore[misc, assignment]
    Histogram = _NoOpMetric  # type: ignore[misc, assignment]

# ---------------------------------------------------------------------------
# HTTP / API
# ---------------------------------------------------------------------------

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total number of HTTP requests received.",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request processing duration in seconds.",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

HTTP_ERRORS_TOTAL = Counter(
    "http_errors_total",
    "Total number of HTTP 5xx responses.",
    ["method", "endpoint"],
)

# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

TRANSLATION_REQUESTS_TOTAL = Counter(
    "translation_requests_total",
    "Total translation node requests dispatched to providers.",
    ["provider", "source_language", "target_language", "status"],
)

TRANSLATION_LATENCY_SECONDS = Histogram(
    "translation_latency_seconds",
    "Round-trip latency for a single translation request.",
    ["provider"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

TRANSLATION_PROVIDER_FAILURES_TOTAL = Counter(
    "translation_provider_failures_total",
    "Total provider-side translation failures.",
    ["provider", "failure_code"],
)

TRANSLATION_COST_USD_TOTAL = Counter(
    "translation_cost_usd_total",
    "Cumulative estimated translation cost in USD.",
    ["provider"],
)

TRANSLATION_INPUT_TOKENS_TOTAL = Counter(
    "translation_input_tokens_total",
    "Cumulative input tokens sent to translation providers.",
    ["provider"],
)

TRANSLATION_OUTPUT_TOKENS_TOTAL = Counter(
    "translation_output_tokens_total",
    "Cumulative output tokens received from translation providers.",
    ["provider"],
)

TRANSLATION_CACHE_HITS_TOTAL = Counter(
    "translation_cache_hits_total",
    "Total translation cache hits (Redis or in-memory).",
)

TRANSLATION_CACHE_MISSES_TOTAL = Counter(
    "translation_cache_misses_total",
    "Total translation cache misses.",
)

TRANSLATION_RETRIES_TOTAL = Counter(
    "translation_retries_total",
    "Total translation retry attempts.",
    ["provider"],
)

# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

OCR_PAGES_TOTAL = Counter(
    "ocr_pages_total",
    "Total pages submitted to the OCR provider.",
    ["provider", "status"],
)

OCR_LATENCY_SECONDS = Histogram(
    "ocr_latency_seconds",
    "Round-trip latency for a single OCR page request.",
    ["provider"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
)

OCR_PROVIDER_FAILURES_TOTAL = Counter(
    "ocr_provider_failures_total",
    "Total OCR provider failures.",
    ["provider", "failure_code"],
)

OCR_RETRY_TOTAL = Counter(
    "ocr_retry_total",
    "Total OCR retry attempts.",
    ["provider"],
)

OCR_CONFIDENCE_HISTOGRAM = Histogram(
    "ocr_confidence",
    "Distribution of OCR confidence scores per page.",
    ["provider"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

RENDER_PAGES_TOTAL = Counter(
    "render_pages_total",
    "Total pages through the rendering stage.",
    ["status"],
)

RENDER_LATENCY_SECONDS = Histogram(
    "render_latency_seconds",
    "End-to-end PDF rendering latency per document.",
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 15.0, 30.0, 60.0],
)

RENDER_FAILURES_TOTAL = Counter(
    "render_failures_total",
    "Total rendering failures by failure code.",
    ["failure_code"],
)

LAYOUT_OVERFLOW_TOTAL = Counter(
    "layout_overflow_total",
    "Total layout overflow events (text did not fit its bounding box).",
)

LAYOUT_OVERLAP_TOTAL = Counter(
    "layout_overlap_total",
    "Total layout overlap detection events.",
)

FONT_MISSING_GLYPH_TOTAL = Counter(
    "font_missing_glyph_total",
    "Total missing-glyph events detected during rendering.",
    ["script"],
)

# ---------------------------------------------------------------------------
# Visual QA
# ---------------------------------------------------------------------------

VISUAL_QA_SCORE_HISTOGRAM = Histogram(
    "visual_qa_score",
    "Distribution of Visual QA composite scores (0.0–1.0).",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

VISUAL_QA_FAILURES_TOTAL = Counter(
    "visual_qa_failures_total",
    "Total Visual QA gate failures by failure code.",
    ["failure_code"],
)

# ---------------------------------------------------------------------------
# Pipeline / documents
# ---------------------------------------------------------------------------

DOCUMENTS_PROCESSED_TOTAL = Counter(
    "documents_processed_total",
    "Total documents that completed or failed the translation pipeline.",
    ["status"],
)

PIPELINE_DURATION_SECONDS = Histogram(
    "pipeline_duration_seconds",
    "End-to-end pipeline duration per document.",
    ["status"],
    buckets=[1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0],
)

ACTIVE_JOBS = Gauge(
    "active_jobs",
    "Number of document translation jobs currently in progress.",
)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

VALIDATION_FAILURES_TOTAL = Counter(
    "validation_failures_total",
    "Total translation validation failures by check type.",
    ["check_type"],
)

# ---------------------------------------------------------------------------
# Provider routing
# ---------------------------------------------------------------------------

ROUTING_DECISIONS_TOTAL = Counter(
    "routing_decisions_total",
    "Total translation routing decisions.",
    ["provider", "reason"],
)
