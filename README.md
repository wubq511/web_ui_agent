<p align="center">
  <h1 align="center">🌐 Web UI Agent</h1>
  <p align="center">
    <em>基于大语言模型的智能 Web 自动化代理系统</em>
  </p>
  <p align="center">
    <a href="#-功能特性">功能特性</a> •
    <a href="#-快速开始">快速开始</a> •
    <a href="#-使用方法">使用方法</a> •
    <a href="#-项目架构">项目架构</a>
  </p>
</p>

---

## 📖 项目简介

**Web UI Agent** 是一个基于大语言模型（LLM）和 Playwright 的智能 Web 自动化代理系统。它能够理解用户的自然语言目标，自动在浏览器中执行操作，完成诸如搜索、登录、填写表单、发送邮件等任务。

项目采用前后端分离架构，提供现代化的 Web 控制中心界面，支持实时监控 Agent 的操作过程。

## ✨ 功能特性

### 🤖 智能决策
- 使用大语言模型分析页面结构，自主决定下一步操作
- 支持 Gemini、Claude、Kimi、豆包等多种 LLM，可动态切换
- 根据任务复杂度自动调整执行策略

### 🔒 反检测机制
- 内置完整的浏览器反检测脚本，模拟真实用户行为
- 支持 CDP 连接到本地 Chrome，保留已有登录状态

### 📡 实时监控
- Web 控制中心提供 30fps 高频截图流
- 实时日志输出，清晰展示执行过程
- 支持暂停/继续，处理验证码等需要人工介入的场景

### 💾 断点续接
- 支持检查点保存和恢复
- 任务中断后可继续执行
- 自动清理过期检查点

### 🔐 凭证管理
- AES 加密存储账号密码
- 自动识别登录表单并填充
- 安全的凭证管理机制

## 🛠 技术栈

### 后端
| 技术 | 用途 |
|------|------|
| [LangGraph](https://github.com/langchain-ai/langgraph) | 状态图框架，定义 Agent 工作流 |
| [LangChain](https://github.com/langchain-ai/langchain) | LLM 应用框架 |
| [Playwright](https://github.com/microsoft/playwright-python) | 浏览器自动化 |
| [FastAPI](https://github.com/tiangolo/fastapi) | Web 服务框架 |
| [WebSockets](https://websockets.readthedocs.io/) | 实时双向通信 |

### 前端
| 技术 | 用途 |
|------|------|
| [React 19](https://react.dev/) | UI 框架 |
| [TypeScript](https://www.typescriptlang.org/) | 类型安全 |
| [Vite 8](https://vitejs.dev/) | 构建工具 |
| [Tailwind CSS 4](https://tailwindcss.com/) | 样式框架 |

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Chrome 浏览器（可选，用于 CDP 模式）

### 安装步骤

1. **克隆仓库**
```bash
git clone https://github.com/wubq511/web_ui_agent.git
cd web_ui_agent
```

2. **安装 Python 依赖**
```bash
pip install -r requirements.txt
playwright install chromium
```

3. **安装前端依赖**
```bash
cd frontend
npm install
```

## 📋 使用方法

### 方式一：命令行模式

直接在命令行中指定任务目标和起始 URL：

```bash
python main.py -o "在百度搜索 Python 教程" -u "https://www.baidu.com"
```

**命令行参数说明：**

| 参数 | 说明 | 示例 |
|------|------|------|
| `-o, --objective` | 任务目标 | `"搜索 Python 教程"` |
| `-u, --url` | 起始 URL | `"https://www.baidu.com"` |
| `-m, --max-steps` | 最大执行步数 | `30` |
| `--model` | 使用的模型 | `gemini-3-flash-preview` |
| `--list-checkpoints` | 列出所有检查点 | - |
| `--resume` | 从检查点恢复 | `cp_xxxxx_xxxxx` |
| `--cleanup` | 清理过期检查点 | - |

### 方式二：Web 控制中心

启动 Web 服务，通过浏览器界面控制 Agent：

```bash
# 终端 1：启动后端服务
python web_server.py

# 终端 2：启动前端服务
cd frontend
npm run dev
```

访问 http://localhost:5173 使用 Web 界面。

### 方式三：连接本地 Chrome

如果需要使用已有的 Chrome 登录状态：

1. 以调试模式启动 Chrome：

Windows:
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

macOS:
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

2. 在 Web 控制中心勾选"连接本地 Chrome"选项

## 🏗 项目架构

```
web_ui_agent/
├── main.py                 # 主程序入口
├── agent.py                # Agent 核心类
├── config.py               # 全局配置
├── state.py                # 状态定义
├── nodes.py                # LangGraph 节点实现
├── web_server.py           # FastAPI Web 服务器
├── model_manager.py        # 多模型管理器
├── step_manager.py         # 动态步骤调整
├── completion_evaluator.py # 任务完成度评估
├── termination_manager.py  # 终止条件管理
├── checkpoint_manager.py   # 检查点管理
├── credential_manager.py   # 凭证加密管理
├── pause_controller.py     # 暂停控制器
├── user_interaction.py     # 用户交互接口
├── performance_monitor.py  # 性能监控
├── security_utils.py       # 安全工具
├── content_extractor.py    # 内容提取器
├── utils.py                # 辅助函数
├── cache_utils.py          # 缓存工具
│
├── frontend/               # 前端 React 应用
│   ├── src/
│   │   ├── components/     # UI 组件
│   │   ├── hooks/          # 自定义 Hooks
│   │   ├── services/       # API 服务
│   │   ├── store/          # 状态管理
│   │   └── types/          # 类型定义
│   ├── package.json
│   └── vite.config.ts
│
├── checkpoints/            # 检查点文件
├── logs/                   # 日志文件
├── process/                # 过程记录
└── credential_data/        # 加密凭证
```

### 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph 状态图                          │
│                                                             │
│   START → perception → reasoning → action → [判断]          │
│              ↑                              │               │
│              └──────────────────────────────┘               │
│                                              ↓               │
│                                            END              │
└─────────────────────────────────────────────────────────────┘

perception  → 感知模块：解析页面 HTML，提取可交互元素
reasoning   → 决策模块：LLM 分析当前状态，决定下一步操作
action      → 执行模块：执行具体操作（点击、输入、滚动等）
```

## 🎮 支持的操作类型

| 操作 | 说明 | 示例 |
|------|------|------|
| `click` | 单击元素 | 点击按钮、链接 |
| `double_click` | 双击元素 | 双击打开文件 |
| `right_click` | 右键点击 | 打开上下文菜单 |
| `hover` | 鼠标悬停 | 触发下拉菜单 |
| `type` | 输入文本 | 填写表单 |
| `press` | 按键 | Enter、Escape |
| `hotkey` | 组合键 | Ctrl+C、Ctrl+V |
| `scroll` | 滚动页面 | 向上/向下滚动 |
| `goto` | 导航到 URL | 跳转到新页面 |
| `wait` | 等待 | 等待页面加载 |
| `done` | 任务完成 | 标记任务结束 |

## ⚙️ 配置说明

### 自定义模型配置

在 Web 控制中心的 API 配置面板中添加自定义模型。支持 OpenAI 兼容接口，可配置多个 Provider 并动态切换。

```bash
python main.py -o "搜索内容" -u "https://example.com" --model "你的模型ID"
```

### API 配置面板

启动 Web 服务后，访问 http://localhost:5173 ，在控制中心面板中：

1. 展开 API 配置区域
2. 点击"新增配置"添加 Provider
3. 填写 API Key、Base URL 等信息
4. 启用需要使用的配置

## 📁 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/command/execute` | POST | 执行 Agent 任务 |
| `/api/agent/pause` | POST | 暂停 Agent |
| `/api/agent/resume` | POST | 继续 Agent |
| `/api/agent/input` | POST | 提交用户输入 |
| `/api/files/all` | GET | 获取日志和过程文件 |

## 🎯 适用场景

- ✅ 自动化测试
- ✅ 数据采集
- ✅ 表单自动填写
- ✅ 邮件自动发送
- ✅ 电商商品搜索
- ✅ 网站功能演示

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

- [LangChain](https://github.com/langchain-ai/langchain) - LLM 应用开发框架
- [Playwright](https://github.com/microsoft/playwright-python) - 浏览器自动化工具
- [FastAPI](https://github.com/tiangolo/fastapi) - 现代 Python Web 框架

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/wubq511">Boqun Wu</a>
</p>
