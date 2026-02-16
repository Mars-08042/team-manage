# `team.marsio.xyz` Docker 部署文档（Cloudflare）

## 1. 部署目标

- 域名：`team.marsio.xyz`
- 服务：本仓库 FastAPI 单体应用（用户端为根路径 `/`）
- 运行方式：Docker Compose
- 反向代理：Nginx
- HTTPS：Let's Encrypt（Certbot）

当前项目关键端点：
- 用户端：`/`
- 管理登录：`/login`
- 管理后台：`/admin`
- 健康检查：`/health`
- 默认端口：`8008`

## 2. 推荐架构

`浏览器 -> Cloudflare -> Nginx(80/443) -> Docker 容器(127.0.0.1:8008)`

## 3. 前置条件

服务器建议 Ubuntu 22.04+/Debian 12+，并满足：
- 已安装 Docker 与 Docker Compose 插件
- 已安装 Nginx
- 已安装 Certbot（或可安装）
- 安全组/防火墙放行 `80`、`443`（`22` 按需）

## 4. Cloudflare 域名解析配置

在 Cloudflare DNS 中新增（或确认已有）：
- `Type`: `A`
- `Name`: `team`
- `Content`: 服务器公网 IP
- `TTL`: `Auto`
- `Proxy status`: `DNS only`（灰云，先这样，方便签发证书）

验证解析：

```bash
nslookup team.marsio.xyz
```

返回 IP 应为你的服务器公网 IP。

## 5. 应用部署步骤

### 5.1 拉取代码并进入目录

```bash
git clone <你的仓库地址> team-manage
cd team-manage
```

### 5.2 配置环境变量

```bash
cp .env.example .env
```

至少修改以下项：

```env
DEBUG=False
APP_PORT=8008
SECRET_KEY=请替换为高强度随机字符串
ADMIN_PASSWORD=请替换为强密码
```

可选：
- `TIMEZONE=Asia/Shanghai`
- `PROXY_ENABLED` 与 `PROXY` 按需配置

### 5.3 启动 Docker 容器

```bash
docker compose up -d --build
docker compose ps
```

健康检查：

```bash
curl http://127.0.0.1:8008/health
```

预期返回：

```json
{"status":"healthy"}
```

### 5.4（建议）限制应用端口仅本机访问

默认 `docker-compose.yml` 端口映射是：

```yaml
ports:
  - "${APP_PORT:-8008}:${APP_PORT:-8008}"
```

建议改为仅本机可访问：

```yaml
ports:
  - "127.0.0.1:${APP_PORT:-8008}:${APP_PORT:-8008}"
```

修改后重启：

```bash
docker compose up -d
```

## 6. Nginx 反向代理配置

新建配置文件 `/etc/nginx/sites-available/team.marsio.xyz`：

```nginx
server {
    listen 80;
    server_name team.marsio.xyz;

    location / {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

启用并重载：

```bash
sudo ln -s /etc/nginx/sites-available/team.marsio.xyz /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 7. 申请 HTTPS 证书

安装 Certbot（若未安装）：

```bash
sudo apt update
sudo apt install -y certbot python3-certbot-nginx
```

签发并自动写入 HTTPS 配置：

```bash
sudo certbot --nginx -d team.marsio.xyz --redirect
```

验证：

```bash
curl -I https://team.marsio.xyz
```

### 7.1 Cloudflare 代理注意事项

如果你把记录改成橙云（Proxied）后签发失败：
- 临时切回 `DNS only`
- 重新执行 Certbot
- 成功后再切回橙云（可选）

如果使用橙云，Cloudflare SSL/TLS 模式建议设为 `Full (strict)`。

## 8. 验证清单

- `docker compose ps` 显示容器 `Up`
- `curl http://127.0.0.1:8008/health` 返回健康状态
- 浏览器访问 `https://team.marsio.xyz/` 可打开用户端
- 浏览器访问 `https://team.marsio.xyz/login` 可打开登录页
- Nginx 配置检测通过：`nginx -t`
- 证书续期检测通过：`sudo certbot renew --dry-run`

## 9. 更新发布流程

```bash
cd <项目目录>
git pull
docker compose down
docker compose up -d --build
docker compose logs -f
```

## 10. 回滚流程

### 10.1 应用版本回滚

```bash
cd <项目目录>
git log --oneline -n 20
git checkout <上一个稳定提交ID>
docker compose up -d --build
```

### 10.2 Nginx 配置回滚

```bash
sudo cp /etc/nginx/sites-available/team.marsio.xyz /etc/nginx/sites-available/team.marsio.xyz.bak-$(date +%F-%H%M)
# 修改后若异常，恢复备份并 reload
```

## 11. 常见问题排查

### 11.1 `502 Bad Gateway`

排查顺序：
- `docker compose ps` 看容器是否启动
- `docker compose logs -f` 看应用报错
- 确认 Nginx `proxy_pass` 与容器端口一致（`8008`）

### 11.2 证书签发失败

常见原因：
- DNS 未生效
- Cloudflare 开启橙云导致 HTTP Challenge 不通
- 80 端口未放行

### 11.3 域名可访问但页面异常

检查：
- `.env` 中关键配置是否正确
- 容器日志是否有数据库或权限错误
- `data/` 挂载目录是否可写

## 12. 生产安全建议

- 首次登录后立即修改管理员密码
- `SECRET_KEY` 必须使用强随机值
- 仅开放 `80/443`，避免公网暴露 `8008`
- 建议定期备份 `data/` 目录（SQLite 数据文件）

> 备注：当前代码中 Session 中间件的 `https_only` 为 `False`。如需进一步提升安全性，可在后续版本中改为生产环境启用 `Secure` Cookie（建议通过环境变量控制）。
