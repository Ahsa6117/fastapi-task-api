#!/usr/bin/env bash
# One-time setup: install Docker Engine inside WSL Ubuntu.
#
# Run it from a WSL terminal (it asks for your sudo password once):
#
#   wsl -d Ubuntu
#   bash /mnt/c/Users/User/Desktop/task-api/scripts/wsl-install-docker.sh
#
# Docker Desktop is the other option on Windows; this route needs no
# reboot and no GUI, and gives the same docker / docker compose commands.
set -e

echo "==> Installing Docker Engine (official convenience script)"
curl -fsSL https://get.docker.com | sudo sh

echo "==> Letting your user run docker without sudo"
sudo usermod -aG docker "$USER"

echo "==> Starting the Docker daemon"
# WSL does not run systemd by default, so start the service directly.
sudo service docker start || sudo dockerd >/tmp/dockerd.log 2>&1 &
sleep 5

echo "==> Versions"
sudo docker --version
sudo docker compose version

echo
echo "Done. Close this WSL terminal and open a new one so the docker group"
echo "takes effect, then check:  docker ps"
