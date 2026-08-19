---
name: Release
about: Checklist de preparacion y cierre de un release
title: "[RELEASE] v"
labels: "type:chore"
assignees: ""
---

## Version

<!-- Ej: v0.1.0 -->

## Alcance

<!-- Que modulos o funcionalidades quedan incluidos en este release -->

## Commits incluidos

<!-- Lista de commits o PRs relevantes desde el release anterior -->

## Checklist de preparacion

- [ ] Backend: ruff (check + format), mypy y pytest (SQLite + PostgreSQL) pasan
- [ ] SDK: pytest pasa
- [ ] Frontend: lint, test y build pasan
- [ ] Docker: `docker compose config` y `docker compose build` pasan
- [ ] Migraciones de Alembic al dia
- [ ] Variables de entorno documentadas en `.env.example`
- [ ] Restore de PostgreSQL probado con la misma `MINERVA_KEY_ENCRYPTION_KEY`
- [ ] Redis conserva AOF y revocaciones despues de reiniciar
- [ ] Smoke test TLS/reverse proxy valida cookies `__Host-`, login, PKCE, refresh y logout
- [ ] Un consumidor real completa el flujo de autorizacion y cierre de sesion
- [ ] PR develop → main creado y aprobado

## Checklist de cierre

- [ ] PR mergeado a main
- [ ] Tag de version creado en main (`git tag v...`)
- [ ] Workflow del tag publica las imagenes de backend y frontend
- [ ] Issue cerrado

## Notas

<!-- Riesgos, dependencias externas o instrucciones de despliegue especiales -->
