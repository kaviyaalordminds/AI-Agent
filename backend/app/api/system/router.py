import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.integrations.claude.factory import get_claude_status
from app.integrations.deployment.factory import get_deployment_provider
from app.integrations.generation.audio.factory import get_audio_provider
from app.integrations.generation.image.factory import get_image_provider
from app.integrations.generation.transcription.factory import get_transcription_provider
from app.integrations.generation.video.factory import get_video_provider
from app.integrations.generation.voice.factory import get_voice_provider
from app.integrations.obsidian.factory import get_obsidian_provider
from app.integrations.storage.factory import get_storage_provider
from app.jobs.factory import get_job_queue
from app.models.user import User
from app.schemas.system import CapabilitiesOut, CapabilityOut, ComponentHealthOut, ProvidersHealthOut
from app.security.sessions import get_current_user

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/capabilities", response_model=CapabilitiesOut)
def get_capabilities(user: User = Depends(get_current_user)):
    settings = get_settings()
    mode = settings.resolved_ai_runtime_mode

    ai_status = get_claude_status()
    ai_capability = CapabilityOut(
        available=ai_status.configured, provider=ai_status.provider, mode=mode, reason=ai_status.detail
    )

    audio_cap = get_audio_provider().capability()
    transcription_cap = get_transcription_provider().capability()
    voice_cap = get_voice_provider().capability()
    image_cap = get_image_provider().capability()
    video_cap = get_video_provider().capability()
    deployment_cap = get_deployment_provider().capability()

    documents_reason = (
        "Document rendering (Markdown/.docx/.pdf) has no external dependency and always "
        "works; AI-drafted content requires the configured AI provider."
        if ai_status.configured
        else f"Document rendering always works, but AI-drafted content is blocked: {ai_status.detail}"
    )
    documents_cap = CapabilityOut(
        available=ai_status.configured, provider=ai_status.provider, mode=mode, reason=documents_reason
    )

    try:
        vault_status = get_obsidian_provider(user.id).status()
        obsidian_cap = CapabilityOut(
            available=vault_status.connected,
            provider=vault_status.provider,
            mode="local",
            reason=vault_status.detail,
        )
    except Exception as exc:
        obsidian_cap = CapabilityOut(available=False, provider=settings.obsidian_provider, mode="local", reason=str(exc))

    try:
        get_storage_provider()
        storage_cap = CapabilityOut(
            available=True,
            provider=settings.storage_provider,
            mode="local" if settings.storage_provider == "local" else "production",
            reason=f"Storage root is writable ({settings.storage_root}).",
        )
    except OSError as exc:
        storage_cap = CapabilityOut(
            available=False, provider=settings.storage_provider, mode="local", reason=str(exc)
        )

    return CapabilitiesOut(
        ai=ai_capability,
        audio=CapabilityOut(**vars(audio_cap)),
        transcription=CapabilityOut(**vars(transcription_cap)),
        voice=CapabilityOut(**vars(voice_cap)),
        image=CapabilityOut(**vars(image_cap)),
        video=CapabilityOut(**vars(video_cap)),
        documents=documents_cap,
        obsidian=obsidian_cap,
        storage=storage_cap,
        deployment=CapabilityOut(**vars(deployment_cap)),
    )


def _check_database(db: Session) -> ComponentHealthOut:
    try:
        db.execute(text("SELECT 1"))
        return ComponentHealthOut(status="ok", detail="Connected.")
    except Exception as exc:
        return ComponentHealthOut(status="down", detail=f"Database error: {exc}")


async def _check_ai_provider() -> ComponentHealthOut:
    settings = get_settings()
    if settings.resolved_ai_provider == "ollama":
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            if resp.status_code == 200:
                return ComponentHealthOut(status="ok", detail=f"Ollama reachable at {settings.ollama_base_url}.")
            return ComponentHealthOut(
                status="degraded", detail=f"Ollama responded with status {resp.status_code}."
            )
        except httpx.RequestError as exc:
            return ComponentHealthOut(status="down", detail=f"Ollama unreachable: {exc}")

    status_obj = get_claude_status()
    if status_obj.configured:
        return ComponentHealthOut(
            status="ok", detail=f"{status_obj.provider} configured (not live-tested to avoid API usage)."
        )
    return ComponentHealthOut(status="down", detail=status_obj.detail)


def _check_obsidian(user: User) -> ComponentHealthOut:
    try:
        vault_status = get_obsidian_provider(user.id).status()
        if vault_status.connected:
            return ComponentHealthOut(status="ok", detail=vault_status.detail)
        return ComponentHealthOut(status="degraded", detail=vault_status.detail)
    except Exception as exc:
        return ComponentHealthOut(status="down", detail=str(exc))


def _check_storage() -> ComponentHealthOut:
    try:
        get_storage_provider()
        return ComponentHealthOut(status="ok", detail="Storage root is writable.")
    except OSError as exc:
        return ComponentHealthOut(status="down", detail=str(exc))


def _check_job_queue() -> ComponentHealthOut:
    try:
        get_job_queue()
        return ComponentHealthOut(status="ok", detail="Job queue is running.")
    except Exception as exc:
        return ComponentHealthOut(status="down", detail=str(exc))


@router.get("/providers/health", response_model=ProvidersHealthOut)
async def get_providers_health(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ProvidersHealthOut(
        database=_check_database(db),
        ai_provider=await _check_ai_provider(),
        obsidian=_check_obsidian(user),
        storage=_check_storage(),
        job_queue=_check_job_queue(),
    )
