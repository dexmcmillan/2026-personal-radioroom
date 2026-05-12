#!/bin/bash
# Pull latest code and sync dependencies.
# Run from the EC2 instance whenever you push changes to the repo.
set -euo pipefail

cd /opt/policescout
git pull
uv sync
echo "Update complete."
