from fastapi import APIRouter, Depends, HTTPException, Query
from apps.api.schemas.document import SectionEditRequest, SectionEditResponse, SelectionEditRequest, SelectionEditResponse
from apps.api.dependencies import get_storage, get_section_edit_pipeline
from apps.worker.tasks.section_edit import SectionEditPipeline

router = APIRouter(prefix="/api/v1/documents", tags=["Sections"])


@router.post("/{document_id}/nodes/{node_id}/edit", response_model=SectionEditResponse)
async def prompt_edit_section(
    document_id: str,
    node_id: str,
    request: SectionEditRequest,
    version_id: str = Query(..., description="Current version ID to edit upon"),
    pipeline: SectionEditPipeline = Depends(get_section_edit_pipeline),
):
    try:
        res = await pipeline.edit_section(
            document_id=document_id,
            current_version_id=version_id,
            node_id=node_id,
            user_instruction=request.instruction,
        )
        return SectionEditResponse(
            document_id=res["document_id"],
            version_id=res["version_id"],
            parent_version_id=res["parent_version_id"],
            node_id=res["node_id"],
            edited_translation=res["edited_translation"],
            status=res["status"],
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{document_id}/edit", response_model=SelectionEditResponse)
async def prompt_edit_selection(
    document_id: str,
    request: SelectionEditRequest,
    pipeline: SectionEditPipeline = Depends(get_section_edit_pipeline),
):
    try:
        res = await pipeline.edit_selection(
            document_id=document_id,
            current_version_id=request.version_id,
            instruction=request.instruction,
            selection=request.selection.model_dump(exclude_none=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SelectionEditResponse(**res)
