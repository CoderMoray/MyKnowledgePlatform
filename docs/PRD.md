# MyKnowledge 建库方案

> 详细产品设计与架构见 **[DESIGN.md](DESIGN.md)**。

## 产品定位（一句话）

**Local-first、开源、数据归你所有的 AI 知识 + 项目管理平台**：Markdown 为真相源、Git 为版本与协作底座、MCP 为 AI 接入标准，让任意 AI agent 客户端（CodeBuddy/WorkBuddy/Trae 等）「取·存」你的知识并越用越厚；可选经阿里云 OSS 做云同步与分享增强，云存储仍在你自己的账号下。

---

## 方案对比

| 方案 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| **A. 新建分支重构** | 想保留旧代码参考，渐进式迁移 | 历史完整，可随时对比 | 仓库会变大 |
| **B. 当前仓库直接重构** | 旧代码完全不用，彻底重写 | 简洁，无历史包袱 | 丢失旧版本历史 |
| **C. 新建仓库** | 新旧项目完全独立 | 干净，互不干扰 | 需要重新配置 CI/CD |

**建议：方案 A（新建分支）**

---

## 具体操作步骤

### 步骤 1：创建新分支

```bash
git checkout -b v2-mcp
git push -u origin v2-mcp
```

### 步骤 2：清理旧代码（保留参考）

```bash
mkdir -p _archive/v1-skill
mv core modules hooks one-time scripts test _archive/v1-skill/
mv SKILL.md settings.yaml manifest.json _meta.json _archive/v1-skill/
git add .
git commit -m "chore: archive v1 skill code to _archive/v1-skill"
```

### 步骤 3：创建新项目结构

```bash
mkdir -p backend/templates backend/tools
mkdir -p frontend/css frontend/js
mkdir -p docs

touch backend/__init__.py
touch backend/config.py
touch backend/models.py
touch backend/markdown_parser.py
touch backend/storage.py
touch backend/readme_generator.py
touch backend/git_manager.py
touch backend/mcp_server.py
touch backend/main.py
touch backend/cli.py

touch backend/tools/__init__.py
touch backend/tools/navigation.py
touch backend/tools/write.py
touch backend/tools/kb.py
touch backend/tools/share.py
touch backend/tools/maintenance.py

touch frontend/index.html
touch frontend/css/style.css
touch frontend/js/app.js

touch requirements.txt
touch start.sh
touch start.bat
touch README.md
touch .gitignore
```

### 步骤 4-8

详见原始 PRD。
