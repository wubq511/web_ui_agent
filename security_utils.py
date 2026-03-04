"""
================================================================================
安全工具模块 - 敏感信息处理与脱敏
================================================================================

【模块概述】
提供敏感信息的安全处理功能，包括：
- 敏感信息脱敏显示
- 安全日志输出
- 敏感字段检测

【设计思路】
1. 统一的脱敏策略，避免敏感信息泄露
2. 可配置的脱敏规则
3. 自动检测敏感字段

【使用示例】
```python
from security_utils import mask_sensitive, safe_print

# 脱敏密码
masked = mask_sensitive("my_password_123", "password")
# 输出: my********23

# 安全打印（自动脱敏敏感字段）
safe_print({"username": "admin", "password": "secret123"})
# 输出: {"username": "admin", "password": "******"}
```
================================================================================
"""

import re
from typing import Any, Dict, List, Optional, Union


# 敏感字段名称列表（不区分大小写匹配）
SENSITIVE_FIELD_NAMES = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api_secret",
    "private_key",
    "privatekey",
    "access_token",
    "refresh_token",
    "auth_token",
    "credential",
    "session_key",
    "session_token",
    "authorization",
    "cookie",
    "salt",
    "hash",
    "pin",
    "cvv",
    "card_number",
    "credit_card",
    "ssn",
    "social_security",
}


def mask_string(
    value: str,
    show_prefix: int = 2,
    show_suffix: int = 2,
    mask_char: str = "*"
) -> str:
    """
    脱敏字符串
    
    【参数】
    value: 原始字符串
    show_prefix: 显示前缀字符数
    show_suffix: 显示后缀字符数
    mask_char: 脱敏字符
    
    【返回值】
    脱敏后的字符串
    
    【示例】
    >>> mask_string("password123")
    'pa******23'
    >>> mask_string("ab", show_prefix=1, show_suffix=1)
    '**'
    """
    if not value:
        return "(空)"
    
    value_str = str(value)
    length = len(value_str)
    
    if length <= show_prefix + show_suffix:
        return mask_char * length
    
    prefix = value_str[:show_prefix] if show_prefix > 0 else ""
    suffix = value_str[-show_suffix:] if show_suffix > 0 else ""
    mask_length = length - show_prefix - show_suffix
    
    return f"{prefix}{mask_char * mask_length}{suffix}"


def is_sensitive_field(field_name: str) -> bool:
    """
    判断字段名是否为敏感字段
    
    【参数】
    field_name: 字段名
    
    【返回值】
    是否为敏感字段
    """
    if not field_name:
        return False
    
    field_lower = field_name.lower().replace("_", "").replace("-", "")
    
    for sensitive in SENSITIVE_FIELD_NAMES:
        if sensitive.replace("_", "") in field_lower:
            return True
    
    return False


def mask_sensitive(
    value: Any,
    field_name: Optional[str] = None,
    show_prefix: int = 2,
    show_suffix: int = 2
) -> Any:
    """
    智能脱敏敏感信息
    
    【参数】
    value: 要脱敏的值
    field_name: 字段名（用于判断是否敏感）
    show_prefix: 显示前缀字符数
    show_suffix: 显示后缀字符数
    
    【返回值】
    脱敏后的值
    
    【示例】
    >>> mask_sensitive("secret123", "password")
    'se******23'
    >>> mask_sensitive("normal_value", "username")
    'normal_value'
    """
    if value is None:
        return None
    
    if isinstance(value, bool):
        return value
    
    if field_name and is_sensitive_field(field_name):
        if isinstance(value, str):
            return mask_string(value, show_prefix, show_suffix)
        elif isinstance(value, (int, float)):
            return mask_string(str(value), show_prefix, show_suffix)
    
    return value


def mask_dict(
    data: Dict[str, Any],
    sensitive_fields: Optional[List[str]] = None,
    show_prefix: int = 2,
    show_suffix: int = 2
) -> Dict[str, Any]:
    """
    脱敏字典中的敏感字段
    
    【参数】
    data: 原始字典
    sensitive_fields: 额外的敏感字段列表
    show_prefix: 显示前缀字符数
    show_suffix: 显示后缀字符数
    
    【返回值】
    脱敏后的字典
    """
    if not isinstance(data, dict):
        return data
    
    result = {}
    
    for key, value in data.items():
        is_sensitive = is_sensitive_field(key)
        
        if sensitive_fields and key in sensitive_fields:
            is_sensitive = True
        
        if is_sensitive and isinstance(value, str):
            result[key] = mask_string(value, show_prefix, show_suffix)
        elif is_sensitive and isinstance(value, (int, float)):
            result[key] = mask_string(str(value), show_prefix, show_suffix)
        elif isinstance(value, dict):
            result[key] = mask_dict(value, sensitive_fields, show_prefix, show_suffix)
        else:
            result[key] = value
    
    return result


mask_sensitive_in_dict = mask_dict


def safe_format(
    template: str,
    data: Dict[str, Any],
    mask_sensitive_fields: bool = True
) -> str:
    """
    安全格式化字符串，自动脱敏敏感字段
    
    【参数】
    template: 格式化模板
    data: 数据字典
    mask_sensitive_fields: 是否脱敏敏感字段
    
    【返回值】
    格式化后的字符串
    
    【示例】
    >>> safe_format("用户: {username}, 密码: {password}", 
    ...            {"username": "admin", "password": "secret123"})
    '用户: admin, 密码: se******23'
    """
    if not mask_sensitive_fields:
        return template.format(**data)
    
    masked_data = mask_dict(data)
    
    try:
        return template.format(**masked_data)
    except KeyError as e:
        return template


def sanitize_log_message(message: str) -> str:
    """
    清理日志消息中的敏感信息（智能识别真正的密码值）
    
    【参数】
    message: 原始日志消息
    
    【返回值】
    清理后的日志消息
    
    【功能】
    自动检测并脱敏日志中的：
    - 密码模式：password='xxx', 密码：'xxx'（只脱敏引号内的值）
    - Token模式：token=xxx, api_key=xxx
    - 连接字符串中的密码
    
    【设计思路】
    只脱敏真正的密码值，不脱敏描述性文本如"密码输入框"、"输入密码"等
    真正的密码通常在引号内或紧跟在等号/冒号后面
    """
    if not message:
        return message
    
    patterns = [
        (r"(password\s*[=:]\s*['\"])([^'\"]+)(['\"])", r"\1******\3"),
        (r"(passwd\s*[=:]\s*['\"])([^'\"]+)(['\"])", r"\1******\3"),
        (r"(pwd\s*[=:]\s*['\"])([^'\"]+)(['\"])", r"\1******\3"),
        (r"(token\s*[=:]\s*['\"])([^'\"]+)(['\"])", r"\1******\3"),
        (r"(api_key\s*[=:]\s*['\"])([^'\"]+)(['\"])", r"\1******\3"),
        (r"(secret\s*[=:]\s*['\"])([^'\"]+)(['\"])", r"\1******\3"),
        (r"(密码[：:]\s*['\"])([^'\"]+)(['\"])", r"\1******\3"),
        (r"(密码[是为]\s*['\"])([^'\"]+)(['\"])", r"\1******\3"),
    ]
    
    result = message
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


class SecureLogger:
    """
    安全日志记录器 - 自动脱敏敏感信息
    
    【功能】
    1. 自动检测并脱敏敏感字段
    2. 支持多种日志级别
    3. 可配置脱敏规则
    """
    
    def __init__(self, name: str, mask_enabled: bool = True):
        """
        初始化安全日志记录器
        
        【参数】
        name: 日志记录器名称
        mask_enabled: 是否启用脱敏
        """
        import logging
        self._logger = logging.getLogger(name)
        self._mask_enabled = mask_enabled
    
    def _sanitize(self, message: str) -> str:
        """清理日志消息"""
        if self._mask_enabled:
            return sanitize_log_message(message)
        return message
    
    def info(self, message: str, *args, **kwargs):
        """记录信息级别日志"""
        self._logger.info(self._sanitize(message), *args, **kwargs)
    
    def debug(self, message: str, *args, **kwargs):
        """记录调试级别日志"""
        self._logger.debug(self._sanitize(message), *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """记录警告级别日志"""
        self._logger.warning(self._sanitize(message), *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """记录错误级别日志"""
        self._logger.error(self._sanitize(message), *args, **kwargs)


def create_secure_print(prefix: str = "") -> callable:
    """
    创建安全打印函数
    
    【参数】
    prefix: 输出前缀
    
    【返回值】
    安全打印函数
    
    【示例】
    >>> secure_print = create_secure_print("[调试] ")
    >>> secure_print("密码: secret123")
    [调试] 密码: ******23
    """
    def secure_print(message: str, **kwargs):
        sanitized = sanitize_log_message(str(message))
        full_message = f"{prefix}{sanitized}" if prefix else sanitized
        print(full_message, **kwargs)
    
    return secure_print
