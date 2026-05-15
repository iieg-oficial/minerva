# Consola de Acervo (Filer UI de SeaweedFS) protegida por el forward auth de Minerva.
# Incluir dentro del server :443 de gateway.conf.template, DESPUES de minerva.locations.inc:
#   include /etc/nginx/includes/acervo-console.locations.inc;
#
# Requiere:
#   - upstreams `acervo_console` y `minerva`  (gateway/upstreams.conf)
#   - include `minerva.locations.inc`         (define /outpost.goauthentik.io/)
#
# Flujo: cada request a /acervo/console/ se valida con auth_request contra el
# embedded outpost. Sin sesion -> 401 -> @minerva_signin -> login de Authentik.
# Con sesion, el outpost responde 200 y pasa los headers X-authentik-*.

location ^~ /acervo/console/ {
    auth_request /outpost.goauthentik.io/auth/nginx;
    error_page 401 = @minerva_signin;

    auth_request_set $auth_cookie $upstream_http_set_cookie;
    add_header Set-Cookie $auth_cookie;

    # Identidad del usuario autenticado, reenviada al upstream.
    auth_request_set $authentik_username $upstream_http_x_authentik_username;
    auth_request_set $authentik_groups $upstream_http_x_authentik_groups;
    auth_request_set $authentik_email $upstream_http_x_authentik_email;
    proxy_set_header X-authentik-username $authentik_username;
    proxy_set_header X-authentik-groups $authentik_groups;
    proxy_set_header X-authentik-email $authentik_email;

    proxy_pass http://acervo_console/;
    include /etc/nginx/includes/proxy-params.inc;
    proxy_set_header Accept-Encoding "";

    # El Filer UI de SeaweedFS usa rutas de assets absolutas. Si bajo el prefijo
    # /acervo/console/ los assets rompen, reescribir aqui con sub_filter (mismo
    # patron que tenia la vieja consola de MinIO). Ver docs/pendientes.
}

# Maneja el 401 del auth_request: arranca el SSO de Minerva y vuelve a la URL pedida.
location @minerva_signin {
    internal;
    add_header Set-Cookie $auth_cookie;
    return 302 /outpost.goauthentik.io/start?rd=$request_uri;
}
