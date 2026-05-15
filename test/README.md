# Ambiente de prueba de Minerva

Valida el flujo completo de **forward auth** en local, sin tocar gateway-hub ni
Acervo. Si funciona aquí, funciona en el ecosistema: el `gateway-test` monta los
**mismos** snippets de `gateway/` que después se copian a gateway-hub.

```
navegador → gateway-test (nginx :8088) → auth_request → embedded outpost (minerva-server)
            → login Authentik (/auth/) → console-dummy (whoami, hace de consola de Acervo)
```

## Preparación

En el `.env` de la raíz, usar valores locales para que los blueprints generen
URLs correctas para la prueba:

```bash
MINERVA_EXTERNAL_URL=http://localhost:8088
MINERVA_COOKIE_DOMAIN=localhost
```

## Correr

```bash
make up         # 1. levanta el stack de Authentik (espera a que quede healthy)
make test-up    # 2. levanta gateway-test + console-dummy
```

## Validar

1. **UI de Authentik** — abrir `http://localhost:8088/auth/`
   Login con `AUTHENTIK_BOOTSTRAP_EMAIL` / `AUTHENTIK_BOOTSTRAP_PASSWORD` del `.env`.

2. **Grupos RBAC** — en `Directory → Groups` deben aparecer `tetlamamakani`,
   `editora`, `externo` y los `proj-*` (los crea `blueprints/00-groups.yaml`).

3. **App protegida** — en una ventana de incógnito abrir
   `http://localhost:8088/acervo/console/`
   - Sin sesión → redirige al login de Minerva.
   - Con un usuario en el grupo `tetlamamakani` o `proj-acervo` → llega al whoami,
     que muestra los headers `X-Authentik-*` reenviados.
   - Con un usuario sin esos grupos → Authentik niega el acceso.

4. **Provider y outpost** — en `Applications → Providers` debe estar
   "Acervo Console" (proxy, forward_single) y en `Outposts` el embedded outpost
   debe listarlo.

## Bajar

```bash
make test-down  # baja gateway-test + console-dummy
make down       # baja el stack de Authentik
```

## Notas

- El dummy `whoami` no tiene assets, así que aísla la prueba al **flujo de auth**.
  El subpath del Filer UI real de SeaweedFS es un detalle aparte de la conexión
  (ver `../docs/pendientes/conexion-ecosistema.md`).
- `gateway-test` se une a la red `minerva-net` que crea el compose principal;
  por eso el stack principal debe estar arriba antes de `make test-up`.
