from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import (
    DbSession,
    KnowledgeCreateContext,
    KnowledgeDeleteContext,
    KnowledgeReadContext,
    KnowledgeUpdateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.documents import (
    ChunkListOut,
    ChunkOut,
    ChunkParamsIn,
    ChunkUpdateIn,
    DocumentDetailOut,
    DocumentListOut,
    OverviewOut,
    TaskListOut,
    TaskOut,
    UploadBatchOut,
)
from app.services.documents import DocumentService

router = APIRouter(tags=["knowledge-documents"])


@router.get("/overview", response_model=ApiResponse[OverviewOut], summary="知识库工作台统计")
async def overview(context: KnowledgeReadContext, session: DbSession) -> ApiResponse[OverviewOut]:
    return ok(await DocumentService(session, context).overview())


@router.get("/documents", response_model=ApiResponse[DocumentListOut], summary="文档列表")
async def list_documents(
    context: KnowledgeReadContext,
    session: DbSession,
    knowledge_base_id: int | None = Query(default=None),
    q: str | None = Query(default=None, max_length=128),
    status: str | None = Query(default=None, max_length=16),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[DocumentListOut]:
    return ok(
        await DocumentService(session, context).list_documents(
            knowledge_base_id=knowledge_base_id,
            q=q,
            status=status,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=ApiResponse[UploadBatchOut],
    summary="上传文档",
)
async def upload_documents(
    knowledge_base_id: int,
    context: KnowledgeCreateContext,
    session: DbSession,
    files: list[UploadFile] = File(...),
) -> ApiResponse[UploadBatchOut]:
    return ok(await DocumentService(session, context).upload(knowledge_base_id, files), "上传完成")


@router.get("/documents/{document_id}", response_model=ApiResponse[DocumentDetailOut], summary="文档详情")
async def get_document(
    document_id: int,
    context: KnowledgeReadContext,
    session: DbSession,
) -> ApiResponse[DocumentDetailOut]:
    return ok(await DocumentService(session, context).get_document(document_id))


@router.get("/documents/{document_id}/file", summary="下载原文件")
async def download_document(
    document_id: int,
    context: KnowledgeReadContext,
    session: DbSession,
) -> FileResponse:
    filename, mime_type, path = await DocumentService(session, context).stored_path(document_id)
    return FileResponse(path, media_type=mime_type, filename=filename)


@router.delete("/documents/{document_id}", response_model=ApiResponse[None], summary="删除文档")
async def delete_document(
    document_id: int,
    context: KnowledgeDeleteContext,
    session: DbSession,
) -> ApiResponse[None]:
    await DocumentService(session, context).delete_document(document_id)
    return ok(None, "删除成功")


@router.post("/documents/{document_id}/parse", response_model=ApiResponse[TaskOut], summary="重新解析")
async def parse_document(
    document_id: int,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[TaskOut]:
    return ok(await DocumentService(session, context).request_parse(document_id), "已排队解析")


@router.post("/documents/{document_id}/chunk", response_model=ApiResponse[TaskOut], summary="重新切片")
async def chunk_document(
    document_id: int,
    payload: ChunkParamsIn,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[TaskOut]:
    return ok(await DocumentService(session, context).request_chunk(document_id, payload), "已排队切片")


@router.get("/chunks", response_model=ApiResponse[ChunkListOut], summary="切片列表")
async def list_chunks(
    context: KnowledgeReadContext,
    session: DbSession,
    knowledge_base_id: int | None = Query(default=None),
    document_id: int | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[ChunkListOut]:
    return ok(
        await DocumentService(session, context).list_chunks(
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            enabled=enabled,
            page=page,
            page_size=page_size,
        )
    )


@router.patch("/chunks/{chunk_id}", response_model=ApiResponse[ChunkOut], summary="编辑切片")
async def update_chunk(
    chunk_id: int,
    payload: ChunkUpdateIn,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[ChunkOut]:
    return ok(await DocumentService(session, context).update_chunk(chunk_id, payload))


@router.get("/tasks", response_model=ApiResponse[TaskListOut], summary="处理任务列表")
async def list_tasks(
    context: KnowledgeReadContext,
    session: DbSession,
    knowledge_base_id: int | None = Query(default=None),
    document_id: int | None = Query(default=None),
    status: str | None = Query(default=None, max_length=16),
    task_type: str | None = Query(default=None, max_length=16),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[TaskListOut]:
    return ok(
        await DocumentService(session, context).list_tasks(
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            status=status,
            task_type=task_type,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/tasks/{task_id}", response_model=ApiResponse[TaskOut], summary="任务详情")
async def get_task(
    task_id: int,
    context: KnowledgeReadContext,
    session: DbSession,
) -> ApiResponse[TaskOut]:
    return ok(await DocumentService(session, context).get_task(task_id))


@router.post("/tasks/{task_id}/retry", response_model=ApiResponse[TaskOut], summary="重试失败任务")
async def retry_task(
    task_id: int,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[TaskOut]:
    return ok(await DocumentService(session, context).retry_task(task_id), "已重新排队")
