FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.30.4-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# nginx.conf es plantilla: el entrypoint de la imagen oficial la pasa por envsubst al
# arrancar y la deja en conf.d/default.conf. El filtro limita la sustitución a las
# variables MINERVA_*, para no tocar las propias de nginx ($remote_addr, $host...).
# MINERVA_TRUSTED_PROXY es el proxy cuyo X-Forwarded-For se cree; por defecto ninguno.
ENV NGINX_ENVSUBST_FILTER=^MINERVA_
ENV MINERVA_TRUSTED_PROXY=127.0.0.1/32
COPY nginx.conf /etc/nginx/templates/default.conf.template
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
