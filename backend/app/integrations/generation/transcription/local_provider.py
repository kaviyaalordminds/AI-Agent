import importlib.util
import shutil
import tempfile
from pathlib import Path

from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import GenerationProviderNotConfiguredError, GenerationProviderRequestError
from app.integrations.generation.transcription.base import TranscriptionProvider, TranscriptionResult, TranscriptionSegment


def _whisper_backend() -> str | None:
    """Real detection, in preference order — never assumes a backend is
    present without checking."""
    if importlib.util.find_spec("faster_whisper") is not None:
        return "faster_whisper"
    if importlib.util.find_spec("whisper") is not None:
        return "openai_whisper"
    if shutil.which("whisper"):
        return "whisper_cli"
    return None


class LocalWhisperProvider(TranscriptionProvider):
    """Local Whisper-compatible transcription. Genuinely transcribes when
    a backend (faster-whisper, openai-whisper, or the whisper CLI) is
    installed; otherwise capability() honestly reports unavailable rather
    than pretending to work — no local speech model ships with this
    application by default, since model weights are hundreds of MB to
    several GB and must be fetched explicitly by the operator."""

    def __init__(self, model_size: str = "base") -> None:
        self._backend = _whisper_backend()
        self._model_size = model_size

    def capability(self) -> CapabilityStatus:
        if self._backend:
            return CapabilityStatus(
                available=True,
                provider=f"local-{self._backend}",
                mode="local",
                reason=f"Local transcription backend '{self._backend}' is installed.",
            )
        return CapabilityStatus(
            available=False,
            provider="local-whisper",
            mode="local",
            reason=(
                "No local transcription backend found. Install one, e.g. "
                "`pip install faster-whisper` (recommended, no ffmpeg required) "
                "or `pip install openai-whisper`, or set TRANSCRIPTION_PROVIDER=cloud "
                "with a configured cloud provider."
            ),
        )

    async def transcribe(self, audio_data: bytes, language: str | None = None) -> TranscriptionResult:
        if not self._backend:
            raise GenerationProviderNotConfiguredError(self.capability().reason)

        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "input.audio"
            audio_path.write_bytes(audio_data)

            if self._backend == "faster_whisper":
                return await self._transcribe_faster_whisper(audio_path, language)
            raise GenerationProviderRequestError(
                f"Backend '{self._backend}' is detected but not yet wired up for transcription "
                "in this deployment — install faster-whisper for a supported local backend."
            )

    async def _transcribe_faster_whisper(self, audio_path: Path, language: str | None) -> TranscriptionResult:
        import asyncio

        def _run() -> TranscriptionResult:
            from faster_whisper import WhisperModel

            model = WhisperModel(self._model_size)
            segments, info = model.transcribe(str(audio_path), language=language)
            collected = [
                TranscriptionSegment(start_seconds=s.start, end_seconds=s.end, text=s.text.strip())
                for s in segments
            ]
            full_text = " ".join(s.text for s in collected).strip()
            return TranscriptionResult(text=full_text, language=info.language, segments=collected)

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:  # pragma: no cover - depends on optional local model files
            raise GenerationProviderRequestError(f"Local transcription failed: {exc}") from exc
