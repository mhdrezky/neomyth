"""Voice module HTTP and WebSocket routes."""

import asyncio
import base64
from pathlib import Path

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api.config import get_settings
from modules.shared.types import PipelineEventType
from modules.voice.pipeline import VoicePipeline
from modules.voice.protocol import (
    ClientMessage,
    ClientMessageType,
    ServerMessage,
    ServerMessageType,
)

router = APIRouter(tags=["voice"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _pipeline_event_to_server_message(event_type: PipelineEventType, data: dict) -> ServerMessage:
    mapping = {
        PipelineEventType.STT_FINAL: ServerMessageType.STT_FINAL,
        PipelineEventType.LLM_DELTA: ServerMessageType.LLM_DELTA,
        PipelineEventType.TTS_AUDIO: ServerMessageType.TTS_AUDIO,
        PipelineEventType.STATE: ServerMessageType.STATE,
        PipelineEventType.ERROR: ServerMessageType.ERROR,
    }
    return ServerMessage(type=mapping[event_type], data=data)


def _create_pipeline() -> VoicePipeline:
    settings = get_settings()
    return VoicePipeline(
        stt_base_url=settings.stt_base_url,
        llm_base_url=settings.vllm_base_url,
        llm_model=settings.vllm_model,
        tts_base_url=settings.tts_base_url,
        tts_voice=settings.tts_voice,
        llm_max_tokens=settings.vllm_max_tokens,
        llm_temperature=settings.vllm_temperature,
    )


@router.get("/voice", response_class=HTMLResponse)
async def voice_ui(request: Request) -> HTMLResponse:
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "voice.html",
        {
            "request": request,
            "interrupt_enabled": settings.voice_interrupt_enabled,
        },
    )


@router.get("/voice/health")
async def voice_workers_health() -> dict[str, bool]:
    pipeline = _create_pipeline()
    try:
        return await pipeline.workers_health()
    finally:
        await pipeline.close()


@router.post("/voice/debug")
async def voice_debug(request: Request) -> dict[str, str]:
    body = await request.body()
    pipeline = _create_pipeline()
    try:
        return await pipeline.debug_chain(body)
    finally:
        await pipeline.close()


@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    settings = get_settings()
    interrupt_enabled = settings.voice_interrupt_enabled
    pipeline = _create_pipeline()
    audio_buffer = bytearray()
    turn_task: asyncio.Task[None] | None = None

    async def emit_turn(pcm: bytes) -> None:
        try:
            async for event in pipeline.handle_speech_end(pcm):
                await websocket.send_json(
                    _pipeline_event_to_server_message(
                        event.type,
                        event.data,
                    ).model_dump()
                )
        except asyncio.CancelledError:
            raise

    async def cancel_active_turn() -> None:
        nonlocal turn_task
        pipeline.cancel()
        if turn_task and not turn_task.done():
            turn_task.cancel()
            try:
                await turn_task
            except asyncio.CancelledError:
                pass
        turn_task = None

    listening_event = pipeline.set_listening()
    await websocket.send_json(
        ServerMessage.config(interrupt_enabled=interrupt_enabled).model_dump()
    )
    await websocket.send_json(
        _pipeline_event_to_server_message(
            listening_event.type,
            listening_event.data,
        ).model_dump()
    )

    try:
        while True:
            raw = await websocket.receive_text()
            msg = ClientMessage.model_validate_json(raw)

            if msg.type == ClientMessageType.PING:
                await websocket.send_json(
                    ServerMessage(type=ServerMessageType.PONG).model_dump()
                )
                continue

            if msg.type == ClientMessageType.AUDIO_CHUNK:
                chunk_b64 = msg.data.get("audio", "")
                if chunk_b64:
                    audio_buffer.extend(base64.b64decode(chunk_b64))
                continue

            if msg.type in (ClientMessageType.SPEECH_START, ClientMessageType.INTERRUPT):
                if interrupt_enabled:
                    await cancel_active_turn()
                    audio_buffer.clear()
                    await websocket.send_json(
                        ServerMessage.state("listening").model_dump()
                    )
                continue

            if msg.type == ClientMessageType.SPEECH_END:
                pcm = bytes(audio_buffer)
                audio_buffer.clear()
                if not pcm:
                    continue

                await cancel_active_turn()
                turn_task = asyncio.create_task(emit_turn(pcm))
    except WebSocketDisconnect:
        await cancel_active_turn()
    finally:
        await cancel_active_turn()
        await pipeline.close()
