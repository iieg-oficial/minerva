---
name: scaffold-feature-frontend
description: Genera una feature nueva del frontend de Minerva (módulo en src/api/ + página en src/features/) siguiendo el patrón feature-sliced con React 19 + Ant Design 6 + axios. Úsalo cuando se pida crear una nueva página/sección del panel administrativo.
---

# Scaffold de feature frontend

Crea una sección nueva del panel respetando la arquitectura feature-sliced de Minerva. Las
referencias canónicas son `src/api/users.js` y `src/features/admin/pages/UsersPage.jsx`.
Lee `frontend/CLAUDE.md` antes de empezar.

## Paso 0 — Datos

Confirma con el usuario:
- `dominio` del recurso en `camelCase` (ej. `oficios`) y el prefijo de la API en el backend (ej. `/oficios`).
- `area`: `admin` o `auth` (normalmente `admin`).
- Columnas/campos a mostrar y editar.

## Paso 1 — Inspecciona el patrón

Lee `src/api/users.js` (funciones async con el `client`) y una página existente como
`src/features/admin/pages/UsersPage.jsx` (hooks, Table, Modal, Form de AntD, manejo de errores con
`message` de `App.useApp()`). Copia el estilo; no introduzcas patrones nuevos.

## Paso 2 — Capa API: `src/api/<dominio>.js`

Funciones `async` que usan el `client` de axios (importado de `./client`), una por operación:
`list<Dominio>(params)`, `get<Dominio>(id)`, `create<Dominio>(data)`, `update<Dominio>(id, data)`,
etc. Devuelven `res.data`. **No** importes `axios` ni manejes el token aquí (lo hace `client.js`).

## Paso 3 — Página: `src/features/<area>/pages/<Nombre>Page.jsx`

- Componente funcional con `useState`/`useEffect`/`useCallback`.
- Carga datos con la función de `src/api/<dominio>.js`; muestra una `Table` de AntD con paginación
  (`offset`/`limit`).
- CRUD con `Modal` + `Form` de AntD; feedback con `message` de `App.useApp()`.
- Reutiliza componentes de `features/<area>/components/` si aplica.

## Paso 4 — Registra la ruta

Añade la ruta en `src/App.jsx` (dentro de `ProtectedRoute` y del `AdminLayout` si es del panel),
y el enlace de navegación en el menú del `AdminLayout` si corresponde.

## Paso 5 — Verifica

```bash
cd frontend && npm run lint && npm run build
```

Reporta los archivos creados/modificados y confirma que la ruta quedó enlazada en el menú.
