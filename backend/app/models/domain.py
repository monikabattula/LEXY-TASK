from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import uuid4

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    pass

def generate_uuid() -> str:
    return str(uuid4())


class Document(SQLModel, table=True):
    __tablename__ = "document"
    
    id: str = Field(default_factory=generate_uuid, primary_key=True, index=True)
    filename: str
    original_path: str
    status: str = Field(default="uploaded", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Forward references - classes defined later
    placeholders: "Placeholder" = Relationship(back_populates="document", sa_relationship_kwargs={"uselist": True})  # type: ignore
    artifacts: "Artifact" = Relationship(back_populates="document", sa_relationship_kwargs={"uselist": True})  # type: ignore


class Placeholder(SQLModel, table=True):
    id: str = Field(default_factory=generate_uuid, primary_key=True, index=True)
    document_id: str = Field(foreign_key="document.id", index=True)
    name: str
    description: Optional[str] = None
    type: str = Field(default="text", index=True)
    required: bool = Field(default=True)
    order_index: Optional[int] = Field(default=None, index=True)
    source_excerpt: Optional[str] = None

    paragraph_index: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None

    document: "Document" = Relationship(back_populates="placeholders")  # type: ignore[assignment]


class SessionModel(SQLModel, table=True):
    __tablename__ = "session"

    id: str = Field(default_factory=generate_uuid, primary_key=True, index=True)
    document_id: str = Field(foreign_key="document.id", index=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    state: str = Field(default="pending", index=True)

    answers: "Answer" = Relationship(back_populates="session", sa_relationship_kwargs={"uselist": True})  # type: ignore[assignment]


class Answer(SQLModel, table=True):
    id: str = Field(default_factory=generate_uuid, primary_key=True, index=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    placeholder_id: str = Field(foreign_key="placeholder.id", index=True)
    value: Optional[str] = None
    confidence: Optional[float] = None
    source: str = Field(default="user")
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    session: "SessionModel" = Relationship(back_populates="answers")  # type: ignore[assignment]


class Artifact(SQLModel, table=True):
    id: str = Field(default_factory=generate_uuid, primary_key=True, index=True)
    document_id: str = Field(foreign_key="document.id", index=True)
    type: str = Field(index=True)  # json_structure|docx|pdf|html_preview
    path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    document: "Document" = Relationship(back_populates="artifacts")  # type: ignore[assignment]




