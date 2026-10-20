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
