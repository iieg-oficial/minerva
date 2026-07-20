from datetime import datetime, timezone

from sqlmodel import Session, select

from app.modules.users.models import User


def normalize_email(email: str) -> str:
    """El correo es la identidad del usuario y se trata case-insensitive: sin esto
    `Alice@x` y `alice@x` serían dos cuentas distintas. Se normaliza en el repo,
    frontera común de todo lookup/escritura (registro, login, dev-login, admin)."""
    return email.strip().lower()


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == normalize_email(email))
        return self.session.exec(statement).first()

    def list_all(self, offset: int = 0, limit: int = 100) -> tuple[list[User], int]:
        statement = select(User).offset(offset).limit(limit)
        items = self.session.exec(statement).all()
        total = self.session.exec(select(User)).all()
        return items, len(total)

    def create(self, user: User) -> User:
        user.email = normalize_email(user.email)
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def update(self, user: User, commit: bool = True) -> User:
        user.email = normalize_email(user.email)
        user.updated_at = datetime.now(timezone.utc)
        self.session.add(user)
        # commit=False deja el cambio pendiente para que el router lo confirme DESPUÉS de
        # escribir las invalidaciones en Redis (fail-closed: si Redis falla, se hace rollback).
        if commit:
            self.session.commit()
            self.session.refresh(user)
        else:
            self.session.flush()
        return user
