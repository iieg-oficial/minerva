# Política de seguridad

Minerva es el proveedor de identidad institucional del IIEG: una vulnerabilidad aquí afecta a
todas las plataformas que delegan su login. Agradecemos los reportes responsables.

## Cómo reportar una vulnerabilidad

**Usa el canal privado de GitHub:**
[**Reportar una vulnerabilidad**](https://github.com/iieg-oficial/minerva/security/advisories/new)
(pestaña *Security* → *Report a vulnerability*).

> ⚠️ **No abras un issue público** para reportar una vulnerabilidad, ni la describas en un pull
> request, una discusión o un canal de chat. El aviso privado es visible solo para quien lo
> reporta y para el equipo del repositorio hasta que se publica.

Si el canal privado no está disponible para ti, escribe a quien mantiene el repositorio pidiendo
un canal seguro **sin incluir detalles técnicos del hallazgo** en ese primer mensaje.

## Qué incluir en el reporte

Entre más completo, más rápido podemos confirmarlo:

- **Versión afectada:** el tag (`v0.5.0`) o el commit exacto.
- **Componente:** backend, frontend, `minerva_sdk`, despliegue/configuración.
- **Impacto:** qué logra un atacante (escalar privilegios, saltarse la autenticación, leer datos
  de otro usuario, denegar el servicio…) y qué acceso previo necesita.
- **Pasos de reproducción:** petición HTTP, configuración o script mínimo. Si tienes una prueba de
  concepto, adjúntala.
- **Mitigación**, si se te ocurre alguna.

**No incluyas secretos reales** en el reporte: tokens, contraseñas, contenido de un `.env`, claves
de firma o volcados de base de datos con datos personales. Redáctalos o describe su forma.

## Qué esperar

1. **Acuse de recibo** del aviso privado.
2. **Triage:** confirmamos si es reproducible y en qué versiones, y lo comentamos en el mismo
   aviso privado.
3. **Corrección y publicación:** el arreglo entra por el flujo normal del repositorio y, cuando el
   riesgo lo amerita, se publica un aviso de seguridad con el crédito a quien reportó (si así lo
   desea).

Este es un proyecto de un instituto público, mantenido por un equipo pequeño: **no ofrecemos un
SLA de respuesta, ni recompensas económicas, ni soporte comercial.** Tampoco podemos comprometer
plazos de corrección.

## Versiones soportadas

Solo la línea estable más reciente recibe correcciones de seguridad.

| Versión | Soporte |
|---|---|
| `1.0.x` | ✅ Soportada (a partir de su publicación) |
| `< 1.0` | ❌ Sin soporte — versiones previas al primer release estable |

Antes de reportar, confirma que reproduces el problema en la versión soportada: revisa el
[`CHANGELOG.md`](CHANGELOG.md) por si ya está corregido.

## Fuera de alcance

- Vulnerabilidades de dependencias **ya publicadas** y sin explotación demostrada en Minerva: esas
  las cubre el escaneo `pip-audit` del CI. Si tienes un exploit que sí funciona contra Minerva,
  entonces sí queremos saberlo.
- Reportes generados por un escáner automático sin análisis ni impacto demostrado.
- Configuraciones inseguras deliberadas del modo de desarrollo: `APP_DEBUG=true`,
  `MINERVA_ENABLE_DEV_LOGIN=true` y los secretos default ya **abortan el arranque** en
  producción (`validate_production_config`), y el resto está documentado en
  [`docs/despliegue.md`](docs/despliegue.md). Un despliegue que ignore esa guía no es una
  vulnerabilidad del proyecto.
- Ingeniería social, acceso físico y ataques de denegación de servicio por volumen.
