"""Voice module HTTP and WebSocket routes."""

import asyncio
import base64
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from api.config import get_settings
from modules.shared.db import get_session
from modules.shared.types import PipelineEventType
from modules.voice import repository as voice_repo
from modules.voice.pipeline import VoicePipeline
from modules.voice.protocol import (
    ClientMessage,
    ClientMessageType,
    ServerMessage,
    ServerMessageType,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])


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


@router.get("/voice/history")
async def voice_history(limit: int = 20, offset: int = 0) -> list[dict]:
    async with get_session() as session:
        rows = await voice_repo.list_sessions(session, limit=limit, offset=offset)
        return [
            {
                "session_id": str(vs.id),
                "title": vs.title,
                "created_at": vs.created_at.isoformat(),
                "last_activity_at": vs.last_activity_at.isoformat(),
                "message_count": count,
            }
            for vs, count in rows
        ]


@router.get("/voice/history/{session_id}")
async def voice_history_detail(session_id: uuid.UUID) -> dict:
    async with get_session() as session:
        vs = await voice_repo.get_session_by_id(session, session_id)
        if not vs:
            raise HTTPException(404, "Voice session not found")
        messages = await voice_repo.get_messages(session, session_id)
        return {
            "session_id": str(vs.id),
            "title": vs.title,
            "created_at": vs.created_at.isoformat(),
            "messages": [
                {"role": m.role, "content": m.content} for m in messages
            ],
        }


@router.delete("/voice/history/{session_id}")
async def voice_history_delete(session_id: uuid.UUID) -> dict:
    async with get_session() as session:
        deleted = await voice_repo.delete_session(session, session_id)
    if not deleted:
        raise HTTPException(404, "Voice session not found")
    return {"deleted": True}


@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    settings = get_settings()
    interrupt_enabled = settings.voice_interrupt_enabled
    pipeline = _create_pipeline()
    audio_buffer = bytearray()
    turn_task: asyncio.Task[None] | None = None
    history_session_id: uuid.UUID | None = None

    async def persist_turn(user_text: str, assistant_text: str) -> None:
        """Save one turn to history; DB failures never break the live session."""
        nonlocal history_session_id
        user_text = user_text.strip()
        assistant_text = assistant_text.strip()
        if not user_text and not assistant_text:
            return
        try:
            async with get_session() as db:
                if history_session_id is None:
                    vs = await voice_repo.create_session(
                        db, title=user_text or assistant_text
                    )
                    history_session_id = vs.id
                turn_messages = []
                if user_text:
                    turn_messages.append(("user", user_text))
                if assistant_text:
                    turn_messages.append(("assistant", assistant_text))
                await voice_repo.append_messages(
                    db, history_session_id, turn_messages
                )
        except Exception:
            logger.exception("Failed to persist voice turn to history")

    async def emit_turn(pcm: bytes) -> None:
        user_text = ""
        assistant_parts: list[str] = []
        try:
            async for event in pipeline.handle_speech_end(pcm):
                if event.type == PipelineEventType.STT_FINAL:
                    user_text = event.data.get("text", "")
                elif event.type == PipelineEventType.LLM_DELTA:
                    assistant_parts.append(event.data.get("text", ""))
                await websocket.send_json(
                    _pipeline_event_to_server_message(
                        event.type,
                        event.data,
                    ).model_dump()
                )
        finally:
            # Also runs on interrupt (cancellation): partial replies are kept.
            await persist_turn(user_text, "".join(assistant_parts))

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
