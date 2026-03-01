"""
================================================================================
Agent 模块 - WebUIAgent 类实现
================================================================================

【模块概述】
封装 WebUIAgent 类，提供完整的 Agent 功能：
- 初始化大语言模型
- 管理浏览器生命周期
- 构建和执行 LangGraph 状态图

【设计思路】
将 Agent 封装为一个类，便于：
1. 管理浏览器生命周期
2. 初始化和配置各组件
3. 提供简洁的运行接口
================================================================================
"""

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from playwright.sync_api import sync_playwright, Page, Browser, Playwright, BrowserContext

from config import (
    API_BASE_URL, MODEL_NAME, LLM_TIMEOUT, LLM_TEMPERATURE,
    ACTION_TIMEOUT, PAGE_LOAD_TIMEOUT, MAX_STEPS,
    DEFAULT_TASK_COMPLEXITY, DEFAULT_PROGRESS_LEVEL,
    PROGRESS_STAGNATION_DEFAULT, DEFAULT_INTERVENTION_PAUSED,
    DEFAULT_FAST_MODE, DEFAULT_STEPS_EXTENSION, MIN_REMAINING_STEPS_THRESHOLD,
    PROXY_SERVER, LOCAL_CHROME_PATH, LOCAL_CHROME_USER_DATA_DIR,
    AVAILABLE_MODELS, DEFAULT_MODEL
)
from state import AgentState, create_initial_state
from nodes import (
    perception_node, reasoning_node, action_node, should_continue,
    AgentContext
)
from utils import get_api_key
from model_manager import init_model_manager, get_model_manager


class WebUIAgent:
    """
    WebUIAgent - Web UI 自动化代理类
    
    【使用示例】
    ```python
    agent = WebUIAgent()
    agent.run("在百度搜索 LangGraph 教程")
    ```
    """
    
    def __init__(self, model: str = None):
        """
        初始化 Agent
        
        【工作流程】
        1. 获取并验证 API 密钥
        2. 初始化模型管理器（支持多模型切换）
        3. 构建状态图
        
        【参数】
        model: 指定初始模型，为None则使用默认模型
        """
        print("🚀 正在初始化 Web UI Agent...")
        
        api_key = get_api_key()
        print("✅ API 密钥验证通过")
        
        self.model_manager = init_model_manager(api_key)
        
        if model and model in AVAILABLE_MODELS:
            self.model_manager.set_initial_model(model)
        
        current_model = self.model_manager.get_current_model()
        initial_model = self.model_manager.get_initial_model()
        model_info = AVAILABLE_MODELS.get(current_model, {})
        print(f"✅ 模型管理器已初始化")
        print(f"   初始模型: {initial_model}")
        print(f"   当前模型: {current_model}")
        print(f"   模型名称: {model_info.get('name', '未知')}")
        print(f"   可切换模型: {', '.join(AVAILABLE_MODELS.keys())}")
        
        self.playwright: Playwright = None
        self.browser: Browser = None
        self.browser_context: BrowserContext = None
        self.page: Page = None

        self.context = AgentContext()
        
        self.graph = self._build_graph()
        print("✅ 状态图构建完成")
    
    def _build_graph(self) -> StateGraph:
        """
        构建 LangGraph 状态图
        
        【设计思路】
        LangGraph 使用状态图（StateGraph）来定义 Agent 的工作流程。
        我们需要：
        1. 创建节点（Node）- 每个节点是一个处理函数
        2. 定义边（Edge）- 节点之间的流转关系
        3. 设置入口点 - 图的起始节点
        
        【图的拓扑结构】
        START -> perception -> reasoning -> action -> [条件判断]
                                                        |
                    ┌──────────────────────────────────┘
                    |
                    └──> END (如果完成或超时)
                    └──> perception (如果继续)
        """
        
        def perception_wrapper(state: AgentState) -> dict:
            return perception_node(state, self.page, self.context)
        
        def reasoning_wrapper(state: AgentState) -> dict:
            llm = self.model_manager.get_current_llm()
            return reasoning_node(state, llm, self.context)
        
        def action_wrapper(state: AgentState) -> dict:
            return action_node(state, self.page, self.context)
        
        def should_continue_wrapper(state: AgentState) -> str:
            return should_continue(state, self.context)
        
        graph = StateGraph(AgentState)
        
        graph.add_node("perception", perception_wrapper)
        graph.add_node("reasoning", reasoning_wrapper)
        graph.add_node("action", action_wrapper)
        
        graph.set_entry_point("perception")
        
        graph.add_edge("perception", "reasoning")
        graph.add_edge("reasoning", "action")
        graph.add_conditional_edges(
            "action",
            should_continue_wrapper,
            {
                "perception": "perception",
                "end": END
            }
        )
        
        return graph.compile()
    
    def _init_browser(self, storage_state: dict = None):
        """
        初始化浏览器

        【设计思路】
        使用 Playwright 的同步 API 启动浏览器。我们设置：
        1. headless=False - 显示浏览器窗口，便于观察执行过程
        2. slow_mo - 减慢操作速度，便于观察
        3. storage_state - 恢复浏览器会话状态（cookies、localStorage等）
        4. stealth_sync - 应用 playwright-stealth 反检测补丁
        5. args - 添加浏览器启动参数，进一步隐藏自动化特征
        """
        print("🌐 正在启动浏览器...")

        self.playwright = sync_playwright().start()

        # 生成随机的浏览器指纹参数
        import random
        # 随机窗口大小（在常见分辨率范围内）
        window_width = random.choice([1920, 1680, 1600, 1440, 1366])
        window_height = random.choice([1080, 1050, 900, 768])

        browser_args = [
            '--disable-blink-features=AutomationControlled',
            f'--window-size={window_width},{window_height}',
            '--window-position=0,0',
            '--disable-extensions',
            '--disable-default-apps',
            '--disable-component-extensions-with-background-pages',
            '--disable-background-networking',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--disable-client-side-phishing-detection',
            '--disable-popup-blocking',
            '--disable-sync',
            '--hide-scrollbars',
            '--disable-notifications',
            '--no-first-run',
            '--no-sandbox',
            '--disable-infobars',
            '--disable-password-generation',
            '--disable-password-manager',
            '--disable-autofill-keyboard-accessory-view',
            '--disable-save-password-bubble',
            '--disable-webgl',
            '--disable-3d-apis',
            '--disable-experimental-extension-apis',
            '--disable-webrtc-hw-encoding',
            # 禁用 WebRTC 完全
            '--disable-webrtc',
            # 禁用 WebGL2
            '--disable-webgl2',
            # 设置用户代理（关键）
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            # 设置语言
            '--lang=zh-CN',
            # 禁用站点隔离（可能有助于某些检测）
            '--disable-site-isolation-trials',
            # 注意：Playwright 的 launch() 不支持 --user-data-dir 参数
            # 如需持久化用户数据，应使用 launch_persistent_context() 方法
        ]
        
        # 添加代理（如果配置了）
        if PROXY_SERVER:
            browser_args.append(f'--proxy-server={PROXY_SERVER}')
            print(f"🌐 使用代理: {PROXY_SERVER}")
        
        # 注意：Playwright 的 browser_context 默认就是隔离的（类似隐身模式）
        # 如果需要持久化用户数据，应使用 launch_persistent_context 方法
        # 这里不需要额外的 --user-data-dir 或 --incognito 参数

        # 尝试连接本地 Chrome（如果可用）
        # 本地 Chrome 更难被检测，因为它有真实的用户数据
        try:
            # 先尝试连接已运行的 Chrome 远程调试端口
            self.browser = self.playwright.chromium.connect_over_cdp("http://localhost:9222")
            print("✅ 已连接到本地 Chrome（远程调试模式）")
            use_local_chrome = True
        except Exception:
            use_local_chrome = False
            # 如果没有本地 Chrome，使用 Playwright 的 Chromium
            self.browser = self.playwright.chromium.launch(
                headless=False,
                slow_mo=100,
                args=browser_args
            )
            print("⚠️ 使用 Playwright Chromium（建议启动本地 Chrome 以获得更好的反检测效果）")
            print("   启动本地 Chrome 命令：")
            print(r'   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\chrome_dev_profile"')

        # 创建浏览器上下文，设置更真实的用户代理和视口
        # 使用真实的 Chrome User-Agent
        user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': user_agent,
            'locale': 'zh-CN',
            'timezone_id': 'Asia/Shanghai',
            'geolocation': {'latitude': 31.2304, 'longitude': 121.4737},  # 上海坐标
            'permissions': ['geolocation'],
            'color_scheme': 'light',
            # 添加额外的 HTTP 头来模拟真实浏览器
            'extra_http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'max-age=0',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
            }
        }

        if storage_state:
            print("🔄 正在恢复浏览器会话状态...")
            context_options['storage_state'] = storage_state

        self.browser_context = self.browser.new_context(**context_options)

        # 添加反检测脚本 - 隐藏自动化特征
        # 这些脚本会在每个页面加载时自动执行
        self.browser_context.add_init_script("""
            // ==================== 基础反检测 ====================
            // 覆盖 navigator.webdriver 属性
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // 删除 webdriver 相关的属性
            delete navigator.__proto__.webdriver;

            // 覆盖 chrome 对象
            window.chrome = {
                runtime: {
                    OnInstalledReason: {CHROME_UPDATE: "chrome_update", INSTALL: "install", SHARED_MODULE_UPDATE: "shared_module_update", UPDATE: "update"},
                    OnRestartRequiredReason: {APP_UPDATE: "app_update", OS_UPDATE: "os_update", PERIODIC: "periodic"},
                    PlatformArch: {ARM: "arm", ARM64: "arm64", MIPS: "mips", MIPS64: "mips64", MIPS64EL: "mips64el", MIPSEL: "mipsel", X86_32: "x86-32", X86_64: "x86-64"},
                    PlatformNaclArch: {ARM: "arm", MIPS: "mips", MIPS64: "mips64", MIPS64EL: "mips64el", MIPSEL: "mipsel", MIPSEL64: "mipsel64", X86_32: "x86-32", X86_64: "x86-64"},
                    PlatformOs: {ANDROID: "android", CROS: "cros", LINUX: "linux", MAC: "mac", OPENBSD: "openbsd", WIN: "win"},
                    RequestUpdateCheckStatus: {NO_UPDATE: "no_update", THROTTLED: "throttled", UPDATE_AVAILABLE: "update_available"}
                },
                loadTimes: function() {
                    return {
                        commitLoadTime: performance.now() / 1000,
                        connectionInfo: "h2",
                        finishDocumentLoadTime: performance.now() / 1000,
                        finishLoadTime: performance.now() / 1000,
                        firstPaintAfterLoadTime: 0,
                        firstPaintTime: performance.now() / 1000,
                        navigationType: "Other",
                        npnNegotiatedProtocol: "h2",
                        requestTime: performance.now() / 1000,
                        startLoadTime: performance.now() / 1000,
                        wasAlternateProtocolAvailable: false,
                        wasFetchedViaSpdy: true,
                        wasNpnNegotiated: true
                    };
                },
                csi: function() {
                    return {
                        onloadT: Date.now(),
                        pageT: performance.now(),
                        startE: performance.timing.navigationStart,
                        tran: 15
                    };
                },
                app: {
                    isInstalled: false,
                    InstallState: {DISABLED: "disabled", INSTALLED: "installed", NOT_INSTALLED: "not_installed"},
                    RunningState: {CANNOT_RUN: "cannot_run", READY_TO_RUN: "ready_to_run", RUNNING: "running"}
                }
            };

            // ==================== 插件模拟 ====================
            // 覆盖 navigator.plugins，使其看起来像有真实插件
            const createFakePlugins = () => {
                const plugins = [
                    {
                        0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format", enabledPlugin: null},
                        description: "Portable Document Format",
                        filename: "internal-pdf-viewer",
                        length: 1,
                        name: "Chrome PDF Plugin",
                        item: function() { return this[0]; },
                        namedItem: function() { return null; }
                    },
                    {
                        0: {type: "application/pdf", suffixes: "pdf", description: "", enabledPlugin: null},
                        description: "",
                        filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                        length: 1,
                        name: "Chrome PDF Viewer",
                        item: function() { return this[0]; },
                        namedItem: function() { return null; }
                    },
                    {
                        0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format", enabledPlugin: null},
                        description: "Portable Document Format",
                        filename: "internal-pdf-viewer2",
                        length: 1,
                        name: "Native Client",
                        item: function() { return this[0]; },
                        namedItem: function() { return null; }
                    }
                ];
                plugins.length = 3;
                plugins.item = function(index) { return this[index] || null; };
                plugins.namedItem = function(name) {
                    for (let i = 0; i < this.length; i++) {
                        if (this[i].name === name) return this[i];
                    }
                    return null;
                };
                plugins.refresh = function() {};
                return plugins;
            };

            Object.defineProperty(navigator, 'plugins', {
                get: createFakePlugins
            });

            // 覆盖 navigator.mimeTypes
            Object.defineProperty(navigator, 'mimeTypes', {
                get: () => {
                    const mimeTypes = [
                        {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format", enabledPlugin: navigator.plugins[1]},
                        {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format", enabledPlugin: navigator.plugins[0]},
                        {type: "application/x-nacl", suffixes: "", description: "Native Client module", enabledPlugin: navigator.plugins[2]},
                        {type: "application/x-pnacl", suffixes: "", description: "Portable Native Client module", enabledPlugin: navigator.plugins[2]}
                    ];
                    mimeTypes.length = 4;
                    mimeTypes.item = function(index) { return this[index] || null; };
                    mimeTypes.namedItem = function(name) {
                        for (let i = 0; i < this.length; i++) {
                            if (this[i].type === name) return this[i];
                        }
                        return null;
                    };
                    return mimeTypes;
                }
            });

            // ==================== 语言和地区 ====================
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en-US', 'en']
            });

            Object.defineProperty(navigator, 'language', {
                get: () => 'zh-CN'
            });

            // ==================== 硬件信息 ====================
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });

            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });

            Object.defineProperty(navigator, 'maxTouchPoints', {
                get: () => 0
            });

            // ==================== 平台和用户代理 ====================
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32'
            });

            Object.defineProperty(navigator, 'vendor', {
                get: () => 'Google Inc.'
            });

            Object.defineProperty(navigator, 'product', {
                get: () => 'Gecko'
            });

            Object.defineProperty(navigator, 'productSub', {
                get: () => '20030107'
            });

            // ==================== 权限和通知 ====================
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => {
                if (parameters.name === 'notifications') {
                    return Promise.resolve({ state: 'default', onchange: null });
                }
                if (parameters.name === 'clipboard-read' || parameters.name === 'clipboard-write') {
                    return Promise.resolve({ state: 'prompt', onchange: null });
                }
                return originalQuery(parameters);
            };

            Object.defineProperty(Notification, 'permission', {
                get: () => 'default'
            });

            // ==================== WebGL 反检测 ====================
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                const params = {
                    37445: 'Intel Inc.',
                    37446: 'Intel Iris OpenGL Engine',
                    7937: 'Intel Iris OpenGL Engine',
                    7936: 'Intel Inc.',
                    33901: new Float32Array([1, 1024]),
                    33902: new Float32Array([1, 1024]),
                    34047: new Float32Array([0.00392156862745098, 0.00392156862745098, 0.00392156862745098, 0.00392156862745098]),
                    36349: 32,
                    36348: 32,
                    35661: 16,
                    36347: 4096,
                    34076: 16384,
                    34930: 8,
                    3379: 16384,
                    34024: 16384,
                    3386: new Int32Array([32767, 32767]),
                    3410: 2,
                    3411: 8,
                    3412: 8,
                    3413: 8,
                    3414: 24,
                    3415: 0,
                    3416: 16
                };
                if (parameter in params) {
                    return params[parameter];
                }
                return getParameter.call(this, parameter);
            };

            // 覆盖 getShaderPrecisionFormat
            const getShaderPrecisionFormat = WebGLRenderingContext.prototype.getShaderPrecisionFormat;
            WebGLRenderingContext.prototype.getShaderPrecisionFormat = function(shaderType, precisionType) {
                return {
                    precision: 23,
                    rangeMin: 127,
                    rangeMax: 127
                };
            };

            // ==================== Canvas 反检测 ====================
            // 添加轻微的噪声到 Canvas 指纹
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;

            // ==================== 屏幕和窗口 ====================
            Object.defineProperty(screen, 'colorDepth', {
                get: () => 24
            });

            Object.defineProperty(screen, 'pixelDepth', {
                get: () => 24
            });

            // ==================== 时区 ====================
            const originalDate = Date;
            const originalIntl = Intl;

            // ==================== 插件检测防护 ====================
            // 防止检测 plugins 的真实性
            Object.setPrototypeOf(navigator.plugins, PluginArray.prototype);
            Object.setPrototypeOf(navigator.mimeTypes, MimeTypeArray.prototype);

            // ==================== 其他防护 ====================
            // 防止检测 Function.prototype.toString
            const originalToString = Function.prototype.toString;
            Function.prototype.toString = function() {
                if (this === Function.prototype.toString) {
                    return 'function toString() { [native code] }';
                }
                return originalToString.call(this);
            };

            // 防止检测 console
            const originalConsole = window.console;
            Object.defineProperty(window, 'console', {
                get: () => originalConsole,
                set: () => {}
            });

            // 模拟正常的 performance 时间
            Object.defineProperty(performance.timing, 'navigationStart', {
                get: () => Date.now() - performance.now()
            });

            // ==================== 阻止检测脚本 ====================
            // 拦截常见的检测脚本
            const originalFetch = window.fetch;
            window.fetch = function(...args) {
                return originalFetch.apply(this, args);
            };

            const originalXHR = window.XMLHttpRequest;
            window.XMLHttpRequest = function() {
                return new originalXHR();
            };

            console.log('🛡️ 反检测脚本已加载');
        """)

        self.page = self.browser_context.new_page()

        # 添加页面级别的反检测脚本
        self.page.add_init_script("""
            // 覆盖 Canvas 指纹
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                if (type === 'image/png' && this.width > 16 && this.height > 16) {
                    // 添加轻微噪声
                    const ctx = this.getContext('2d');
                    if (ctx) {
                        const imageData = ctx.getImageData(0, 0, this.width, this.height);
                        const data = imageData.data;
                        // 修改少量像素
                        for (let i = 0; i < 10; i++) {
                            const idx = Math.floor(Math.random() * data.length / 4) * 4;
                            data[idx] = (data[idx] + 1) % 256;
                        }
                        ctx.putImageData(imageData, 0, 0);
                    }
                }
                return originalToDataURL.apply(this, arguments);
            };

            // 覆盖 getImageData
            const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
            CanvasRenderingContext2D.prototype.getImageData = function(x, y, w, h) {
                const imageData = originalGetImageData.apply(this, arguments);
                // 添加轻微噪声
                if (w > 16 && h > 16) {
                    const data = imageData.data;
                    for (let i = 0; i < 10; i++) {
                        const idx = Math.floor(Math.random() * data.length / 4) * 4;
                        data[idx] = (data[idx] + 1) % 256;
                    }
                }
                return imageData;
            };

            // 模拟真实的鼠标移动
            let lastMouseX = 0;
            let lastMouseY = 0;
            document.addEventListener('mousemove', function(e) {
                lastMouseX = e.clientX;
                lastMouseY = e.clientY;
            }, true);

            // 覆盖 requestAnimationFrame 以模拟正常的刷新率
            const originalRAF = window.requestAnimationFrame;
            window.requestAnimationFrame = function(callback) {
                return originalRAF.call(window, callback);
            };

            // 模拟真实的输入延迟
            const originalSetTimeout = window.setTimeout;
            window.setTimeout = function(callback, delay) {
                // 添加随机延迟（0-10ms）
                const randomDelay = delay + Math.random() * 10;
                return originalSetTimeout.call(window, callback, randomDelay);
            };
        """)

        if storage_state:
            print("✅ 浏览器会话状态已恢复")

        self.page.set_default_timeout(ACTION_TIMEOUT)

        self.context.set_page(self.page)

        print("✅ 浏览器启动成功（已启用反检测模式）")

        self._prompt_credential_login()
    
    def _prompt_credential_login(self):
        """
        在浏览器启动后提示用户登录凭证管理器
        
        【设计思路】
        浏览器启动后立即提示用户登录凭证管理器，
        这样在执行任务时可以直接使用已保存的账号密码。
        密码错误时提供重新输入的机会（最多3次）。
        """
        try:
            from credential_manager import CredentialManager
            HAS_CREDENTIAL_MANAGER = True
        except ImportError:
            HAS_CREDENTIAL_MANAGER = False
            return
        
        if not HAS_CREDENTIAL_MANAGER:
            return
        
        print("\n" + "─"*60)
        print("🔐 凭证管理器")
        print("─"*60)
        
        self.context.init_credential_manager()
        cred_status = self.context.get_credential_status()
        
        if cred_status.get("is_setup_complete"):
            print("📌 检测到已保存的凭证库")
            print("   登录后可自动填充账号密码（按 Enter 跳过）")
            
            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                try:
                    import msvcrt
                    if attempt > 1:
                        print(f"\n🔄 请重新输入主密码 (第 {attempt}/{max_attempts} 次): ", end='', flush=True)
                    else:
                        print("主密码: ", end='', flush=True)
                    password_chars = []
                    while True:
                        ch = msvcrt.getch()
                        if ch == b'\r' or ch == b'\n':
                            print()
                            break
                        elif ch == b'\x08' or ch == b'\x7f':
                            if password_chars:
                                password_chars.pop()
                                print('\b \b', end='', flush=True)
                        elif ch == b'\x03':
                            print("\n⏭️ 已跳过登录")
                            return
                        else:
                            try:
                                char = ch.decode('utf-8')
                                password_chars.append(char)
                                print('*', end='', flush=True)
                            except:
                                pass
                    master_password = ''.join(password_chars)
                except Exception:
                    master_password = input(f"主密码 (第 {attempt}/{max_attempts} 次): ")
                
                if not master_password:
                    print("⏭️ 已跳过，稍后可使用 'cred_login' 命令登录")
                    return
                
                if self.context.login_credential_manager(master_password):
                    print("✅ 凭证管理器登录成功")
                    return
                else:
                    if attempt < max_attempts:
                        print("❌ 主密码错误，请重试")
                    else:
                        print("❌ 登录失败次数过多，稍后可使用 'cred_login' 命令登录")
        else:
            print("📌 凭证管理器未初始化")
            print("   使用 'cred_login' 命令初始化并添加账号")
        
        print("─"*60 + "\n")
    
    def _close_browser(self):
        """
        手动关闭浏览器

        【设计思路】
        在用户确认查看完信息后，手动调用此方法关闭浏览器和 Playwright 实例，
        释放资源并避免内存泄漏。
        """
        # 关闭页面
        if self.page:
            try:
                self.page.close()
            except Exception:
                pass
            self.page = None

        # 关闭浏览器上下文
        if self.browser_context:
            try:
                self.browser_context.close()
            except Exception:
                pass
            self.browser_context = None

        # 关闭浏览器
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
            self.browser = None

        # 停止 playwright
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright = None

        print("✅ 浏览器已关闭")
    
    def _display_result_in_browser(self, state: AgentState):
        """
        在浏览器中展示任务结果摘要
        
        【设计思路】
        任务完成后，在浏览器中打开一个新页面展示执行结果，
        方便用户查看任务详情和操作记录。
        """
        if not self.browser:
            return
        
        result_page = self.browser.new_page()
        
        step_count = state['step_count']
        is_done = state['is_done']
        error_message = state.get('error_message', '')
        history = state.get('history', [])
        objective = state.get('objective', '未知任务')
        termination_reason = state.get('termination_reason', '')
        progress_ratio = state.get('progress_ratio', 0)
        max_steps = state.get('max_steps', MAX_STEPS)
        
        status_icon = "✅" if is_done else "⚠️"
        status_text = "已完成" if is_done else "未完成"
        status_color = "#28a745" if is_done else "#ffc107"
        
        history_rows = ""
        for entry in history:
            step = entry.get('step', '?')
            action = entry.get('action_type', '?')
            result = entry.get('result', '?')
            thought = entry.get('thought', '')
            history_rows += f"""
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{step}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;"><code>{action}</code></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{result[:100]}{'...' if len(result) > 100 else ''}</td>
                </tr>
            """
        
        termination_info = ""
        if termination_reason:
            termination_info = f"""
                <div class='warning'>
                    <strong>🛑 终止原因：</strong>{termination_reason}
                </div>
            """
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>任务执行结果 - Web UI Agent</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    max-width: 900px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    background-color: white;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    padding: 30px;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                    padding-bottom: 20px;
                    border-bottom: 2px solid #e0e0e0;
                }}
                .status-badge {{
                    display: inline-block;
                    padding: 8px 20px;
                    border-radius: 20px;
                    font-size: 18px;
                    font-weight: bold;
                    background-color: {status_color};
                    color: white;
                }}
                .info-card {{
                    background-color: #f8f9fa;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 15px 0;
                }}
                .info-item {{
                    display: flex;
                    margin: 10px 0;
                }}
                .info-label {{
                    font-weight: bold;
                    min-width: 100px;
                    color: #555;
                }}
                .info-value {{
                    color: #333;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 15px;
                }}
                th {{
                    background-color: #007bff;
                    color: white;
                    padding: 12px 8px;
                    border: 1px solid #ddd;
                    text-align: left;
                }}
                tr:nth-child(even) {{
                    background-color: #f8f9fa;
                }}
                tr:hover {{
                    background-color: #e9ecef;
                }}
                .warning {{
                    background-color: #fff3cd;
                    border-left: 4px solid #ffc107;
                    padding: 15px;
                    margin: 15px 0;
                    border-radius: 4px;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #e0e0e0;
                    color: #666;
                }}
                .close-hint {{
                    background-color: #d1ecf1;
                    border-left: 4px solid #17a2b8;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
                .progress-bar {{
                    background-color: #e9ecef;
                    border-radius: 10px;
                    height: 20px;
                    overflow: hidden;
                }}
                .progress-fill {{
                    background-color: #28a745;
                    height: 100%;
                    width: {progress_ratio * 100}%;
                    transition: width 0.3s ease;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎯 Web UI Agent 任务执行结果</h1>
                    <div class="status-badge">{status_icon} {status_text}</div>
                </div>
                
                <div class="info-card">
                    <h3>📋 任务信息</h3>
                    <div class="info-item">
                        <span class="info-label">目标：</span>
                        <span class="info-value">{objective}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">总步数：</span>
                        <span class="info-value">{step_count} / {max_steps}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">完成进度：</span>
                        <span class="info-value">{progress_ratio:.1%}</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill"></div>
                    </div>
                </div>
                
                {termination_info}
                
                {"<div class='warning'><strong>⚠️ 错误信息：</strong>" + error_message + "</div>" if error_message else ""}
                
                <div class="close-hint">
                    <strong>💡 提示：</strong>任务已完成，您可以查看上方信息。如需关闭浏览器，请返回终端按 <kbd>Enter</kbd> 键或关闭此窗口。
                </div>
                
                <h3>📜 执行历史</h3>
                <table>
                    <thead>
                        <tr>
                            <th style="width: 80px;">步骤</th>
                            <th style="width: 150px;">操作类型</th>
                            <th>执行结果</th>
                        </tr>
                    </thead>
                    <tbody>
                        {history_rows}
                    </tbody>
                </table>
                
                <div class="footer">
                    <p>Web UI Agent 自动化任务执行完成</p>
                    <p>浏览器将保持打开状态，您可以随时查看页面内容</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        result_page.set_content(html_content)
        print("📊 任务结果已在浏览器中展示")
    
    def _wait_for_user_close(self):
        """
        等待用户手动确认关闭浏览器
        
        【设计思路】
        任务完成后，保持浏览器打开，等待用户在终端按 Enter 键后关闭。
        这样用户有足够时间查看浏览器中的信息内容。
        """
        print("\n" + "═"*60)
        print("💡 任务已完成，浏览器保持打开状态")
        print("   您可以在浏览器中查看任务执行结果")
        print("   按 Enter 键关闭浏览器并退出程序...")
        print("═"*60)
        
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        
        self._close_browser()
    
    def run(self, objective: str, start_url: str = None, 
            keep_browser_open: bool = True,
            max_steps: int = None,
            resume_from_checkpoint: str = None) -> AgentState:
        """
        运行 Agent 执行任务
        
        【参数】
        objective: str - 用户目标描述
        start_url: str - 起始页面 URL（可选）
        keep_browser_open: bool - 任务完成后是否保持浏览器打开（默认 True）
        max_steps: int - 最大步骤限制（可选，默认使用配置值）
        resume_from_checkpoint: str - 从检查点恢复的ID（可选）
        
        【工作流程】
        1. 初始化浏览器
        2. 如果有起始 URL，导航到该页面
        3. 初始化状态
        4. 执行状态图
        5. 输出结果
        6. 在浏览器中展示结果（如果 keep_browser_open 为 True）
        7. 等待用户确认后关闭浏览器（如果 keep_browser_open 为 True）
        
        【返回值】
        AgentState: 最终状态
        """
        checkpoint_data = None
        storage_state = None
        actual_objective = objective
        
        if resume_from_checkpoint:
            checkpoint_data = self.context.checkpoint_manager.load_checkpoint(
                resume_from_checkpoint
            )
            if checkpoint_data:
                storage_state = checkpoint_data.storage_state
                actual_objective = checkpoint_data.state.get("objective", objective)
                if storage_state:
                    print("📦 发现保存的浏览器会话状态")
        
        print("\n" + "═"*60)
        print("🎯 开始执行任务")
        print("═"*60)
        print(f"📋 目标: {actual_objective}")
        if start_url:
            print(f"🌐 起始页面: {start_url}")
        print("═"*60 + "\n")
        
        self._init_browser(storage_state=storage_state)
        
        try:
            if checkpoint_data:
                initial_state = checkpoint_data.state
                
                initial_state.setdefault("task_complexity", DEFAULT_TASK_COMPLEXITY.value)
                initial_state.setdefault("progress_level", DEFAULT_PROGRESS_LEVEL)
                initial_state.setdefault("adjusted_stagnation_threshold", PROGRESS_STAGNATION_DEFAULT)
                initial_state.setdefault("intervention_paused", DEFAULT_INTERVENTION_PAUSED)
                initial_state.setdefault("fast_mode", DEFAULT_FAST_MODE)
                
                self.context.step_manager = self.context.step_manager.from_dict(
                    checkpoint_data.step_manager
                )
                self.context.completion_evaluator = self.context.completion_evaluator.from_dict(
                    checkpoint_data.completion_evaluator
                )
                self.context.termination_manager = self.context.termination_manager.from_dict(
                    checkpoint_data.termination_manager
                )
                
                if max_steps and max_steps > self.context.step_manager.current_max_steps:
                    self.context.step_manager.current_max_steps = max_steps
                    print(f"📊 使用命令行指定的最大步骤: {max_steps}")
                else:
                    saved_step_count = initial_state.get("step_count", 0)
                    remaining_steps = self.context.step_manager.current_max_steps - saved_step_count
                    if remaining_steps < MIN_REMAINING_STEPS_THRESHOLD:
                        new_max = saved_step_count + DEFAULT_STEPS_EXTENSION
                        self.context.step_manager.adjust_max_steps(
                            reason="恢复检查点时自动扩展（剩余步骤不足）",
                            target_steps=new_max,
                            current_step=saved_step_count
                        )
                
                initial_state["max_steps"] = self.context.step_manager.current_max_steps
                
                saved_url = initial_state.get("current_url", "")
                if saved_url and saved_url != "about:blank" and not saved_url.startswith("data:"):
                    print(f"🌐 导航到检查点页面: {saved_url}")
                    try:
                        self.page.goto(saved_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
                        try:
                            self.page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
                        except Exception:
                            print("⚠️ 网络未完全空闲，继续执行...")
                            self.page.wait_for_load_state("load", timeout=5000)
                        initial_state["current_url"] = self.page.url
                    except Exception as e:
                        print(f"⚠️ 导航到检查点页面失败: {e}")
                
                print(f"✅ 已从检查点恢复: {resume_from_checkpoint}")
                print(f"📊 恢复后最大步骤: {self.context.step_manager.current_max_steps}")
                print(f"📝 已执行步骤: {initial_state.get('step_count', 0)}")
            elif resume_from_checkpoint:
                print("⚠️ 检查点加载失败，使用初始状态")
                if max_steps:
                    self.context.step_manager.current_max_steps = max_steps
                initial_state = create_initial_state(
                    objective=objective,
                    current_url="",
                    max_steps=self.context.step_manager.current_max_steps
                )
            else:
                if max_steps:
                    self.context.step_manager.current_max_steps = max_steps
                    
                if start_url:
                    print(f"🌐 导航到起始页面: {start_url}")
                    self.page.goto(start_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
                    try:
                        self.page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
                    except Exception:
                        print("⚠️ 网络未完全空闲，继续执行...")
                        self.page.wait_for_load_state("load", timeout=5000)
                
                initial_state = create_initial_state(
                    objective=objective,
                    current_url=self.page.url,
                    max_steps=self.context.step_manager.current_max_steps
                )
            
            self.context.initialize(objective, start_url or "")
            
            final_state = self.graph.invoke(initial_state)
            
            try:
                self._print_summary(final_state)
            except Exception as e:
                print(f"⚠️ 打印摘要时出错: {e}")
            
            try:
                self.context.logger.log_session_end(
                    success=final_state.get('is_done', False),
                    step_count=final_state.get('step_count', 0),
                    duration=self.context.termination_manager.get_elapsed_time(),
                    reason=final_state.get('termination_reason', '')
                )
            except Exception as e:
                print(f"⚠️ 记录会话结束日志时出错: {e}")
            
            try:
                if keep_browser_open:
                    self._display_result_in_browser(final_state)
                    self._wait_for_user_close()
                else:
                    self._close_browser()
            except Exception as e:
                print(f"⚠️ 浏览器操作时出错: {e}")
                self._close_browser()
            
            try:
                self.context.cleanup()
            except Exception as e:
                print(f"⚠️ 清理资源时出错: {e}")
            
            return final_state
            
        except Exception as e:
            print(f"\n❌ 执行过程中发生错误: {e}")
            self.context.logger.log_error(str(e), 0)
            if keep_browser_open:
                print("\n💡 浏览器保持打开，您可以查看错误现场")
                print("   按 Enter 键关闭浏览器...")
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    pass
            self._close_browser()
            self.context.cleanup()
            raise
    
    def _print_summary(self, state: AgentState):
        """
        打印执行结果汇总
        
        【参数】
        state: AgentState - 最终状态
        """
        try:
            print("\n" + "═"*60)
            print("📊 执行结果汇总")
            print("═"*60)
            print(f"✅ 总步数: {state['step_count']}")
            print(f"📊 最大步骤: {state.get('max_steps', MAX_STEPS)}")
            print(f"📈 完成进度: {state.get('progress_ratio', 0):.1%}")
            print(f"🎯 任务状态: {'已完成' if state['is_done'] else '未完成'}")
            
            if state.get("termination_reason"):
                print(f"🛑 终止原因: {state['termination_reason']}")
            
            if state.get("error_message"):
                print(f"⚠️ 最后错误: {state['error_message']}")
            
            print(f"💾 检查点: {state.get('saved_checkpoint_id', '无')}")
            
            print("\n📜 执行历史:")
            for entry in state["history"]:
                step = entry.get("step", "?")
                action = entry.get("action_type", "?")
                result = entry.get("result", "?")[:50]
                print(f"   步骤{step}: {action} -> {result}")
            
            print("\n" + self.context.step_manager.get_adjustment_summary())
            print("\n" + self.context.completion_evaluator.get_completion_summary())
            print("\n" + self.context.logger.get_step_summary())
            
            from performance_monitor import get_performance_monitor
            perf_monitor = get_performance_monitor()
            perf_monitor.print_summary()
            perf_report_path = perf_monitor.save_report()
            print(f"\n📄 性能报告已保存: {perf_report_path}")
        except Exception as e:
            print(f"⚠️ 生成执行摘要时出错: {e}")
    
    def list_checkpoints(self, limit: int = 5):
        """列出可用的检查点"""
        self.context.checkpoint_manager.display_checkpoints(limit)
    
    def cleanup_old_checkpoints(self, max_age_hours: int = 24, keep_count: int = 5):
        """清理过期检查点"""
        self.context.checkpoint_manager.cleanup_old_checkpoints(max_age_hours, keep_count)
