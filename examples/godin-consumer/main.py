"""Ejemplo mínimo de un sistema consumidor (Godín) integrado con Minerva.

Ejecuta Minerva Dev Kit primero (docker compose up) e importa el manifiesto de
Godín. Luego:

    export MINERVA_ISSUER_URL=http://localhost:9000
    export MINERVA_APPLICATION_CODE=godin
    export MINERVA_JWT_SECRET=dev-secret
    uvicorn main:app --reload --port 8000

Obtén un token con `POST http://localhost:9000/api/v1/auth/dev-login` y úsalo
como `Authorization: Bearer <token>` contra estos endpoints.
"""
from fastapi import Depends, FastAPI

from minerva_sdk.fastapi import get_current_user, require_permission

app = FastAPI(title="Godín (consumidor de Minerva)")


@app.get("/whoami")
def whoami(user=Depends(get_current_user)):
    return {"sub": user["sub"], "email": user.get("email")}


@app.get("/oficios")
def listar_oficios(user=Depends(require_permission("godin.oficios.view"))):
    return {"oficios": [], "user": user.get("email")}


@app.post("/oficios")
def crear_oficio(user=Depends(require_permission("godin.oficios.create"))):
    return {"message": "Oficio creado", "user": user.get("email")}


@app.post("/oficios/{oficio_id}/autorizar")
def autorizar_oficio(oficio_id: str, user=Depends(require_permission("godin.oficios.authorize"))):
    return {"message": f"Oficio {oficio_id} autorizado", "user": user.get("email")}
