FROM ubuntu@sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 iproute2 iptables iputils-ping wireguard-tools strongswan-charon strongswan-swanctl libcharon-extra-plugins && rm -rf /var/lib/apt/lists/*
COPY setup.py controller.py supervisor.py health.py guard.py cleanup_ipsec.py eventlog.py selection.py operations.py configuration.py ipsec_config.py doctor.py status.py /app/
COPY strongswan.conf /etc/strongswan.conf
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["python3","/app/health.py"]
STOPSIGNAL SIGTERM
ENTRYPOINT ["python3","-u","/app/supervisor.py"]
