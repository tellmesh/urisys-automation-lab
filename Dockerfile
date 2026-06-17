FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    URISYS_LAB_HOST=0.0.0.0 \
    URISYS_LAB_PORT=8099 \
    URISYS_LAB_PACKS=stt,chat,message,webrtc \
    URISYS_LAB_FORWARD_SCHEMES=rdp,kvm,him,ocr,llm,browser,shell,http,https,env,log \
    URISYS_RDP_URL=http://urirdp:8795

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/lab

# Build context: tellmesh workspace root
COPY uricore /opt/lab/vendor/uricore
COPY urisysedge /opt/lab/vendor/urisysedge
COPY uristt /opt/lab/vendor/uristt
COPY uriwebrtc /opt/lab/vendor/uriwebrtc
COPY urimessage /opt/lab/vendor/urimessage
COPY urichat /opt/lab/vendor/urichat
COPY urisys-automation-lab /opt/lab/vendor/urisys-automation-lab
COPY urisys-automation-lab/server ./server
COPY urisys-automation-lab/web ./web
COPY urisys-automation-lab/flows ./flows
COPY urisys-automation-lab/docker/entrypoint.sh /usr/local/bin/lab-entrypoint
COPY uri2ops /tmp/uri2ops
COPY uri3 /tmp/uri3
COPY uri2flow /tmp/uri2flow

RUN chmod +x /usr/local/bin/lab-entrypoint \
    && mkdir -p /opt/lab/data \
    && pip install --no-cache-dir \
       -e /opt/lab/vendor/uricore \
       -e /opt/lab/vendor/urisysedge \
       -e /opt/lab/vendor/uristt \
       -e /opt/lab/vendor/uriwebrtc \
       -e /opt/lab/vendor/urimessage \
       -e /opt/lab/vendor/urichat \
       -e /opt/lab/vendor/urisys-automation-lab \
       /tmp/uri2ops /tmp/uri3 /tmp/uri2flow \
    && rm -rf /tmp/uri2ops /tmp/uri3 /tmp/uri2flow

EXPOSE 8099

HEALTHCHECK --interval=10s --timeout=5s --retries=6 \
    CMD curl -fsS "http://127.0.0.1:${URISYS_LAB_PORT}/health" || exit 1

ENTRYPOINT ["/usr/local/bin/lab-entrypoint"]
CMD ["python3", "server/automation_lab_server.py"]
