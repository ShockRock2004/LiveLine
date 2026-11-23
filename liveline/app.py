import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response

from liveline.engines import load_engines
from liveline.metrics import CallLog
from liveline.session import CallSession
from liveline.telephony import Plivo, Twilio

DASHBOARD = Path(__file__).with_name("dashboard.html")


def create_app(settings, engines=None) -> FastAPI:
    call_log = CallLog()
    state = {"engines": engines}

    @asynccontextmanager
    async def lifespan(app):
        if state["engines"] is None:
            state["engines"] = await load_engines(settings)
        yield

    app = FastAPI(title="LiveLine", lifespan=lifespan)

    @app.api_route("/twilio/voice", methods=["GET", "POST"])
    async def twilio_voice():
        return Response(Twilio.answer(f"wss://{settings.public_host}/twilio/media"), media_type="text/xml")

    @app.api_route("/plivo/answer", methods=["GET", "POST"])
    async def plivo_answer():
        return Response(Plivo.answer(f"wss://{settings.public_host}/plivo/media"), media_type="text/xml")

    @app.websocket("/twilio/media")
    async def twilio_media(ws: WebSocket):
        await run_call(ws, Twilio())

    @app.websocket("/plivo/media")
    async def plivo_media(ws: WebSocket):
        await run_call(ws, Plivo())

    async def run_call(ws: WebSocket, phone) -> None:
        await ws.accept()
        lock = asyncio.Lock()   # the reply task and the listener both send

        async def send(text: str) -> None:
            async with lock:
                await ws.send_text(text)

        session = CallSession(send, phone, state["engines"], settings, call_log)
        try:
            while True:
                await session.handle(await ws.receive_text())
        except WebSocketDisconnect:
            pass
        finally:
            session.close()

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD.read_text(encoding="utf-8")

    @app.get("/api/settings")
    async def get_settings():
        return vars(settings)

    @app.put("/api/settings")
    async def put_settings(request: Request):
        settings.update(await request.json())
        settings.save()
        return vars(settings)

    @app.get("/api/calls")
    async def calls(limit: int = 20):
        return call_log.recent(limit)

    @app.get("/api/summary")
    async def summary():
        return call_log.summary()

    @app.get("/health")
    async def health():
        return {"ready": state["engines"] is not None}

    return app
