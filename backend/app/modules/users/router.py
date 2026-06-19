from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.dependencies.admin import require_minerva_admin
from app.core.dependencies.auth import get_current_user
from app.core.dependencies.db import get_db
from app.modules.users.schemas import UserCreate, UserRead, UserStatusUpdate, UserUpdate
from app.modules.users.service import UserService
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(require_minerva_admin)])


def get_user_service(session: Session = Depends(get_db)) -> UserService:
    return UserService(session)


@router.get("", response_model=PaginatedResponse[UserRead])
def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: UserService = Depends(get_user_service),
    _current_user: dict = Depends(get_current_user),
):
    users, total = service.list_users(offset, limit)
    return PaginatedResponse.create(users, total)


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: str,
    service: UserService = Depends(get_user_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.get_user(user_id)


@router.post("", response_model=UserRead, status_code=201)
def create_user(
    data: UserCreate,
    request: Request,
    service: UserService = Depends(get_user_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.create_user(data)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: str,
    data: UserUpdate,
    service: UserService = Depends(get_user_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.update_user(user_id, data)


@router.patch("/{user_id}/status", response_model=UserRead)
def update_user_status(
    user_id: str,
    data: UserStatusUpdate,
    service: UserService = Depends(get_user_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.update_status(user_id, data)
