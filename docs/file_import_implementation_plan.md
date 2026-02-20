# Team 文件导入功能实施计划

## 1. 需求概述
目标是在现有的 Team 管理系统中增加“文件导入”功能，允许管理员通过上传包含 Token 信息的 JSON 文件（如 `auth.json`）来批量导入 Team。
该功能应集成在现有的“导入 Team”模态框中，与“单个导入”和“批量导入”并列。

## 2. 技术方案设计

### 2.1 总体架构
*   **前端主导**：利用浏览器端的 `FileReader` API 读取文件内容，减轻后端压力，且无需上传文件本身到服务器，保护隐私。
*   **接口复用**：解析出 Token 信息后，前端循环调用现有的后端 API `/admin/teams/import` `(import_type="single")`，无需新增后端接口。
*   **实时反馈**：在前端展示每个文件的导入进度和结果。

### 2.2 前端界面变更 (`app/templates/base.html`)
在 `importTeamModal` 模态框中进行以下修改：
1.  **新增 Tab 导航**：增加“文件导入”按钮。
2.  **新增面板 (Panel)**：
    *   **文件上传区**：支持点击上传和拖拽上传，设置 `accept=".json"`，支持 `multiple` 多选。
    *   **进度显示区**：包含进度条、当前处理文件名、成功/失败计数。
    *   **结果详情列表**：表格展示每个文件的处理结果（文件名、提取到的邮箱、状态、错误信息）。

### 2.3 前端逻辑实现 (`app/static/js/main.js`)
新增 `handleFileImport` 函数，核心逻辑如下：
1.  **获取文件列表**：从 `<input type="file">` 获取用户选择的文件数组。
2.  **UI 初始化**：重置进度条和结果列表。
3.  **循环处理**：
    *   遍历文件列表，使用 `FileReader.readAsText()` 读取文件内容。
    *   **JSON 解析与校验**：尝试解析 JSON，如果失败则标记该文件失败。
    *   **智能字段提取**：兼容多种 JSON 结构：
        *   扁平结构：直接获取 `access_token`。
        *   嵌套结构：尝试从 `tokens` 或 `credentials` 对象中获取。
    *   **字段映射**：
        *   `access_token` (必填)
        *   `refresh_token`, `session_token`, `client_id`, `email`, `account_id` (可选)
4.  **调用 API**：
    *   使用提取的字段构造请求体。
    *   发送 POST 请求至 `/admin/teams/import`。
5.  **更新状态**：根据 API 返回结果更新成功/失败计数及结果列表。
6.  **完成处理**：所有文件处理完毕后，显示总结果并在短暂延迟后刷新页面。

### 2.4 后端变更
*   **无需变更**：直接使用现有的 `TeamService.import_team_single` 逻辑，该逻辑已包含 Token 验证、刷新和账户信息获取功能。

## 3. 支持的 JSON 数据格式
为了兼容不同工具导出的配置，前端解析逻辑将支持以下结构：

**格式 A (标准扁平结构):**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "rt-...",
  "account_id": "8f...",
  "email": "user@example.com"
}
```

**格式 B (嵌套在 tokens 中):**
```json
{
  "tokens": {
    "access_token": "eyJ...",
    "refresh_token": "rt-..."
  }
}
```

## 4. 异常处理
*   **文件格式错误**：非 JSON 文件或 JSON 语法错误，记为失败并提示“文件格式错误”。
*   **缺少必要字段**：未找到 `access_token`，记为失败。
*   **网络错误/API 报错**：捕获 API 请求异常，将后端返回的错误信息展示在结果列表中。

## 5. 开发计划 (Task List)
- [ ] 修改 `app/templates/base.html`，添加 Tab 和上传 UI。
- [ ] 修改 `app/static/js/main.js`，实现文件读取和解析逻辑。
- [ ] 调试并验证不同格式的 JSON 文件导入。
- [ ] 验证多文件并发/串行处理的稳定性。
