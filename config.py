"""
================================================================================
配置模块 - Web UI Agent 的全局配置常量
================================================================================

【模块概述】
集中管理所有配置常量，便于后续修改和维护。这些常量控制着 Agent 的核心行为。

【设计思路】
将配置与代码分离的好处：
1. 修改配置时不需要翻阅大量代码
2. 便于在不同环境（开发/测试/生产）使用不同配置
3. 配置项一目了然，便于理解和维护
================================================================================
"""

from enum import Enum


class TaskComplexity(Enum):
    """
    任务复杂度枚举 - 统一定义，供所有模块使用
    
    【级别说明】
    SIMPLE: 简单任务，如搜索、点击、打开页面
    MEDIUM: 中等任务，如登录、填写表单、选择选项
    COMPLEX: 复杂任务，如购买、提交订单、发送邮件
    VERY_COMPLEX: 非常复杂任务，如批量操作、多步骤流程
    """
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


API_BASE_URL = "https://api.lingyaai.cn/v1"
MODEL_NAME = "gemini-3-flash-preview"

# ============================================================================
# 多模型配置 - 支持自主切换
# ============================================================================
# 可用模型列表，Agent可在这些模型之间自主切换
# 每个模型包含: 名称、描述、优先级、特点标签、是否支持自动切换
#
# 【模型切换策略】
# - 默认模型: gemini-3-flash-preview（速度快，成本低）
# - 自动切换目标: claude-opus-4-6（最强模型，所有模型失败时都自动切换到此模型）
# - 其他模型: 支持命令行指定、运行时切换，也支持自动切换到 claude
AVAILABLE_MODELS = {
    "gemini-3-flash-preview": {
        "name": "Gemini 3 Flash Preview",
        "description": "Google Gemini 3 Flash 预览版，速度快，成本低",
        "priority": 1,
        "tags": ["fast", "cost-effective", "general"],
        "max_tokens": 8192,
        "supports_vision": False,
        "supports_auto_switch": True,
    },
    "kimi-k2.5": {
        "name": "Kimi K2.5",
        "description": "月之暗面 Kimi K2.5，中文理解能力强，agent能力强",
        "priority": 2,
        "tags": ["chinese", "reasoning", "long-context"],
        "max_tokens": 8192,
        "supports_vision": False,
        "supports_auto_switch": True,
    },
    "claude-opus-4-6": {
        "name": "Claude Opus 4.6",
        "description": "Anthropic Claude Opus 4.6，最强agent模型，推理能力最强，支持复杂任务",
        "priority": 3,
        "tags": ["reasoning", "complex-tasks", "safety"],
        "max_tokens": 4096,
        "supports_vision": False,
        "supports_auto_switch": True,
    },
    "doubao-seed-2-0-pro": {
        "name": "Doubao Seed 2.0 Pro",
        "description": "字节跳动豆包 Seed 2.0 Pro，性价比高",
        "priority": 4,
        "tags": ["chinese", "cost-effective", "fast"],
        "max_tokens": 8192,
        "supports_vision": False,
        "supports_auto_switch": True,
    },
    "minimax-m2.5": {
        "name": "MiniMax M2.5",
        "description": "MiniMax M2.5，创意能力强",
        "priority": 5,
        "tags": ["creative", "chinese", "reasoning"],
        "max_tokens": 8192,
        "supports_vision": False,
        "supports_auto_switch": True,
    },
}

# 默认模型
DEFAULT_MODEL = "gemini-3-flash-preview"

# 自动切换的目标模型（失败时自动切换到此模型）
AUTO_SWITCH_TARGET_MODEL = "claude-opus-4-6"

# 模型切换配置
MODEL_SWITCH_CONFIG = {
    # 连续失败多少次后触发模型切换
    "failure_threshold": 3,
    # 成功调用多少次后可以考虑切换回默认模型
    "success_threshold": 5,
    # 是否启用自动切换（False则只使用默认模型）
    "auto_switch_enabled": True,
    # 切换冷却时间（秒），避免频繁切换
    "switch_cooldown": 30,
    # 是否在错误时自动切换模型
    "switch_on_error": True,
}

MAX_STEPS = 10
MIN_STEPS = 5
MAX_STEPS_LIMIT = 100
DYNAMIC_STEP_INCREMENT = 5
STEP_ADJUSTMENT_THRESHOLD = 0.7

ACTION_TIMEOUT = 30000
PAGE_LOAD_TIMEOUT = 60000

LLM_TIMEOUT = 60
LLM_TEMPERATURE = 0.7

ENV_API_KEY_NAME = "LINGYAAI_API_KEY"

TASK_TIMEOUT = 600
CHECKPOINT_INTERVAL = 5
CHECKPOINT_DIR = "checkpoints"

LOG_DIR = "logs"
LOG_LEVEL = "INFO"
LOG_MAX_SIZE = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5

ENABLE_USER_INTERACTION = True
INTERACTION_CHECK_INTERVAL = 3
USER_INPUT_TIMEOUT = 300

COMPLETION_CONFIDENCE_THRESHOLD = 0.8

PROGRESS_STAGNATION_THRESHOLD = 3
PROGRESS_STAGNATION_MIN = 3
PROGRESS_STAGNATION_MAX = 8
PROGRESS_STAGNATION_DEFAULT = 5

TASK_COMPLEXITY_KEYWORDS = {
    "simple": ["搜索", "点击", "打开", "search", "click", "open"],
    "medium": ["登录", "填写", "选择", "login", "fill", "select"],
    "complex": ["购买", "提交", "发送", "邮件", "buy", "submit", "send", "email", "购物车"],
    "very_complex": ["多个", "批量", "比较", "筛选", "全部", "完整", "multiple", "batch", "compare", "filter", "all"]
}

TASK_COMPLEXITY_WEIGHTS = {
    "simple": 1.0,
    "medium": 1.5,
    "complex": 2.0,
    "very_complex": 2.5
}

PROGRESS_LEVEL_THRESHOLD = {
    "no_progress": 0.005,
    "partial_progress": 0.02,
    "significant_progress": 0.08
}

ENABLE_FAST_MODE = True
FAST_MODE_STAGNATION_THRESHOLD = 3

ENABLE_HUMAN_INTERVENTION = True
INTERVENTION_PAUSE_DURATION = 60

ERROR_RETRY_LIMIT = 3

ERROR_TYPE_WEIGHTS = {
    "timeout": 0.5,
    "element_not_found": 0.5,
    "click_failed": 0.7,
    "input_failed": 0.6,
    "navigation_failed": 0.8,
    "api_error": 1.0,
    "network_error": 0.8,
    "unknown": 1.0
}

ERROR_SEVERITY_MULTIPLIERS = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.5,
    "critical": 3.0
}

ERROR_RECOVERY_ACTIONS = {
    "timeout": "retry_with_wait",
    "element_not_found": "refresh_and_retry",
    "click_failed": "scroll_and_retry",
    "input_failed": "clear_and_retry",
    "navigation_failed": "go_back_and_retry",
    "api_error": "abort",
    "network_error": "wait_and_retry"
}

CONSECUTIVE_ERROR_BONUS = 0.5
SUCCESS_ERROR_REDUCTION = 1
ERROR_LIMIT_MIN = 3
ERROR_LIMIT_MAX = 15
ERROR_LIMIT_DEFAULT = 5

RESOURCE_MEMORY_LIMIT = 512 * 1024 * 1024
RESOURCE_CPU_THRESHOLD = 90

DEFAULT_TASK_COMPLEXITY = TaskComplexity.MEDIUM
DEFAULT_PROGRESS_LEVEL = "no_progress"
DEFAULT_INTERVENTION_PAUSED = False
DEFAULT_FAST_MODE = False
DEFAULT_STEPS_EXTENSION = 25
MIN_REMAINING_STEPS_THRESHOLD = 10

# 代理配置（用于绕过IP检测）
# 格式: http://user:pass@host:port 或 http://host:port
# 建议使用住宅代理以获得更好的效果
PROXY_SERVER = None  # 例如: "http://127.0.0.1:7890"

# 本地Chrome路径（Windows默认路径）
LOCAL_CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
LOCAL_CHROME_USER_DATA_DIR = r"C:\chrome_dev_profile"

# CDP 远程调试端口配置（用于 web_server 连接 agent 的浏览器）
CDP_PORT = 9222
CDP_HOST = "localhost"

# 截图流配置
SCREENSHOT_TARGET_FPS = 30
SCREENSHOT_MIN_FPS = 10
SCREENSHOT_MAX_FPS = 30
SCREENSHOT_JPEG_QUALITY = 60
SCREENSHOT_MAX_WIDTH = 1280
SCREENSHOT_MAX_HEIGHT = 720
