from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_proposal import ActionProposal, ProposalRevision, ProposalValidation
from app.models.conversation import Conversation, Message


class ActionProposalRepository:
    def __init__(self, session: AsyncSession, tenant_id: int, user_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def owned_conversation(self, conversation_id: int) -> Conversation | None:
        return await self.session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == self.tenant_id,
                Conversation.user_id == self.user_id,
                Conversation.status == "ACTIVE",
                Conversation.deleted_at.is_(None),
            )
        )

    async def owned_message(self, message_id: int, conversation_id: int) -> Message | None:
        return await self.session.scalar(
            select(Message).where(
                Message.id == message_id,
                Message.tenant_id == self.tenant_id,
                Message.user_id == self.user_id,
                Message.conversation_id == conversation_id,
            )
        )

    async def by_idempotency(self, key: str) -> ActionProposal | None:
        return await self.session.scalar(
            select(ActionProposal).where(
                ActionProposal.tenant_id == self.tenant_id,
                ActionProposal.user_id == self.user_id,
                ActionProposal.idempotency_key == key,
            )
        )

    async def get(self, proposal_id: int, *, lock: bool = False) -> ActionProposal | None:
        statement = select(ActionProposal).where(
            ActionProposal.id == proposal_id,
            ActionProposal.tenant_id == self.tenant_id,
            ActionProposal.user_id == self.user_id,
            ActionProposal.deleted_at.is_(None),
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list(
        self,
        page: int,
        page_size: int,
        conversation_id: int | None = None,
        action_types: tuple[str, ...] = (),
    ) -> tuple[list[ActionProposal], int]:
        filters = (
            ActionProposal.tenant_id == self.tenant_id,
            ActionProposal.user_id == self.user_id,
            ActionProposal.deleted_at.is_(None),
        )
        if conversation_id is not None:
            filters = (*filters, ActionProposal.conversation_id == conversation_id)
        if action_types:
            filters = (*filters, ActionProposal.action_type.in_(action_types))
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(ActionProposal).where(*filters)
            )
            or 0
        )
        rows = list(
            (
                await self.session.scalars(
                    select(ActionProposal)
                    .where(*filters)
                    .order_by(ActionProposal.updated_at.desc(), ActionProposal.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return rows, total

    async def validation(self, proposal_id: int, revision: int) -> ProposalValidation | None:
        return await self.session.scalar(
            select(ProposalValidation).where(
                ProposalValidation.tenant_id == self.tenant_id,
                ProposalValidation.proposal_id == proposal_id,
                ProposalValidation.revision == revision,
            )
        )

    async def revisions(self, proposal_id: int) -> list[ProposalRevision]:
        return list(
            (
                await self.session.scalars(
                    select(ProposalRevision)
                    .where(
                        ProposalRevision.tenant_id == self.tenant_id,
                        ProposalRevision.proposal_id == proposal_id,
                    )
                    .order_by(ProposalRevision.revision.desc())
                )
            ).all()
        )
