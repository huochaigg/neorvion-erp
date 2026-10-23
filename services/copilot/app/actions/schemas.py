from pydantic import BaseModel, ConfigDict, Field

from app.schemas.action_proposal import ActionBody


class ProposeActionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: ActionBody


class ValidateActionProposalArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: int = Field(gt=0)
    expected_revision: int = Field(gt=0)
