## Minerva v1.1.0

Release de credenciales, seguridad y estabilidad del panel.

### Novedades
- Nueva política de contraseñas con medidor de fuerza.
- Los enlaces de acceso pueden redirigir a la app correcta.
- El alta y la edición de usuarios ya no fijan contraseña directamente.
- Correcciones importantes en `/userinfo`, `/no-access`, cambio de contraseña y errores del panel.
- Endurecimiento del login/logout y de las defensas por IP y rate limit.
- Actualización de dependencias críticas (`python-jose`, `axios`).

### Seguridad
- Reforzamos la protección ante abuso de rate limit y abuso del header `X-Forwarded-For`.
- Mejoramos la limpieza de sesión al cerrar sesión.
- Revisamos la compatibilidad de dependencias y cerramos avisos de seguridad.

### Recomendaciones
- Si despliegas en producción, revisa la configuración de `MINERVA_TRUSTED_PROXY`,
  `MINERVA_PROXY_IP` y `MINERVA_SUBNET`.
- Si usas enlaces de recuperación o activación, verifica que `homepage_url` de la app esté bien
  configurada para el destino final.

