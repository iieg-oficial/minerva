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

- [ ] Backend: ruff (check + format), compilacion y pytest pasan
- [ ] Frontend: lint y build pasan
- [ ] Docker: `docker compose config` y `docker compose build` pasan
- [ ] Migraciones de Alembic al dia
- [ ] Variables de entorno documentadas en `.env.example`
- [ ] PR develop → main creado y aprobado

## Checklist de cierre

- [ ] PR mergeado a main
- [ ] Tag de version creado en main (`git tag v...`)
- [ ] Issue cerrado

## Notas

<!-- Riesgos, dependencias externas o instrucciones de despliegue especiales -->
