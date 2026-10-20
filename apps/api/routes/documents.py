import hashlib
import uuid
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import Response
from packages.document.parser.pdf_classifier import PDFClassifier
from apps.api.schemas.document import DocumentUploadResponse, TranslationStartRequest
from apps.api.dependencies import get_storage, get_pipeline
from packages.storage.object_store.base import ObjectStore
from apps.worker.tasks.pipeline import DocumentTranslationPipeline
from packages.document.ir.serializer import IRSerializer

router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    storage: ObjectStore = Depends(get_storage),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File size exceeds 50MB limit.")

    classification, total_pages, is_valid = PDFClassifier.classify(content)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Corrupted or unreadable PDF.")

    document_id = str(uuid.uuid4())
    key = f"documents/{document_id}/original.pdf"
    await storage.put_object(key, content, "application/pdf")

    return DocumentUploadResponse(
        document_id=document_id,
        filename=file.filename,
        file_size_bytes=len(content),
        total_pages=total_pages,
        classification=classification,
    )


@router.post("/{document_id}/translate")
async def translate_document(
    document_id: str,
    request: TranslationStartRequest,
    storage: ObjectStore = Depends(get_storage),
    pipeline: DocumentTranslationPipeline = Depends(get_pipeline),
):
    pdf_key = f"documents/{document_id}/original.pdf"
    if not await storage.exists(pdf_key):
        raise HTTPException(status_code=404, detail="Document not found.")

    pdf_bytes = await storage.get_object(pdf_key)

    try:
        result = await pipeline.execute(
            document_id=document_id,
            pdf_bytes=pdf_bytes,
            target_language=request.target_language,
            source_language=request.source_language,
            user_requested_provider=request.provider,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "job_id": str(uuid.uuid4()),
        "document_id": document_id,
        "version_id": result["version_id"],
        "status": result["status"],
        "qa_score": result["qa_score"],
        "target_language": result["target_language"],
        "download_url": f"/api/v1/documents/{document_id}/versions/{result['version_id']}/pdf",
        "ir_url": f"/api/v1/documents/{document_id}/versions/{result['version_id']}/structure",
    }



@router.get("/{document_id}/versions/{version_id}/pdf")
async def get_version_pdf(
    document_id: str,
    version_id: str,
    storage: ObjectStore = Depends(get_storage),
):
    pdf_key = f"documents/{document_id}/versions/{version_id}/output.pdf"
    if not await storage.exists(pdf_key):
        raise HTTPException(status_code=404, detail="Version PDF not found.")

    pdf_bytes = await storage.get_object(pdf_key)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{document_id}_{version_id}.pdf"',
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/{document_id}/versions/{version_id}/structure")
async def get_version_structure(
    document_id: str,
    version_id: str,
    storage: ObjectStore = Depends(get_storage),
):
    ir_key = f"documents/{document_id}/versions/{version_id}/document.ir.json"
    if not await storage.exists(ir_key):
        raise HTTPException(status_code=404, detail="Version IR structure not found.")

    ir_bytes = await storage.get_object(ir_key)
    ir = IRSerializer.from_json(ir_bytes.decode("utf-8"))
    return ir.model_dump()


@router.get("/{document_id}/original/pdf")
async def get_original_pdf(
    document_id: str,
    storage: ObjectStore = Depends(get_storage),
):
    pdf_key = f"documents/{document_id}/original.pdf"
    if not await storage.exists(pdf_key):
        raise HTTPException(status_code=404, detail="Original PDF not found.")

    pdf_bytes = await storage.get_object(pdf_key)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{document_id}_original.pdf"',
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


