# FlareSolverr 远程过盾方案

## 背景

服务器配置较低（1GB 内存 / 2 核 CPU），无法在本机运行浏览器过盾。
当前方案为手动通过隧道在本地过盾后将 cf_clearance 填入数据库，效率低下。

## 方案概述

在本地电脑（或其他高配服务器）部署 FlareSolverr 服务，低配服务器通过 HTTP API 远程调用获取已过盾的 Cookies，定期自动刷新。

## 前提条件

- 本地电脑与服务器使用相同的链式代理节点，确保**出口 IP 一致**
- FlareSolverr 过盾时的 **User-Agent** 与服务器请求时保持一致
- 当前项目 UA：`Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36`

## 架构

```
┌─────────────────────────────────┐
│  本地电脑 / 高配服务器            │
│                                 │
│  FlareSolverr (Docker)          │
│  ├─ 内置 Chromium 浏览器         │
│  ├─ 配置链式代理（与服务器同节点） │
│  └─ 监听 HTTP 8191 端口         │
└──────────────┬──────────────────┘
               │ HTTP API
               ▼
┌─────────────────────────────────┐
│  低配服务器 (1GB / 2核)          │
│                                 │
│  team-manage 主应用              │
│  ├─ 定时任务：调用 FlareSolverr   │
│  │   获取 cf_clearance           │
│  ├─ 写入数据库缓存               │
│  └─ 后续请求携带 cookie 访问 GPT  │
└─────────────────────────────────┘
```

## 实现步骤

### 第一步：本地部署 FlareSolverr

1. 使用 Docker 一键部署 FlareSolverr
2. 配置代理环境变量，确保 FlareSolverr 过盾时走与服务器相同的链式代理出口
3. 确保 FlareSolverr 的端口（默认 8191）对服务器可访问（可通过内网穿透或公网暴露）

### 第二步：服务器新增 FlareSolverr 客户端配置

在项目的系统设置中增加以下配置项：

- `flaresolverr_url`：FlareSolverr 服务地址（如 `http://你的IP:8191/v1.request`）
- `flaresolverr_enabled`：是否启用自动过盾
- `cf_clearance_refresh_interval`：自动刷新间隔（建议 2-4 小时）

### 第三步：实现自动过盾刷新逻辑

在服务器主应用中新增一个服务/模块，负责：

1. **调用 FlareSolverr API**
   - 向 FlareSolverr 发送 POST 请求，指定目标 URL 为 `https://chatgpt.com`
   - 在请求参数中指定与项目一致的 User-Agent
   - FlareSolverr 会启动浏览器完成 Cloudflare Challenge，返回 cookies

2. **解析响应提取 cf_clearance**
   - 从 FlareSolverr 返回的 cookies 数组中找到 `cf_clearance`
   - 校验值是否有效（非空、格式正确）

3. **写入数据库**
   - 复用现有的 `settings_service.set_cf_clearance()` 方法写入
   - 记录获取时间，用于判断是否需要刷新

### 第四步：定时任务自动刷新

1. 在应用启动时注册一个后台定时任务（使用 APScheduler 或 asyncio 定时循环）
2. 每隔固定时间（如 2 小时）自动调用 FlareSolverr 刷新 cf_clearance
3. 刷新失败时记录日志并告警，不覆盖已有的有效 cookie
4. 当 API 请求检测到 Cloudflare Challenge 时，也主动触发一次刷新

### 第五步：保留手动兜底

现有的手动填入 cf_clearance 的功能保持不变，作为自动方案失败时的备用方案。

## 关键注意事项

| 项目 | 说明 |
|------|------|
| IP 一致性 | FlareSolverr 的代理出口 IP 必须与服务器请求的出口 IP 完全一致 |
| UA 一致性 | FlareSolverr 请求时指定的 UA 必须与服务器代码中的 UA 完全一致 |
| 网络可达 | 服务器必须能访问到 FlareSolverr 的 HTTP 端口 |
| 安全性 | FlareSolverr 端口不要暴露到公网，建议通过内网穿透或 SSH 隧道访问 |
| 失败处理 | 自动刷新失败不应覆盖仍有效的旧 cookie |
| 本地电脑在线 | 如果 FlareSolverr 部署在本地电脑，需要电脑保持开机状态 |

## 涉及文件（预估）

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/services/flaresolverr.py` | 新建 | FlareSolverr 客户端，封装 API 调用与 cookie 解析 |
| `app/services/settings.py` | 修改 | 新增 FlareSolverr 相关配置存取方法 |
| `app/tasks/cf_refresh.py` | 新建 | 定时刷新任务 |
| `app/main.py` | 修改 | 注册定时任务到应用生命周期 |
| 前端设置页面 | 修改 | 增加 FlareSolverr 地址配置入口 |
