# LiveLine

A voice AI phone agent that runs entirely on one computer.
A caller rings a Twilio or Plivo number and talks to a dental clinic receptionist.
Speech to text, the language model and text to speech all run locally on the GPU,
so a call costs nothing beyond the phone minutes.

| Stage | Model |
|---|---|
| Turn taking and barge-in | Silero VAD |
| Speech to text | faster-whisper `base.en` on CUDA |
| Language model | Llama 3.2 3B through Ollama |
| Text to speech | Piper `en_US-lessac-medium` |

The agent speaks its first sentence while the model is still writing the rest.
If the caller talks over the agent, its queued audio is dropped at once.
A dashboard at `http://localhost:8000` shows the time of every stage of every turn
and lets you change settings during a call.

Measured on an RTX 3050 laptop GPU (4 GB) with `tools/fake_call.py`:
replies start 1.6 s after the caller stops talking (mean of 46 replies),
and barge-in clears the agent's audio in 79 ms (mean of 9 calls).

## Run with Docker

Needs an NVIDIA GPU and the NVIDIA Container Toolkit.

```
docker compose up
```

## Run without Docker

Needs Python 3.12, an NVIDIA GPU and [Ollama](https://ollama.com).

```
python -m venv .venv
.venv\Scripts\activate             # Linux: source .venv/bin/activate
pip install -r requirements.txt
pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
python tools/download_models.py
python -m liveline
```

## Test without a phone

```
pytest                                          # no GPU needed
python tools/fake_call.py --calls 50 --barge-in # five scripted intents, prints latency
```

## Connect a real number

1. Expose port 8000 (for example `ngrok http 8000`) and set `public_host` in the dashboard.
2. Twilio: set the number's voice webhook to `https://<host>/twilio/voice`.
3. Plivo: set the application's answer URL to `https://<host>/plivo/answer`.
