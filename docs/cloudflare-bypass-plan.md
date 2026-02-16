# Cloudflare 过盾功能实现方案

## 问题背景

项目通过 `curl_cffi`（`impersonate="chrome"`）调用 ChatGPT 后端 API（`https://chatgpt.com/backend-api/...`），近期被 Cloudflare 的 **Managed Challenge**（托管质询）拦截。

错误表现：API 请求返回的不是 JSON 数据，而是 Cloudflare 的 HTML 质询页面，其中包含 `_cf_chl_opt` 和 `cType: 'managed'` 等特征。

## 解决方案

采用 **独立脚本过盾 + 主应用 Cookie 注入** 的方案。

### 方案原理

1. Cloudflare 过盾后会设置 `cf_clearance` cookie 作为"通行证"
2. 后续请求只要携带该 cookie，并满足 **相同 IP** + **相似 TLS 指纹**，即可通过
3. `curl_cffi` 的 `impersonate="chrome"` 已处理了 TLS 指纹模拟
4. 因此只需将过盾获得的 cookie 注入到 `curl_cffi` 请求中即可

### 方案架构

```
独立脚本 (solve_cf.py)              主应用 (chatgpt.py)
        │                                  │
        │ 1. 读取数据库中的代理配置         │
        │ 2. 启动 Chromium (低内存参数)     │
        │ 3. 通过代理访问 chatgpt.com       │
        │ 4. 等待 Cloudflare 自动过盾       │
        │ 5. 提取 cf_clearance cookie       │
        │ 6. 写入数据库设置表               │
        │ 7. 退出浏览器                     │
        │                                  │
        │                                  │ A. 请求前从数据库读取 cf_clearance
        │                                  │ B. 注入 cookie 到 curl_cffi 请求
        │                                  │ C. 检测响应是否为 Cloudflare 质询
        │                                  │ D. 若是,返回 error_code: "cloudflare_challenge"
```

## 实现细节

### 1. 独立过盾脚本 `solve_cf.py`

放在项目根目录，使用 Playwright 实现。

**功能：**
- 读取数据库中的代理配置（复用 `app/services/settings.py` 的逻辑）
- 启动 Chromium 无头浏览器（带低内存优化参数：`--disable-gpu`, `--disable-dev-shm-usage`, `--no-sandbox`, `--single-process`）
- 如果配置了代理，浏览器也走同一代理（确保出口 IP 一致）
- 访问 `https://chatgpt.com`
- 等待 Cloudflare 质询自动完成（通常 5-10 秒，可设超时 30 秒）
- 判断过盾成功的标志：页面不再包含 `_cf_chl_opt`，或者获取到了 `cf_clearance` cookie
- 提取 `cf_clearance` cookie 的值
- 写入数据库的系统设置表（key: `cf_clearance`）
- 关闭浏览器，退出脚本

**使用方式：**
```bash
# SSH 到服务器后执行
python solve_cf.py
```

**依赖：**
- 需要安装 `playwright`：`pip install playwright`
- 需要安装 Chromium：`playwright install chromium`
- 服务器是 Linux，可能需要安装系统依赖：`playwright install-deps chromium`

**服务器资源注意事项：**
- 服务器 1GB 内存 / 2 核，Chromium 临时运行需要 200-500MB
- 建议运行脚本前先停掉主应用释放内存，跑完再启动
- 或者给服务器加 swap 空间兜底

### 2. 修改 `app/services/chatgpt.py`

**2a. 添加 Cloudflare 质询检测方法：**

在 `ChatGPTService` 类中添加静态方法 `_is_cloudflare_challenge(response_text)`：
- 检查响应文本中是否包含 `_cf_chl_opt` 或 `cf-challenge` 等 Cloudflare 特征
- 返回布尔值

**2b. 修改 `_make_request` 方法：**

在收到响应后、解析 JSON 前，增加 Cloudflare 检测：
- 如果响应状态码为 403 且内容是 Cloudflare 质询 HTML，返回：
  ```python
  {
      "success": False,
      "status_code": 403,
      "data": None,
      "error": "Cloudflare 质询拦截，需要重新过盾",
      "error_code": "cloudflare_challenge"
  }
  ```
- 这种情况不需要重试（不是临时错误，重试也不会成功）

**2c. 修改 `_create_session` 方法：**

创建 `curl_cffi` 会话后，从数据库读取存储的 `cf_clearance` cookie 并注入：
- 通过 `settings_service` 读取 `cf_clearance` 值
- 如果有值，设置 cookie：`session.cookies.set("cf_clearance", value, domain=".chatgpt.com")`

### 3. 修改 `app/services/settings.py`

添加 Cloudflare cookie 的存取方法（参考现有的代理配置存取模式）：
- `get_cf_clearance(db_session)` → 返回存储的 cf_clearance 值
- `set_cf_clearance(db_session, value)` → 存储 cf_clearance 值

### 4. 前端管理后台（可选）

在系统设置页面增加：
- 显示当前 `cf_clearance` 的状态（是否已设置、设置时间）
- 手动输入 cookie 的输入框（作为脚本方案的备选）
- 当 API 返回 `cloudflare_challenge` 错误时，前端显示明确提示："需要在服务器上运行过盾脚本"

### 5. API 端点（可选）

添加设置/获取 cf_clearance 的 API：
- `GET /api/settings/cf-clearance` — 获取当前状态
- `PUT /api/settings/cf-clearance` — 手动设置值（备用方案）

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `solve_cf.py` | 新建 | 独立过盾脚本 |
| `app/services/chatgpt.py` | 修改 | 添加 CF 检测 + Cookie 注入 |
| `app/services/settings.py` | 修改 | 添加 cf_clearance 存取方法 |
| `requirements.txt` | 修改 | 添加 playwright 依赖 |
| 路由文件 | 修改 | 添加 cf_clearance API 端点（可选）|
| 前端设置页面 | 修改 | 添加状态展示和手动输入（可选）|

## 验证方法

1. 在服务器上运行 `python solve_cf.py`，确认输出成功获取 cookie
2. 检查数据库中 cf_clearance 值是否已写入
3. 重启主应用，调用获取成员列表等 API，确认不再被 Cloudflare 拦截
4. 等待 cookie 过期后，确认前端能显示 "cloudflare_challenge" 错误提示

## 注意事项

- `cf_clearance` cookie 有效期一般为 **几小时到几天**，过期后需重新运行脚本
- 过盾脚本的浏览器必须与主应用使用 **相同的出口 IP**（同一代理配置）
- 如果更换了代理/IP，需要重新过盾
- Chromium 在低内存服务器上运行时，建议先停掉主应用避免 OOM
