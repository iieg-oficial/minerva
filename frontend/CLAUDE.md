# CLAUDE.md — Frontend de Minerva

Panel administrativo en **React 19 + Ant Design 6 + Vite**. Lee primero el `CLAUDE.md` de la raíz
para la visión y reglas globales. Este archivo cubre las reglas del frontend.

## Stack

- **React 19** + **react-dom 19**
- **Ant Design 6** (`antd`) + `@ant-design/icons` 6 — librería de UI principal
- **Vite 6** (build/dev) · **React Router DOM 7** (routing) · **axios 1.7** (HTTP)
- `type: module` (ESM). No hay TypeScript: el código es `.jsx`.

## Entorno y comandos

```bash
cd frontend
npm install
npm run dev      # Vite dev server en :3000 (host 0.0.0.0)
npm run build    # build de producción a dist/
npm run lint     # ESLint
npm run format   # Prettier (escribe cambios)
```

En desarrollo Vite proxea `/api` al backend (ver `vite.config.js`). En producción lo hace Nginx
(`nginx.conf`). ⚠️ Revisa el gotcha de puertos 8000/9000 en el CLAUDE.md raíz si tocas el proxy.

## Arquitectura feature-sliced (separación de responsabilidades)

```
src/
├── api/                 # ÚNICA capa que habla HTTP. Un archivo por dominio.
│   ├── client.js        # instancia axios + interceptores (token, manejo de 401)
│   ├── users.js         # listUsers/getUser/createUser/... (funciones async que usan `client`)
│   └── ...
├── features/            # UI organizada por dominio
│   ├── auth/            # { components, pages } (LoginPage, ProtectedRoute, ...)
│   └── admin/           # { layout, components, pages } (UsersPage, RolesPage, ...)
├── App.jsx              # rutas + tema de AntD
├── main.jsx            # entry point (Router + AntD ConfigProvider)
└── index.css           # estilos globales + fuentes
```

Reglas:
- **Las llamadas HTTP van SOLO en `src/api/*.js`**, usando el `client` de axios. Un componente
  **nunca** importa `axios` ni arma URLs directamente: importa funciones de `src/api/`.
- **Una página/feature por dominio.** Componentes reutilizables en `features/<area>/components/`.
- Manejo de errores con `message`/`notification` de AntD (`App.useApp()`), no `alert`.
- **Sesión y multi-cuenta (patrón BFF):** el panel **no** guarda tokens en el navegador. La fuente de
  verdad del multi-cuenta es el **backend** (contenedor en Redis); el navegador solo trae una cookie
  opaca HttpOnly. `src/api/session.js` es un cliente + caché en memoria de ese estado
  (`fetchSession`/`getSessions`/`getActive`/`isExpired`/`setActive`/`removeSession`/`deactivate`/
  `logoutAll` + `getCsrf`/`setCsrf`). El estado reactivo lo expone `SessionProvider`
  (`features/auth/SessionContext.jsx`) vía `useSession()` (`{loading, active, accounts, isAdmin,
  refresh}`), que consumen `ProtectedRoute`, `AccountSelector`, `AdminLayout`, `LoginPage`,
  `AuthorizePage`. `api/client.js` va con `withCredentials` y adjunta `X-CSRF-Token` en mutaciones.
  `logout()` es **suave** (cierra la cuenta activa sin revocar); `logoutAll()` y quitar cuenta revocan
  en el backend. El selector (`components/AccountSelector.jsx`) y el formulario de login comparten el
  shell `components/AuthShell.jsx`. **No** vuelvas a meter tokens/`is_admin` en `localStorage`.
- **Al crear una página nueva, registra su ruta** en `App.jsx` (dentro de `ProtectedRoute` si aplica).

## Convenciones

- Identificadores en inglés (`camelCase`); labels, mensajes y textos de UI en **español**.
- Usa los alias de import: `@` → `src`, `@features` → `src/features`, `@app` → `src/app`.
- Componentes funcionales con hooks (`useState`, `useEffect`, `useCallback`). Sin componentes de clase.
- Usa componentes de AntD (Table, Modal, Form, ...) en vez de HTML crudo cuando exista equivalente,
  para mantener consistencia visual con el resto del panel.

## Calidad (antes de terminar)

```bash
npm run lint     # debe pasar sin errores
npm run build    # debe compilar sin errores
```
