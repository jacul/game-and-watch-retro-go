#!/bin/sh
set -eu
exec "${OPENOCD_BINARY:-openocd}" "$@" -c "adapter speed 100"
