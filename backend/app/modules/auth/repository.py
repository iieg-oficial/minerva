import uuid
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select, update

from app.modules.auth.models import AuthCode, RefreshToken


class AuthCodeRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_code(
        self,
        client_id: str,
        user_id: str,
        redirect_uri: str,
        scope: str | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        nonce: str | None = None,
        auth_time: int | None = None,
    ) -> AuthCode:
        code = str(uuid.uuid4())
        auth_code = AuthCode(
            code=code,
            client_id=client_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scope=scope,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            nonce=nonce,
            auth_time=auth_time,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        self.session.add(auth_code)
        self.session.commit()
        return auth_code

    def get_by_code(self, code: str) -> AuthCode | None:
        statement = select(AuthCode).where(AuthCode.code == code, AuthCode.used.is_(False))
        return self.session.exec(statement).first()

    def mark_used(self, auth_code: AuthCode) -> bool:
        """Reclama el código de forma atómica. False si otro canje concurrente ya lo tomó."""
        result = self.session.execute(
            update(AuthCode).where(AuthCode.id == auth_code.id, AuthCode.used.is_(False)).values(used=True)
        )
        self.session.commit()
        return result.rowcount == 1


class RefreshTokenRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        token_hash: str,
        family_id: str,
        user_id: str,
        client_id: str,
        scope: str | None,
        access_jti: str | None,
        ttl_days: int,
        commit: bool = True,
    ) -> RefreshToken:
        refresh = RefreshToken(
            token_hash=token_hash,
            family_id=family_id,
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            access_jti=access_jti,
            expires_at=datetime.now(timezone.utc) + timedelta(days=ttl_days),
        )
        self.session.add(refresh)
        # commit=False deja el nuevo refresh pendiente: en la rotación, el router confirma
        # tras blacklistear en Redis el access_jti viejo (fail-closed).
        if commit:
            self.session.commit()
            self.session.refresh(refresh)
        else:
            self.session.flush()
        return refresh

    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return self.session.exec(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).first()

    def mark_rotated(self, refresh: RefreshToken, commit: bool = True) -> bool:
        """Reclama la rotación de forma atómica. False si ya fue rotado/revocado (reúso)."""
        result = self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == refresh.id, RefreshToken.status == "active")
            .values(status="rotated")
        )
        self.session.commit() if commit else self.session.flush()
        return result.rowcount == 1

    def revoke(self, refresh: RefreshToken) -> None:
        refresh.status = "revoked"
        self.session.add(refresh)
        self.session.commit()

    def revoke_family(self, family_id: str, commit: bool = True) -> list[str]:
        """Revoca toda la familia (detección de reúso). Devuelve los access_jti
        afectados para poder ponerlos en la blacklist. Con commit=False deja la
        revocación pendiente para que el router confirme tras blacklistear en Redis."""
        members = list(self.session.exec(select(RefreshToken).where(RefreshToken.family_id == family_id)).all())
        jtis: list[str] = []
        for member in members:
            if member.status != "revoked":
                member.status = "revoked"
                self.session.add(member)
            if member.access_jti:
                jtis.append(member.access_jti)
        self.session.commit() if commit else self.session.flush()
        return jtis

    def revoke_all_for_user(self, user_id: str, commit: bool = True) -> list[str]:
        """Revoca todos los refresh tokens vigentes del usuario (cambio de
        credenciales/status): así ningún consumidor puede seguir emitiendo access
        tokens. Devuelve los access_jti afectados para ponerlos en la blacklist.
        Con commit=False deja la revocación pendiente para confirmar tras Redis."""
        members = list(self.session.exec(select(RefreshToken).where(RefreshToken.user_id == user_id)).all())
        jtis: list[str] = []
        for member in members:
            if member.status != "revoked":
                member.status = "revoked"
                self.session.add(member)
                if member.access_jti:
                    jtis.append(member.access_jti)
        self.session.commit() if commit else self.session.flush()
        return jtis
