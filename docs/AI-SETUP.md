# MyKnowledge AI 安装指南

> 目标：让 AI agent 自动化完成 MyKnowledge 的安装、配置和接入。
> 使用方式：用户将本文档内容复制给其 AI agent（CodeBuddy / Trae / WorkBuddy 等），
> AI 依次执行以下步骤即可完成部署。

---

## 步骤 1：检查前提条件

### 1.1 Python 版本

```bash
python3 --version
```

- 需要 **Python ≥ 3.10**
- 如果未安装，提示用户从 https://www.python.org/downloads/ 下载
- macOS 用户也可通过 Homebrew 安装：`brew install python@3.12`

### 1.2 Git

```bash
git --version
```

- 如果未安装，提示用户从 https://git-scm.com/downloads 下载
- macOS 用户：`brew install git`

### 1.3 pip（Python 包管理器）

```bash
python3 -m pip --version
```

- Python 3.10+ 通常自带 pip，如没有则：`python3 -m ensurepip --upgrade`

---

## 步骤 2：安装 MyKnowledge

选择一种方式安装：

### 方式 A：pip 安装（推荐）

```bash
python3 -m pip install myknowledge
```

验证安装：

```bash
myknowledge version --check
```

应输出类似：
```
MyKnowledge v0.5.0
✓ 已是最新版本
```

### 方式 B：从源码安装（开发用）

```bash
git clone https://github.com/CoderMoray/MyKnowledge_PlatForm.git
cd MyKnowledge_PlatForm
python3 -m pip install -e .
```

---

## 步骤 3：健康检查

运行全量自检，AI 自动判断所有配置状态：

```bash
myknowledge doctor
```

输出示例：
```
MyKnowledge v0.5.0 — 健康检查报告
============================================================
  ✓  Python ≥ 3.10         3.12.5
  ✓  Git                   git version 2.45.2
  ✓  Python 依赖           ✓ mcp, ✓ PyYAML, ✓ GitPython
  ✗  身份配置              未设置 — FileNotFoundError
  ✗  知识库目录 (...KB)    不存在
  ✗  Git 仓库              未初始化
============================================================
⚠ 发现以上问题，请参考对应修复步骤。
```

AI 解读报告：有 `✗` 标记的项需要修复。

---

## 步骤 4：初始化知识库

```bash
myknowledge init
```

成功输出：
```
✓ 知识库已创建: /Users/xxx/.myknowledge
```

---

## 步骤 5：设置身份

**此步骤需要用户交互。** AI 应向用户说明并请求提供：

```
我需要设置您的身份信息，这样 MyKnowledge 创建文档时会自动记录作者。
请问您的：
1. 邮箱地址（用于 Git commit 作者信息）
2. 昵称/姓名（在知识库中显示）
```

用户提供后执行：

```bash
myknowledge login "user@example.com" "张三"
```

验证：

```bash
myknowledge whoami
# 应输出: 张三 <user@example.com>
```

---

## 步骤 6：配置 MCP（让 AI client 连接 MyKnowledge）

### 6.1 获取 MCP 配置

```bash
myknowledge mcp-config
```

输出示例：
```json
{
  "mcpServers": {
    "MyKnowledge": {
      "command": "/usr/local/bin/python3",
      "args": ["-m", "backend.cli", "mcp"],
      "env": {}
    }
  }
}
```

### 6.2 写入 AI client 配置

AI 应自动将上述 JSON 写入对应 AI client 的 MCP 配置文件中：

| AI Client | 配置文件位置 |
|-----------|-------------|
| CodeBuddy | `~/.codebuddy/mcp.json` |
| Trae | 设置 → MCP 服务器 → 添加 |
| WorkBuddy | 配置文件路径（依版本而定） |

#### CodeBuddy 自动配置

```bash
# 确保 .codebuddy 目录存在
mkdir -p ~/.codebuddy

# 写入/更新 mcp.json
cat > ~/.codebuddy/mcp.json << 'EOF'
{
  "mcpServers": {
    "MyKnowledge": {
      "command": "myknowledge",
      "args": ["mcp"]
    }
  }
}
EOF
```

> **注意**：如果 `myknowledge` 不在 PATH 中，使用 `python3 -m backend.cli mcp` 代替。

---

## 步骤 7：最终验证

### 7.1 再次健康检查

```bash
myknowledge doctor
```

确认所有项为 `✓`。

### 7.2 测试 MCP 连接

通过调用 MCP 工具验证连接正常：

```bash
# 如果 AI client 已配置，可以直接调 MCP 工具的 nav__read_readme
# 或者在终端中独立测试：
myknowledge mcp-config
echo "配置完成，请重启你的 AI client 以使 MCP 配置生效。"
```

### 7.3 检查版本与更新

```bash
myknowledge version --check
```

如果提示有新版本，执行：

```bash
myknowledge upgrade
```

---

## 附录 A：快速故障排除

| 问题 | 检查点 | 解决 |
|------|--------|------|
| `myknowledge: command not found` | Python pip 安装路径是否在 PATH 中 | `python3 -m backend.cli --help` 临时替代，修复 PATH |
| `✗ 身份未设置` | 未执行 `login` | `myknowledge login <email> <昵称>` |
| MCP 工具调用超时 | Python 版本过低或依赖缺失 | `myknowledge doctor` 检查，`myknowledge upgrade` 更新 |
| `✗ Python 依赖` 中的包缺失 | pip 安装不完整 | `python3 -m pip install myknowledge --upgrade` |
| MCP 连接失败 | mcp.json 路径或 command 配置错误 | 重新执行 `myknowledge mcp-config` 获取正确配置 |

---

## 附录 B：安全说明

- MyKnowledge 是本地优先工具，数据存储在用户本地 `~/.myknowledge/`
- 不内置 LLM，不联网发送数据
- OSS 云同步是可选功能，需用户显式配置
- AI agent 执行本指南仅需要文件写权限（写入 mcp.json）和用户当前终端权限
