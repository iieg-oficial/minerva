## Issue

Closes #

## Que se hizo

<!-- Resumen breve de los cambios -->

## Tipo

- [ ] `feat` - Nueva funcionalidad
- [ ] `fix` - Correccion de bug
- [ ] `refactor` - Cambio interno sin alterar comportamiento
- [ ] `docs` - Documentacion
- [ ] `chore` - Configuracion, tooling o mantenimiento
- [ ] `test` - Pruebas

## Alcance

- [ ] Backend
- [ ] Frontend
- [ ] SDK (`minerva_sdk`)
- [ ] Manifiestos
- [ ] Docker / Compose
- [ ] Base de datos / migraciones
- [ ] Documentacion

## Validacion

- [ ] Backend: `cd backend && conda run -n minerva ruff check app alembic tests`
- [ ] Backend: `cd backend && conda run -n minerva ruff format --check app alembic tests`
- [ ] Backend: `cd backend && conda run -n minerva pytest tests/ -v`
- [ ] Frontend: `cd frontend && npm run lint`
- [ ] Frontend: `cd frontend && npm run build`
- [ ] Docker: `docker compose config`
- [ ] Docker: `docker compose build`
- [ ] No aplica. Motivo:

## Notas para review

<!-- Riesgos, decisiones o puntos especificos para revisar -->
