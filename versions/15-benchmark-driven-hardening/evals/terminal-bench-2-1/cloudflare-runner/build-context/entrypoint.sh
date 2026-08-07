#!/bin/sh
set -eu

dockerd-entrypoint.sh dockerd --iptables=false --ip6tables=false \
  >/workspace/dockerd.log 2>&1 &
rm -f /workspace/docker.ready /workspace/docker.failed
attempt=0
until docker version >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 300 ]; then
    touch /workspace/docker.failed
    exit 1
  fi
  sleep 0.2
done
touch /workspace/docker.ready

exec uvicorn runner:app --app-dir /opt --host 0.0.0.0 --port 8080
