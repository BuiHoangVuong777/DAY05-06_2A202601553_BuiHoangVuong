FROM nginx:1.27-alpine

# Files in /etc/nginx/templates are envsubst'd into /etc/nginx/conf.d at startup
# by the official image's entrypoint — that's how ${BACKEND_URL} is injected.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY index.html /usr/share/nginx/html/index.html

EXPOSE 80
