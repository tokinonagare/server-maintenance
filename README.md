# 服务器维护与服务恢复指南

本仓库保存了远程服务器 (137.131.37.97) 的核心服务配置，包括 Docker Compose 文件和 Nginx 配置。用于在服务器维护或迁移后快速恢复服务。

## 1. 环境要求

- **操作系统:** Oracle Linux (或兼容的 Linux 发行版)
- **必备软件:**
  - Docker & Docker Compose
  - Nginx
  - Certbot (用于 SSL 证书)

## 2. 目录结构

- `docker/`: 包含所有 Docker 服务的启动配置。
  - `woodpecker/`: Woodpecker CI Server & Agent。
  - `jenkins/`: Jenkins Controller & Agents。
  - `woodpecker-agent/`: 独立的 Woodpecker Agents。
  - `tester-bot/`: Telegram Tester Bot。
- `nginx/`: 系统级 Nginx 配置文件。

## 3. 快速恢复步骤

### 3.1 恢复 Nginx 配置
1. 将 `nginx/nginx.conf` 复制到服务器的 `/etc/nginx/nginx.conf`。
2. 将 `nginx/conf.d/jenkins.conf` 复制到服务器的 `/etc/nginx/conf.d/jenkins.conf`。
3. **SSL 证书:** 确保 `/etc/letsencrypt/live/jenkins.tokinonagare.com/` 目录下有有效的证书文件。如果丢失，需重新运行 `certbot` 申请。
4. 测试并重启 Nginx:
   ```bash
   sudo nginx -t
   sudo systemctl restart nginx
   ```

### 3.2 启动 Docker 服务
对于每个服务目录，进入目录并运行 `docker-compose up -d`。

#### Woodpecker CI
```bash
cd docker/woodpecker
docker-compose up -d
```

#### Jenkins
```bash
cd docker/jenkins
# 注意：如果是首次启动，可能需要先构建本地镜像或处理挂载卷数据
docker-compose up -d
```

#### Tester Bot
1. 进入 `docker/tester-bot`。
2. 将 `.env.example` 复制为 `.env` 并填入真实的 `TELEGRAM_TOKEN`。
3. 启动:
   ```bash
   docker-compose up -d
   ```

## 4. 关键信息备忘

- **Woodpecker Host:** `http://137.131.37.97:8000`
- **Jenkins Domain:** `https://jenkins.tokinonagare.com`
- **数据备份:** 本仓库仅保存配置，不包含数据库和应用数据（如 `woodpecker-data`、Jenkins 的 `jobs` 等）。请确保这些数据在服务器上有独立的持久化卷或备份机制。
