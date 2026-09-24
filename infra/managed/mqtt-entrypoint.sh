#!/bin/sh
set -eu
while [ ! -f /managed/passwords ] || [ ! -f /managed/acl ]; do sleep 1; done
mosquitto -c /mosquitto/config/mosquitto.conf &
broker_pid=$!
trap 'kill -TERM "$broker_pid"; wait "$broker_pid"' TERM INT
previous=""
while kill -0 "$broker_pid" 2>/dev/null; do
    current=$(cat /managed/revision 2>/dev/null || true)
    if [ "$current" != "$previous" ]; then
        if [ -n "$previous" ]; then
            kill -TERM "$broker_pid"
            wait "$broker_pid" || true
            mosquitto -c /mosquitto/config/mosquitto.conf &
            broker_pid=$!
        else
            kill -HUP "$broker_pid"
        fi
        previous="$current"
    fi
    sleep 2 &
    wait $! || true
done
wait "$broker_pid"
