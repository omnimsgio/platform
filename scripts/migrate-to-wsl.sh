#!/usr/bin/env bash
set -euo pipefail

WIN_PROJECT="/mnt/c/Users/avrca/Documents/Projects/omnimsgio"
LINUX_PROJECT="/home/avrca/projects/omnimsgio"

if ! id avrca &>/dev/null; then
  useradd -m -s /bin/bash avrca
  usermod -aG sudo,docker avrca 2>/dev/null || usermod -aG sudo avrca
  echo 'avrca ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/avrca
  chmod 440 /etc/sudoers.d/avrca
fi

mkdir -p /home/avrca/projects
chown -R avrca:avrca /home/avrca

if [ -d "$LINUX_PROJECT/.git" ]; then
  echo "Project already at $LINUX_PROJECT"
else
  echo "Copying project from Windows to WSL..."
  cp -a "$WIN_PROJECT" "$LINUX_PROJECT"
  chown -R avrca:avrca "$LINUX_PROJECT"
  echo "Copy complete."
fi

sudo -u avrca git config --global user.name "avrcanio"
sudo -u avrca git config --global user.email "avrcanus@gmail.com"
sudo -u avrca git config --global init.defaultBranch main

if [ ! -d "$LINUX_PROJECT/.venv" ]; then
  sudo -u avrca python3 -m venv "$LINUX_PROJECT/.venv"
fi

# Set avrca as default WSL user for this distro
if grep -q '\[user\]' /etc/wsl.conf 2>/dev/null; then
  sed -i 's/^default=.*/default=avrca/' /etc/wsl.conf || true
else
  printf '[user]\ndefault=avrca\n' >> /etc/wsl.conf
fi

echo "--- Migration summary ---"
echo "Project path: $LINUX_PROJECT"
sudo -u avrca git -C "$LINUX_PROJECT" status --short | head -20
sudo -u avrca git -C "$LINUX_PROJECT" remote -v
docker --version || echo "docker: not available"
python3 --version
test -d "$LINUX_PROJECT/.venv" && echo "venv: ok"
echo "Default WSL user: avrca"
