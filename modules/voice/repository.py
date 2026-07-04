"""CRUD operations for voice conversation history."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.shared.db.models import VoiceMessage, VoiceSession

MAX_TITLE_CHARS = 80


async def create_session(session: AsyncSession, *, title: str) -> VoiceSession:
    voice_session = VoiceSession(title=title.strip()[:MAX_TITLE_CHARS] or "Voice session")
    session.add(voice_session)
    await session.flush()
    return voice_session


async def get_session_by_id(
    session: AsyncSession, session_id: uuid.UUID
) -> VoiceSession | None:
    return await session.get(VoiceSession, session_id)


async def list_sessions(
    session: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
) -> list[tuple[VoiceSession, int]]:
    """Return sessions newest-first, each with its message count."""
    stmt = (
        select(VoiceSession, func.count(VoiceMessage.id))
        .outerjoin(VoiceMessage, VoiceMessage.session_id == VoiceSession.id)
        .group_by(VoiceSession.id)
        .order_by(VoiceSession.last_activity_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def get_messages(
    session: AsyncSession, session_id: uuid.UUID
) -> list[VoiceMessage]:
    stmt = (
        select(VoiceMessage)
        .where(VoiceMessage.session_id == session_id)
        .order_by(VoiceMessage.sort_order)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def append_messages(
    session: AsyncSession,
    session_id: uuid.UUID,
    messages: list[tuple[str, str]],
) -> list[VoiceMessage]:
    """Append (role, content) pairs preserving order; bumps last_activity_at."""
    if not messages:
        return []

    stmt = select(func.coalesce(func.max(VoiceMessage.sort_order), -1)).where(
        VoiceMessage.session_id == session_id
    )
    next_order = (await session.execute(stmt)).scalar_one() + 1

    objs = [
        VoiceMessage(
            session_id=session_id,
            role=role,
            content=content,
            sort_order=next_order + i,
        )
        for i, (role, content) in enumerate(messages)
    ]
    session.add_all(objs)

    voice_session = await session.get(VoiceSession, session_id)
    if voice_session:
        voice_session.last_activity_at = datetime.now(timezone.utc)

    await session.flush()
    return objs


async def delete_session(session: AsyncSession, session_id: uuid.UUID) -> bool:
    voice_session = await session.get(VoiceSession, session_id)
    if not voice_session:
        return False
    await session.delete(voice_session)
    await session.flush()
    return True
