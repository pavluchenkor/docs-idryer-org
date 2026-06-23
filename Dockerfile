FROM python:3.12-slim

ARG WEBHOOK_VERSION=2.8.3

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl ca-certificates rsync gettext-base pngquant && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        mkdocs \
        mkdocs-material \
        mkdocs-awesome-pages-plugin \
        mkdocs-static-i18n \
        mkdocs-glightbox \
        pillow

RUN curl -fsSL "https://github.com/adnanh/webhook/releases/download/${WEBHOOK_VERSION}/webhook-linux-amd64.tar.gz" \
        -o /tmp/webhook.tar.gz && \
    tar -xzf /tmp/webhook.tar.gz -C /tmp && \
    mv /tmp/webhook-linux-amd64/webhook /usr/local/bin/webhook && \
    rm -rf /tmp/webhook*

WORKDIR /app
# entrypoint.sh запекается в образ — он редко меняется и нужен на старте.
# rebuild.sh и hooks.json.template подмонтированы volume'ом из docker-compose
# (см. README), это позволяет править их без пересборки образа: достаточно
# git pull + docker-compose restart.
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 9000
ENTRYPOINT ["/app/entrypoint.sh"]
