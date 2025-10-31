from pathlib import Path
from typing import Dict
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Query
from fastapi import Depends
from fastapi.responses import FileResponse, HTMLResponse
from sqlmodel import select

from app.core.db import get_session
from app.core.storage import document_upload_path, save_bytes, ensure_parent
from app.core.config import settings
from app.models.domain import Document, Placeholder, Answer, SessionModel, Artifact
from app.services.placeholder_detector import detect_placeholders
from app.services.doc_filler import fill_document, generate_html_preview
from sqlmodel import Session


router = APIRouter(prefix="/documents", tags=["documents"])


def parse_document_placeholders(document_id: str) -> None:
    """Background task to parse document and detect placeholders."""
    import logging
    import traceback
    from app.core.db import session_scope
    
    logger = logging.getLogger(__name__)
    
    with session_scope() as session:
        doc = session.get(Document, document_id)
        if not doc or not doc.original_path:
            logger.error(f"Document {document_id} not found or has no original_path")
            return
        
        file_path = Path(doc.original_path)
        if not file_path.exists():
            logger.error(f"Document file does not exist: {file_path}")
            return
        
        logger.info(f"Starting placeholder detection for document {document_id} at {file_path}")
        
        try:
            detected = detect_placeholders(file_path)
            logger.info(f"Detected {len(detected)} placeholders for document {document_id}")
            
            # Delete existing placeholders for this document
            existing = session.exec(
                select(Placeholder).where(Placeholder.document_id == document_id)
            ).all()
            for p in existing:
                session.delete(p)
            
            # Save new placeholders
            for idx, p_data in enumerate(detected):
                placeholder = Placeholder(
                    document_id=document_id,
                    name=p_data.get("name", ""),
                    description=p_data.get("description"),
                    type=p_data.get("type", "text"),
                    required=p_data.get("required", True),
                    order_index=p_data.get("order_index", idx),
                    source_excerpt=p_data.get("source_excerpt", ""),
                    paragraph_index=p_data.get("paragraph_index"),
                    char_start=p_data.get("char_start"),
                    char_end=p_data.get("char_end"),
                )
                session.add(placeholder)
            
            doc.status = "parsed"
            session.add(doc)
            logger.info(f"Successfully parsed document {document_id}: {len(detected)} placeholders saved")
        except Exception as e:
            logger.error(f"Error parsing document {document_id}: {e}")
            logger.error(traceback.format_exc())
            doc.status = "parse_failed"
            session.add(doc)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    session: Session = Depends(get_session),
):
    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are supported")
    data = await file.read()
    doc = Document(filename=file.filename, original_path="", status="uploaded")
    session.add(doc)
    session.flush()  # to get doc.id

    path = document_upload_path(doc.id, file.filename)
    save_bytes(path, data)
    doc.original_path = str(path)
    session.add(doc)
    session.commit()

    # Trigger parsing in background
    background_tasks.add_task(parse_document_placeholders, doc.id)

    return {"document_id": doc.id, "status": doc.status}


@router.get("/{document_id}")
def get_document(document_id: str, session: Session = Depends(get_session)):
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "created_at": doc.created_at,
    }


@router.post("/{document_id}/parse")
def trigger_parse(
    document_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    background_tasks.add_task(parse_document_placeholders, document_id)
    return {"message": "Parsing started", "document_id": document_id}


@router.get("/{document_id}/placeholders")
def list_placeholders(document_id: str, session: Session = Depends(get_session)):
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    results = session.exec(select(Placeholder).where(Placeholder.document_id == document_id)).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "type": p.type,
            "required": p.required,
            "order_index": p.order_index,
        }
        for p in results
    ]


@router.post("/{document_id}/render")
def render_document(
    document_id: str,
    session_id: str = Query(..., description="Session ID with answers"),
    session: Session = Depends(get_session),
):
    """Render filled document from session answers."""
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    sess = session.get(SessionModel, session_id)
    if not sess or sess.document_id != document_id:
        raise HTTPException(status_code=404, detail="Session not found or doesn't match document")
    
    # Get all placeholders
    placeholders = session.exec(
        select(Placeholder).where(Placeholder.document_id == document_id)
    ).all()
    
    # Get all answers for this session
    answers_query = session.exec(
        select(Answer).where(Answer.session_id == session_id)
    ).all()
    answers_dict = {a.placeholder_id: a.value for a in answers_query if a.value}
    
    if not answers_dict:
        raise HTTPException(status_code=400, detail="No answers found in session")
    
    try:
        # Generate filled .docx
        output_path = settings.outputs_dir / document_id / "filled.docx"
        fill_document(doc, answers_dict, placeholders, output_path)
        
        # Save artifact record
        artifact = Artifact(
            document_id=document_id,
            type="docx",
            path=str(output_path),
        )
        session.add(artifact)
        
        # Generate HTML preview
        html_path = settings.previews_dir / document_id / "index.html"
        generate_html_preview(doc, answers_dict, placeholders, html_path)
        
        html_artifact = Artifact(
            document_id=document_id,
            type="html_preview",
            path=str(html_path),
        )
        session.add(html_artifact)
        
        doc.status = "filled"
        session.add(doc)
        
        return {
            "message": "Document rendered successfully",
            "document_id": document_id,
            "download_path": f"/v1/documents/{document_id}/download",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error rendering document: {str(e)}")


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    file_type: str = Query("docx", description="File type: docx or html"),
    session: Session = Depends(get_session),
):
    """Download rendered document."""
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Find the artifact
    if file_type == "docx":
        artifacts = session.exec(
            select(Artifact).where(
                Artifact.document_id == document_id,
                Artifact.type == "docx"
            )
        ).all()
        if not artifacts:
            raise HTTPException(status_code=404, detail="Rendered document not found. Please render first.")
        artifact = artifacts[0]
        file_path = Path(artifact.path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")
        return FileResponse(
            file_path,
            filename=f"{doc.filename.replace('.docx', '_filled.docx')}",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    elif file_type == "html":
        artifacts = session.exec(
            select(Artifact).where(
                Artifact.document_id == document_id,
                Artifact.type == "html_preview"
            )
        ).all()
        if not artifacts:
            raise HTTPException(status_code=404, detail="HTML preview not found. Please render first.")
        artifact = artifacts[0]
        file_path = Path(artifact.path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")
        return FileResponse(
            file_path,
            filename="preview.html",
            media_type="text/html"
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid file_type. Use 'docx' or 'html'")


@router.get("/{document_id}/preview")
def get_preview_url(document_id: str, session: Session = Depends(get_session)):
    """Get preview URL."""
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    artifacts = session.exec(
        select(Artifact).where(
            Artifact.document_id == document_id,
            Artifact.type == "html_preview"
        )
    ).all()
    
    if not artifacts:
        return {"preview_url": None, "message": "Preview not available. Please render the document first."}
    
    return {
        "preview_url": f"/v1/documents/{document_id}/download?file_type=html",
    }


@router.get("/{document_id}/live-preview")
def get_live_preview(
    document_id: str,
    session_id: str = Query(..., description="Session ID to get current answers"),
    session: Session = Depends(get_session),
):
    """Generate live preview with current answers (even if not all filled)."""
    
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    sess = session.get(SessionModel, session_id)
    if not sess or sess.document_id != document_id:
        raise HTTPException(status_code=404, detail="Session not found or doesn't match document")
    
    # Get all placeholders
    placeholders = session.exec(
        select(Placeholder).where(Placeholder.document_id == document_id)
    ).all()
    
    # Get current answers (even if incomplete)
    answers_query = session.exec(
        select(Answer).where(Answer.session_id == session_id)
    ).all()
    answers_dict = {a.placeholder_id: a.value for a in answers_query if a.value}
    
    # Generate HTML preview on-the-fly
    try:
        # Use a temp file for live preview
        html_content = generate_live_html_preview(doc, answers_dict, placeholders)
        return HTMLResponse(content=html_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating preview: {str(e)}")


def generate_live_html_preview(
    doc_model: Document,
    answers: Dict[str, str],
    placeholders: list[Placeholder],
) -> str:
    """Generate HTML preview content (returns string, not file)."""
    from app.services.doc_parser import extract_text_from_docx
    import html as html_module
    import re
    
    # Extract document text
    doc_path = Path(doc_model.original_path)
    if not doc_path.exists():
        raise FileNotFoundError(f"Original document not found: {doc_model.original_path}")
    
    full_text, paragraphs = extract_text_from_docx(doc_path)
    
    # Create mapping: placeholder_id -> value (ONLY use actual extracted values, not field names)
    placeholder_map = {}
    for p in placeholders:
        if p.id in answers:
            # Only use the extracted value, ensure it's not a field name
            value = answers[p.id]
            # Don't use field names like "the company name" - just use the actual value
            if value and value.strip():
                placeholder_map[p.id] = value.strip()
                placeholder_map[p.name] = value.strip()
    
    # Build document content with replaced placeholders
    content_paragraphs = []
    for para_idx, (orig_idx, para_text) in enumerate(paragraphs):
        processed_text = para_text
        
        # Replace each placeholder
        for placeholder in placeholders:
            if placeholder.id not in placeholder_map:
                continue
            
            value = placeholder_map[placeholder.id]
            
            # Try to replace source_excerpt (the actual placeholder text in document)
            if placeholder.source_excerpt and placeholder.source_excerpt in processed_text:
                processed_text = processed_text.replace(
                    placeholder.source_excerpt,
                    f'<span class="filled-value">{value}</span>',
                    1
                )
                continue  # Only replace once per placeholder
            
            # Also try bracket notation [FIELD_NAME]
            bracket_pattern = f"[{placeholder.name.upper()}]"
            if bracket_pattern in processed_text:
                processed_text = processed_text.replace(
                    bracket_pattern,
                    f'<span class="filled-value">{value}</span>',
                    1
                )
                continue
            
            # Try with underscores
            if placeholder.source_excerpt and "_____" in placeholder.source_excerpt:
                underscore_pattern = r'_{3,}'
                if re.search(underscore_pattern, processed_text):
                    processed_text = re.sub(
                        underscore_pattern,
                        f'<span class="filled-value">{value}</span>',
                        processed_text,
                        count=1
                    )
        
        if processed_text.strip():
            content_paragraphs.append(processed_text)
    
    # Build HTML
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{doc_model.filename} - Live Preview</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Georgia', 'Times New Roman', serif;
            padding: 20px;
            line-height: 1.8;
            color: #333;
            background-color: #fafafa;
        }}
        .document-container {{
            background-color: white;
            padding: 40px 60px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            min-height: 100%;
        }}
        h1 {{
            color: #1a1a1a;
            margin-bottom: 20px;
            font-size: 22px;
            text-align: center;
            font-weight: bold;
        }}
        p {{
            margin-bottom: 12px;
            text-align: justify;
        }}
        .filled-value {{
            background-color: #e3f2fd;
            padding: 2px 6px;
            border-radius: 3px;
            font-weight: 500;
            color: #1565c0;
            border-bottom: 2px solid #64b5f6;
        }}
    </style>
</head>
<body>
    <div class="document-container">
"""
    
    # Add all paragraphs
    for para_text in content_paragraphs:
        # Escape HTML but preserve our filled-value spans
        parts = para_text.split('<span class="filled-value">')
        escaped_parts = []
        for i, part in enumerate(parts):
            if '</span>' in part:
                value_part, rest = part.split('</span>', 1)
                escaped_parts.append(f'<span class="filled-value">{html_module.escape(value_part)}</span>{html_module.escape(rest)}')
            else:
                escaped_parts.append(html_module.escape(part))
        
        final_text = ''.join(escaped_parts)
        
        if final_text.strip():
            html_content += f"        <p>{final_text}</p>\n"
    
    html_content += """    </div>
</body>
</html>
"""
    
    return html_content


