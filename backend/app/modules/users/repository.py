from datetime import datetime, timezone

from sqlmodel import Session, select

from app.modules.users.models import User


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return self.session.exec(statement).first()

    def list_all(self, offset: int = 0, limit: int = 100) -> tuple[list[User], int]:
        statement = select(User).offset(offset).limit(limit)
        items = self.session.exec(statement).all()
        total = self.session.exec(select(User)).all()
        return items, len(total)

    def create(self, user: User) -> User:
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def update(self, user: User) -> User:
        user.updated_at = datetime.now(timezone.utc)
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user
