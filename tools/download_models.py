"""Download Silero VAD and the Piper voices into models/. Whisper and Llama download themselves."""
import subprocess
import sys
import urllib.request
from pathlib import Path

MODELS = Path("models")
SILERO = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
VOICES = ["en_US-lessac-medium", "en_US-ryan-medium"]   # agent voice, fake caller voice

MODELS.mkdir(exist_ok=True)
if not (MODELS / "silero_vad.onnx").exists():
    urllib.request.urlretrieve(SILERO, MODELS / "silero_vad.onnx")
for voice in VOICES:
    if not (MODELS / f"{voice}.onnx").exists():
        subprocess.run([sys.executable, "-m", "piper.download_voices", voice, "--data-dir", str(MODELS)], check=True)
print("models ready:", ", ".join(sorted(p.name for p in MODELS.iterdir())))
