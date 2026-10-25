FROM nginx:1.27-alpine
# The official image renders /etc/nginx/templates/*.template with the container's env vars at start-up.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY index.html /usr/share/nginx/html/index.html
# Same-origin API path; nginx proxies it (see nginx.conf.template).
RUN sed -i 's|__GET_UPLOAD_URL_ENDPOINT__|/api|' /usr/share/nginx/html/index.html
