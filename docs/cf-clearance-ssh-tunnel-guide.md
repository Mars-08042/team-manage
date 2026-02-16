# Cloudflare 过盾（SSH 隧道 + 本地浏览器）操作手册

本文用于在服务器环境下无法自动过盾时，通过本地浏览器获取 `cf_clearance` 并写入系统。

## 1. 适用场景

- 后台点击“执行过盾脚本”持续失败
- 日志提示一直停留在 Cloudflare challenge 阶段
- 需要通过本地浏览器人工完成挑战

## 2. 前置条件

- 你可以用 SSH 正常登录服务器
- 服务器上有可用代理（示例使用 `127.0.0.1:7890`）
- 本地系统：Windows（PowerShell）

## 3. 一次性准备（Windows 私钥权限）

如果私钥报 `UNPROTECTED PRIVATE KEY FILE`，先执行：

```powershell
$k="D:\Desktop\Azure\linux-key.pem"
icacls $k /inheritance:r
icacls $k /remove "Authenticated Users" "Users" "Everyone"
icacls $k /grant:r "${env:USERNAME}:`(R`)"
icacls $k
```

## 4. 建立 SSH 本地隧道

在本机 Windows PowerShell 执行（不要在服务器终端执行）：

```powershell
ssh -i "D:\Desktop\Azure\linux-key.pem" -N -L 17890:127.0.0.1:7890 mars@20.255.118.9
```

说明：
- 看到终端一直不返回是正常的（`-N` 模式会一直保持连接）
- 这个窗口请保持打开

可选验证（新开一个 PowerShell 窗口）：

```powershell
netstat -ano | findstr 17890
curl.exe --proxy http://127.0.0.1:17890 https://api.ipify.org
```

## 5. 本地浏览器走服务器代理

新开一个 PowerShell，启动临时 Chrome：

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --proxy-server="http://127.0.0.1:17890" --user-data-dir="$env:TEMP\cf-proxy-profile"
```

然后在该浏览器中访问：

```text
https://chatgpt.com
```

完成 Cloudflare 挑战，直到页面可正常访问。

## 6. 提取 cf_clearance

在该浏览器按 `F12`：

1. `Application`  
2. `Storage -> Cookies -> https://chatgpt.com`  
3. 找到名称 `cf_clearance`  
4. 复制 `Value`

## 7. 写入系统后台

打开：

```text
https://team.marsio.xyz/admin/settings
```

在 `Cloudflare 过盾` 区域：

1. 粘贴 `cf_clearance`
2. 点击“保存 Cookie”
3. 点击“刷新状态”
4. 确认显示“已设置”

## 8. 验证是否生效

服务器执行：

```bash
sudo docker compose logs -f --tail=200 app
```

确认后续业务请求不再出现 `cloudflare_challenge`。

## 9. 常见问题

### 9.1 `Permission denied (publickey)`

- 检查 SSH 用户名是否正确（`mars` / `azureuser`）
- 检查私钥是否是该服务器对应的 key
- 用调试查看：

```powershell
ssh -vvv -o IdentitiesOnly=yes -i "D:\Desktop\Azure\linux-key.pem" mars@20.255.118.9
```

### 9.2 `Identity file ... not accessible`

- 你在 Linux 终端用了 Windows 路径（`D:\...`）
- 正确做法：在本机 Windows PowerShell 执行隧道命令

### 9.3 隧道命令“卡住不动”

- 正常现象，表示隧道保持中
- 只要不报错并且 `17890` 在监听即可

### 9.4 保存了 cookie 仍无效

- 常见原因：本地浏览器获取 cookie 时没有走同一代理出口
- 确保第 5 步的浏览器是通过 `127.0.0.1:17890` 启动
- `cf_clearance` 过期后需重复以上流程

