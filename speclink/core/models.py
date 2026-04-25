from pathlib import Path

from pydantic import BaseModel, Field


class CodeElement(BaseModel):
    id: str
    name: str
    signature: str
    code: str = Field(default="", exclude=True)
    file_path: str


class Classification(BaseModel):
    target_id: str
    is_match: bool


class Section(BaseModel):
    heading: str
    chunk_index: int = 0
    hash: str | None = None

    file_path: str = Field(default="", exclude=True)
    content: str = Field(default="", exclude=True)

    files: list[str] = Field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.file_path}::{self.heading}::{self.chunk_index}"


class Document(BaseModel):
    doc_file: str
    sections: list[Section]


class DocMap(BaseModel):
    codebase_sha: str = ""
    mappings: list[Document]

    @classmethod
    def from_json(cls, source: Path | str) -> "DocMap":
        if isinstance(source, Path):
            return cls.model_validate_json(source.read_text())
        return cls.model_validate_json(source)
