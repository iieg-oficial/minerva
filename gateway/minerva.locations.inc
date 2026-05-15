# Rutas de Minerva (Authentik) para gateway-hub.
# Incluir dentro del server :443 de gateway.conf.template:
#   include /etc/nginx/includes/minerva.locations.inc;
#
# Requiere el upstream `minerva` (ver gateway/upstreams.conf).

# Endpoint del embedded outpost. DEBE quedar accesible sin autenticacion:
# lo consultan el `auth_request` de las apps protegidas y los redirects del
# flujo de login. No aplicar bot-protection ni rate limit agresivo aqui.
location ^~ /outpost.goauthentik.io/ {
    proxy_pass http://minerva/outpost.goauthentik.io/;
    include /etc/nginx/includes/proxy-params.inc;
    proxy_set_header X-Original-URL $scheme://$http_host$request_uri;
    auth_request_set $auth_cookie $upstream_http_set_cookie;
    add_header Set-Cookie $auth_cookie;
}

# UI de Authentik: login, ejecucion de flows y panel de administracion del IdP.
#
# NOTA (ver docs/pendientes/conexion-ecosistema.md): servir Authentik bajo el
# subpath /auth/ es la opcion disponible hoy (no hay subdominio: el wildcard
# *.jalisco.gob.mx no cubre auth.iieg.jalisco.gob.mx y no controlamos el DNS).
# Validar el subpath en el primer despliegue; si los assets/flows rompen, la
# alternativa es gestionar un subdominio dedicado.
location ^~ /auth/ {
    proxy_pass http://minerva/;
    include /etc/nginx/includes/proxy-params.inc;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffer_size 16k;
    proxy_buffers 8 16k;
}
