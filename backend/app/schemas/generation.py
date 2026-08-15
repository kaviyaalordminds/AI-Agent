import base64
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CreateImageJobRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    project_id: uuid.UUID | None = None


# --- Poster / Logo / Graphic Design: same underlying image generation
# pipeline as CreateImageJobRequest (job queue -> ImageProvider ->
# storage), but each takes domain-specific structured fields that the
# router turns into a purpose-built prompt server-side, rather than
# making the caller write the whole prompt by hand like plain Image
# generation does. See app/api/generation/router.py for the prompt
# assembly and app/jobs/worker.py for execution (both reuse _run_image_job).


class CreatePosterJobRequest(BaseModel):
    headline: str = Field(min_length=1, max_length=200, description="Main text to display prominently on the poster.")
    subheading: str | None = Field(default=None, max_length=200)
    prompt: str = Field(min_length=1, max_length=2000, description="Visual style/subject description.")
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    project_id: uuid.UUID | None = None


class CreateLogoJobRequest(BaseModel):
    brand_name: str = Field(min_length=1, max_length=200)
    style: Literal["minimalist", "modern", "vintage", "geometric", "playful", "luxury"] = "minimalist"
    description: str | None = Field(default=None, max_length=1000, description="Additional concept/detail.")
    colors: str | None = Field(default=None, max_length=200, description="Preferred color palette, e.g. 'blue and gold'.")
    project_id: uuid.UUID | None = None


class CreateGraphicDesignJobRequest(BaseModel):
    design_type: Literal["social_media_post", "banner", "flyer", "business_card", "presentation_cover", "other"] = "other"
    prompt: str = Field(min_length=1, max_length=2000)
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    project_id: uuid.UUID | None = None


class CreateVideoJobRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    duration_seconds: float = Field(default=4.0, ge=1.0, le=60.0)
    reference_image_base64: str | None = Field(
        default=None,
        max_length=40_000_000,  # ~30MB decoded; storage.write() enforces the real MAX_UPLOAD_FILE_SIZE_MB limit
        description="Optional base64-encoded reference image for image-to-video generation.",
    )
    project_id: uuid.UUID | None = None

    @field_validator("reference_image_base64")
    @classmethod
    def _validate_base64(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            base64.b64decode(value, validate=True)
        except Exception as exc:
            raise ValueError("reference_image_base64 must be valid base64-encoded image data.") from exc
        return value


class CreateTranscriptionJobRequest(BaseModel):
    audio_base64: str = Field(
        min_length=1,
        max_length=40_000_000,  # ~30MB decoded; storage.write() enforces the real MAX_UPLOAD_FILE_SIZE_MB limit
        description="Base64-encoded audio file to transcribe.",
    )
    language: str | None = Field(default=None, max_length=10)
    project_id: uuid.UUID | None = None

    @field_validator("audio_base64")
    @classmethod
    def _validate_base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except Exception as exc:
            raise ValueError("audio_base64 must be valid base64-encoded audio data.") from exc
        return value


# --- Structured document generation (Word / PowerPoint / Excel) ---
# These formats require no AI provider: the caller supplies fully
# structured content and a local library (python-docx/python-pptx/
# openpyxl) renders it deterministically. Kept separate from the
# Claude-drafted /api/documents flow (which takes a free-text prompt),
# but both ultimately produce a Document row — see app/documents/structured.py.


class WordBlock(BaseModel):
    type: Literal["heading", "paragraph", "bullet_list", "numbered_list", "table"]
    text: str | None = Field(default=None, max_length=8000)
    level: int = Field(default=1, ge=1, le=4, description="Heading level, used only when type == 'heading'.")
    items: list[str] | None = Field(default=None, max_length=200)
    rows: list[list[str]] | None = Field(default=None, max_length=500)
    header_row: bool = Field(default=True, description="Whether the first row of a table is a header row.")
    bold: bool = False
    italic: bool = False


class WordDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    author: str | None = Field(default=None, max_length=255)
    blocks: list[WordBlock] = Field(min_length=1, max_length=300)
    project_id: uuid.UUID | None = None


class PptSlide(BaseModel):
    title: str = Field(default="", max_length=255)
    layout: Literal["title", "title_content", "section_header", "blank"] = "title_content"
    subtitle: str | None = Field(default=None, max_length=500)
    bullets: list[str] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(default=None, max_length=4000)


class PptDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    subtitle: str | None = Field(default=None, max_length=500)
    slides: list[PptSlide] = Field(min_length=1, max_length=150)
    project_id: uuid.UUID | None = None


class ExcelChart(BaseModel):
    type: Literal["bar", "line", "pie"] = "bar"
    title: str | None = Field(default=None, max_length=255)
    category_column: str = Field(description="Header of the column used for chart categories (x-axis/labels).")
    value_columns: list[str] = Field(min_length=1, max_length=10, description="Headers of the numeric columns to chart.")


class ExcelSheet(BaseModel):
    name: str = Field(min_length=1, max_length=31, description="Excel sheet names are limited to 31 characters.")
    headers: list[str] = Field(min_length=1, max_length=100)
    rows: list[list[str | float | int | None]] = Field(default_factory=list, max_length=5000)
    freeze_header: bool = True
    charts: list[ExcelChart] = Field(default_factory=list, max_length=10)


class ExcelDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    sheets: list[ExcelSheet] = Field(min_length=1, max_length=50)
    project_id: uuid.UUID | None = None
