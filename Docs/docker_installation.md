# Docker Installation Guide

Follow these steps to install Docker on Ubuntu or Debian based systems.

1. **Update your package index**
   ```bash
   sudo apt update
   ```
2. **Install prerequisite packages**
   ```bash
   sudo apt install -y \
       ca-certificates \
       curl \
       gnupg \
       lsb-release
   ```
3. **Add Docker’s official GPG key**
   ```bash
   sudo mkdir -p /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   ```
4. **Set up the Docker repository**
   ```bash
   echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
     $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
   ```
5. **Install Docker Engine**
   ```bash
   sudo apt update
   sudo apt install -y docker-ce docker-ce-cli containerd.io
   ```
6. **Optional: Manage Docker as a non-root user**
   ```bash
   sudo usermod -aG docker $USER
   newgrp docker
   ```
7. **Verify the installation**
   ```bash
   docker run hello-world
   ```

Docker should now be installed and ready to use.
