"""Goal CRUD endpoints (computed progress comes from the goal engine)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.base import MessageResponse
from app.schemas.goal import GoalCreate, GoalResponse, GoalUpdate
from app.services.goal_service import GoalService

router = APIRouter(tags=["goals"])


@router.get("/goals", response_model=list[GoalResponse])
def list_goals(session: Session = Depends(get_db)) -> list[GoalResponse]:
    return [GoalResponse(**item) for item in GoalService(session).list()]


@router.post("/goals", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
def create_goal(payload: GoalCreate, session: Session = Depends(get_db)) -> GoalResponse:
    return GoalResponse(**GoalService(session).create(**payload.model_dump()))


@router.get("/goals/{goal_id}", response_model=GoalResponse)
def get_goal(goal_id: int, session: Session = Depends(get_db)) -> GoalResponse:
    return GoalResponse(**GoalService(session).get(goal_id))


@router.patch("/goals/{goal_id}", response_model=GoalResponse)
def update_goal(
    goal_id: int, payload: GoalUpdate, session: Session = Depends(get_db)
) -> GoalResponse:
    fields = payload.model_dump(exclude_unset=True)
    return GoalResponse(**GoalService(session).update(goal_id, **fields))


@router.delete("/goals/{goal_id}", response_model=MessageResponse)
def delete_goal(goal_id: int, session: Session = Depends(get_db)) -> MessageResponse:
    GoalService(session).delete(goal_id)
    return MessageResponse(message="Goal deleted")