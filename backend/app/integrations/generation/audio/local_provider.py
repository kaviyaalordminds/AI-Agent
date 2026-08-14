import asyncio
import shutil
import tempfile
from pathlib import Path

from app.integrations.capability import CapabilityStatus
from app.integrations.generation.audio.base import AudioProvider, SynthesizedAudio
from app.integrations.generation.errors import GenerationProviderNotConfiguredError, GenerationProviderRequestError

_ESPEAK_CANDIDATES = ("espeak-ng", "espeak")


def _find_espeak() -> str | None:
    for name in _ESPEAK_CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    return None


class LocalTTSProvider(AudioProvider):
    """Real local text-to-speech via espeak-ng/espeak — no API key, no
    network access, works offline. Genuinely synthesizes audio when the
    binary is installed; when it isn't, capability() honestly reports
    unavailable instead of pretending to work."""

    def __init__(self) -> None:
        self._binary = _find_espeak()

    def capability(self) -> CapabilityStatus:
        if self._binary:
            return CapabilityStatus(
                available=True,
                provider="local-espeak",
                mode="local",
                reason=f"Local TTS engine found at {self._binary}.",
            )
        return CapabilityStatus(
            available=False,
            provider="local-espeak",
            mode="local",
            reason=(
                "No local TTS engine found (espeak-ng or espeak). Install one, "
                "e.g. `apt install espeak-ng` (Linux) or `brew install espeak-ng` (macOS), "
                "or set TTS_PROVIDER=cloud with a configured cloud provider."
            ),
        )

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language: str | None = None,
        speed: float = 1.0,
        format: str = "wav",
    ) -> SynthesizedAudio:
        if not self._binary:
            raise GenerationProviderNotConfiguredError(self.capability().reason)
        if format != "wav":
            raise GenerationProviderRequestError(
                "Local TTS (espeak-ng) only produces WAV output in this deployment."
            )

        voice_code = voice or language or "en"
        words_per_minute = max(80, min(450, round(175 * speed)))

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "speech.wav"
            proc = await asyncio.create_subprocess_exec(
                self._binary,
                "-v", voice_code,
                "-s", str(words_per_minute),
                "-w", str(out_path),
                text,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0 or not out_path.exists():
                raise GenerationProviderRequestError(
                    f"Local TTS synthesis failed: {stderr.decode(errors='replace').strip() or 'unknown error'}"
                )
            data = out_path.read_bytes()

        return SynthesizedAudio(data=data, format="wav", content_type="audio/wav")
