#!/usr/bin/env bash
#
# install-prerequisites.sh — provision a fresh Ubuntu 24.04 AWS instance (with an
# NVIDIA Tesla GPU) to run the DFFRNT AI Assistant.
#
# The app ships as a Docker image, so the host needs only: curl, tar, Docker
# Engine + Compose v2, and — for GPU inference — the NVIDIA driver and the NVIDIA
# Container Toolkit. This installs exactly what install.sh checks for, plus the
# GPU stack so `gpu = true` in config.toml (or environment = "local-cuda") works.
#
# Run once on the target, then deploy with ./install.sh (see deploy/README.md).
#
#   curl/scp this file to the box, then:  sudo bash install-prerequisites.sh
#
# Idempotent: safe to re-run. A REBOOT is required after first run so the NVIDIA
# kernel driver loads.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "!! Run as root:  sudo bash install-prerequisites.sh" >&2
  exit 1
fi

# The login user (not root) is the one who should end up in the docker group.
TARGET_USER="${SUDO_USER:-${USER:-ubuntu}}"

export DEBIAN_FRONTEND=noninteractive
ARCH="$(dpkg --print-architecture)"          # amd64 or arm64
. /etc/os-release                            # VERSION_CODENAME (noble), ID (ubuntu)

echo ">> [1/5] Base packages (curl, tar, ...)"
apt-get update -y
apt-get install -y \
  ca-certificates curl gnupg tar lsb-release apt-transport-https

# ---- Docker Engine + Compose v2 (Docker's official apt repo) ----------------
echo ">> [2/5] Docker Engine + Compose v2"
install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
fi
cat > /etc/apt/sources.list.d/docker.list <<EOF
deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable
EOF
apt-get update -y
apt-get install -y \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

# Let the login user run docker without sudo (takes effect on next login).
if [ "$TARGET_USER" != "root" ]; then
  usermod -aG docker "$TARGET_USER"
  echo "   added '$TARGET_USER' to the docker group (re-login to take effect)"
fi

# ---- NVIDIA driver (Tesla / datacenter, headless server variant) ------------
echo ">> [3/5] NVIDIA GPU driver"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  echo "   driver already present:"
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader || true
else
  apt-get install -y ubuntu-drivers-common
  # The -server driver variants are the supported choice for headless datacenter
  # GPUs (Tesla T4/V100/A10G/...). autoinstall picks the recommended version.
  ubuntu-drivers install --gpgpu || ubuntu-drivers autoinstall
  echo "   driver installed — a REBOOT is required before nvidia-smi will work"
fi

# ---- NVIDIA Container Toolkit (lets containers use the GPU) ------------------
echo ">> [4/5] NVIDIA Container Toolkit"
if [ ! -f /etc/apt/keyrings/nvidia-container-toolkit.gpg ]; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /etc/apt/keyrings/nvidia-container-toolkit.gpg
  chmod a+r /etc/apt/keyrings/nvidia-container-toolkit.gpg
fi
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/etc/apt/keyrings/nvidia-container-toolkit.gpg] https://#g' \
  > /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update -y
apt-get install -y nvidia-container-toolkit
# Register the NVIDIA runtime with the Docker daemon and restart it.
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker

# ---- summary ----------------------------------------------------------------
echo ">> [5/5] Verifying"
docker --version
docker compose version
curl --version | head -1
echo
cat <<EOF
>> Prerequisites installed.

   NEXT STEPS:
     1. Reboot so the NVIDIA driver loads:   sudo reboot
     2. After reboot, verify the GPU:        nvidia-smi
        and GPU access from a container:
          docker run --rm --gpus all ubuntu nvidia-smi
     3. Deploy the app (from the bundle dir): ./install.sh
        To run Ollama on the GPU, set 'gpu = true' in config.toml.

   (If you didn't reboot, '$TARGET_USER' must also re-login to use docker
    without sudo.)
EOF
