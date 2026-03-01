"""
================================================================================
辅助函数模块 - 通用工具函数
================================================================================

【模块概述】
提供各种辅助函数，包括：
- API 密钥获取
- JSON 解析
- 元素定位器生成（XPath、CSS选择器）
================================================================================
"""

import os
import re
import json

from bs4 import Tag

from config import ENV_API_KEY_NAME


def get_api_key() -> str:
    """
    获取 API 密钥
    
    【设计思路】
    API 密钥是敏感信息，不应该硬编码在代码中。我们通过环境变量来获取，
    这样可以：
    1. 避免将密钥泄露到代码仓库
    2. 方便在不同环境中使用不同的密钥
    3. 符合安全最佳实践
    
    【返回值】
    str: API 密钥字符串
    
    【异常】
    ValueError: 当环境变量未设置时抛出，包含详细的设置说明
    """
    api_key = os.environ.get(ENV_API_KEY_NAME)
    
    if not api_key:
        error_msg = """
╔══════════════════════════════════════════════════════════════════╗
║                    API 密钥未设置错误                            ║
╠══════════════════════════════════════════════════════════════════╣
║  未检测到环境变量 LINGYAAI_API_KEY                              ║
║                                                                  ║
║  请按以下步骤设置：                                              ║
║                                                                  ║
║  Windows (PowerShell):                                          ║
║    $env:LINGYAAI_API_KEY="你的密钥"                              ║
║                                                                  ║
║  Windows (CMD):                                                  ║
║    set LINGYAAI_API_KEY=你的密钥                                 ║
║                                                                  ║
║  Linux/macOS:                                                    ║
║    export LINGYAAI_API_KEY="你的密钥"                            ║
║                                                                  ║
║  或在代码中设置（不推荐）：                                       ║
║    os.environ["LINGYAAI_API_KEY"] = "你的密钥"                   ║
╚══════════════════════════════════════════════════════════════════╝
"""
        raise ValueError(error_msg)
    
    return api_key


def parse_json_from_response(response_text: str) -> dict:
    """
    从 LLM 响应中解析 JSON（性能优化版）
    
    【设计思路】
    大语言模型有时会在 JSON 前后添加 Markdown 标记（如 ```json ... ```），
    或者包含额外的文字说明。这个函数负责：
    1. 去除 Markdown 代码块标记
    2. 提取纯 JSON 字符串
    3. 解析为 Python 字典
    
    【参数】
    response_text: str - LLM 返回的原始文本
    
    【返回值】
    dict: 解析后的 JSON 对象
    
    【异常】
    ValueError: 当无法解析 JSON 时抛出
    """
    cleaned_text = response_text.strip()
    
    if cleaned_text.startswith('```'):
        first_newline = cleaned_text.find('\n')
        if first_newline != -1:
            cleaned_text = cleaned_text[first_newline + 1:]
        
        if cleaned_text.endswith('```'):
            cleaned_text = cleaned_text[:-3]
        
        cleaned_text = cleaned_text.strip()
    
    first_brace = cleaned_text.find('{')
    last_brace = cleaned_text.rfind('}')
    
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        cleaned_text = cleaned_text[first_brace:last_brace + 1]
    
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败: {e}\n原始响应: {response_text}")


def get_element_xpath(element: Tag) -> str:
    """
    获取元素的 XPath 路径
    
    【设计思路】
    XPath 是一种在 XML/HTML 文档中定位元素的语言。我们需要为每个元素
    生成一个唯一的 XPath，以便后续通过 Playwright 定位和操作该元素。
    
    【生成策略】
    1. 优先使用 id 属性（最精确）
    2. 其次使用 name 属性
    3. 最后使用标签名和位置索引
    
    【参数】
    element: Tag - BeautifulSoup 解析的元素对象
    
    【返回值】
    str: 元素的 XPath 路径
    """
    if element.get('id'):
        return f"//*[@id='{element.get('id')}']"
    
    if element.get('name'):
        return f"//*[@name='{element.get('name')}']"
    
    tag = element.name
    parent = element.parent
    
    if parent and isinstance(parent, Tag):
        siblings = parent.find_all(tag, recursive=False)
        if len(siblings) > 1:
            index = siblings.index(element) + 1
            return f"//{tag}[{index}]"
    
    return f"//{tag}"


def get_element_selector(element: Tag) -> str:
    """
    获取元素的 CSS 选择器
    
    【设计思路】
    CSS 选择器是另一种定位元素的方式，通常比 XPath 更简洁。
    我们按以下优先级生成选择器：
    1. id 选择器（#id）
    2. class 选择器（.class）
    3. 属性选择器（[attr=value]）
    4. 标签选择器（tag）
    
    【参数】
    element: Tag - BeautifulSoup 解析的元素对象
    
    【返回值】
    str: 元素的 CSS 选择器
    """
    if element.get('id'):
        return f"#{element.get('id')}"
    
    if element.get('class'):
        classes = element.get('class')
        if isinstance(classes, list) and classes:
            return f".{classes[0]}"
    
    if element.get('name'):
        return f"[name='{element.get('name')}']"
    
    if element.get('type'):
        return f"{element.name}[type='{element.get('type')}']"
    
    return element.name


def _is_valid_css_id(id_value: str) -> bool:
    """
    检查 CSS ID 是否有效
    
    【设计思路】
    CSS ID 选择器有一些限制：
    1. 不能以数字开头
    2. 不能包含某些特殊字符（如点号、冒号等）
    
    如果 ID 无效，我们需要使用属性选择器 [id="xxx"] 或转义。
    
    【参数】
    id_value: str - 要检查的 ID 值
    
    【返回值】
    bool: ID 是否可以直接用于 CSS 选择器
    """
    if not id_value:
        return False
    
    if id_value[0].isdigit():
        return False
    
    invalid_chars = {'.', ':', '[', ']', ' ', '#', '>', '+', '~', '*', '|', '^', '$', '@', '!', '%', '&', '(', ')', ',', ';', '<', '=', '?', '`', '{', '}', '/', '\\'}
    
    for char in id_value:
        if char in invalid_chars:
            return False
    
    return True


def _escape_css_selector(selector: str) -> str:
    """
    转义 CSS 选择器，处理无效的 ID
    
    【设计思路】
    当 ID 以数字开头或包含特殊字符时，直接使用 #id 会失败。
    我们需要将其转换为属性选择器 [id="xxx"] 或使用 CSS 转义。
    
    【转义策略】
    1. 如果是 ID 选择器（#开头），检查 ID 是否有效
    2. 如果 ID 无效，转换为属性选择器 [id="xxx"]
    3. 对于其他情况，保持原样
    
    【参数】
    selector: str - 原始 CSS 选择器
    
    【返回值】
    str: 修复后的 CSS 选择器
    """
    if not selector:
        return selector
    
    if selector.startswith('#'):
        id_value = selector[1:]
        
        if not _is_valid_css_id(id_value):
            escaped_id = id_value.replace('\\', '\\\\').replace('"', '\\"')
            return f'[id="{escaped_id}"]'
    
    return selector


def validate_url(url: str) -> tuple[bool, str]:
    """
    验证 URL 格式是否有效
    
    【设计思路】
    检查 URL 是否符合基本格式要求，包括协议、域名等。
    
    【参数】
    url: str - 要验证的 URL
    
    【返回值】
    tuple[bool, str]: (是否有效, 修复后的URL或错误信息)
    """
    if not url:
        return False, "URL 为空"
    
    url = url.strip()
    
    if not url.startswith(('http://', 'https://')):
        if '.' in url and not url.startswith(('javascript:', 'data:', 'file:')):
            url = 'https://' + url
        else:
            return False, f"无效的 URL 格式: {url}"
    
    url_pattern = re.compile(
        r'^https?://'  # 协议
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # 域名
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP 地址
        r'(?::\d+)?'  # 端口
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    if url_pattern.match(url):
        return True, url
    
    if '.' in url and len(url) > 10:
        return True, url
    
    return False, f"URL 格式验证失败: {url}"
