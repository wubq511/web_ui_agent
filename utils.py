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
    从 LLM 响应中解析 JSON
    
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
    
    json_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    match = re.search(json_block_pattern, cleaned_text)
    
    if match:
        cleaned_text = match.group(1).strip()
    
    json_obj_pattern = r'\{[\s\S]*\}'
    match = re.search(json_obj_pattern, cleaned_text)
    
    if match:
        cleaned_text = match.group(0)
    
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
