import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

SETTINGS_FILE = Path(os.environ.get("LIVELINE_SETTINGS_FILE", "settings.json"))


@dataclass
class Settings:
    public_host: str = "localhost:8000"
    whisper_model: str = "base.en"
    whisper_beam_size: int = 1
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2:3b"
    llm_max_tokens: int = 80
    piper_voice: str = "models/en_US-lessac-medium.onnx"
    vad_model: str = "models/silero_vad.onnx"
    vad_threshold: float = 0.5
    speech_start_ms: int = 64
    end_of_turn_ms: int = 500
    min_speech_ms: int = 250

    @classmethod
    def load(cls) -> "Settings":
        """Defaults, then settings.json, then LIVELINE_<NAME> environment variables."""
        settings = cls()
        if SETTINGS_FILE.exists():
            settings.update(json.loads(SETTINGS_FILE.read_text()))
        env = {f.name: os.environ["LIVELINE_" + f.name.upper()]
               for f in fields(cls) if "LIVELINE_" + f.name.upper() in os.environ}
        settings.update(env)
        return settings

    def update(self, values: dict) -> None:
        for f in fields(self):
            if f.name in values:
                setattr(self, f.name, type(getattr(self, f.name))(values[f.name]))

    def save(self) -> None:
        SETTINGS_FILE.write_text(json.dumps(asdict(self), indent=2))
