#!/usr/bin/env bash
# Build-time setup for the workshop agent's Modal sandbox image.
#
# This runs once per commit during the image build (see agent_image in
# workshop_modal.py), with the network open and a writable HOME. Its results are
# baked into the image and reused across runs, so install the toolchain here
# rather than at agent runtime -- at runtime the sandbox denies reads under $HOME
# and only lets commands write to the worktree, so installing uv/dlt there fails.
set -euo pipefail

# Install uv to a system path. $HOME/.local/bin (the installer's default) is
# unreadable at runtime, so place the binary where the sandbox can still exec it.
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# Build the project environment (.venv in the repo) with dev dependencies, so the
# agent can run pytest and dlt without resolving/downloading packages at runtime.
uv sync --extra dev
