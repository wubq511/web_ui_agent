"""
================================================================================
账号凭证管理模块 - 安全的账号信息存储与检索系统
================================================================================

【模块概述】
提供安全的账号信息管理功能，包括：
- 加密存储账号密码信息
- 智能查询与自动填充
- 访问控制与操作日志
- 数据导入/导出与备份恢复

【安全设计】
1. 使用 AES-256-GCM 进行数据加密
2. 使用 PBKDF2 进行密钥派生
3. 密码字段使用单向哈希+盐值存储
4. 所有敏感操作记录审计日志

### 💡 使用方法
在 Agent 运行时使用命令 :
cred_login        # 登录凭证管理器（输入主密码）
cred_add          # 添加新账号
cred_list         # 列出所有账号
cred_search 淘宝  # 搜索包含"淘宝"的账号
cred_status       # 查看状态

【使用示例】
```python
from credential_manager import CredentialManager

# 初始化管理器
manager = CredentialManager()

# 添加账号
manager.add_credential(
    platform="淘宝",
    username="user@example.com",
    password="secure_password",
    alias="我的淘宝账号"
)

# 查询账号
cred = manager.get_credential_by_platform("淘宝")
print(cred["username"])  # 输出用户名（密码已脱敏）
```
================================================================================
"""

import os
import json
import hashlib
import secrets
import base64
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
import uuid

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    print("⚠️ cryptography 库未安装，使用基础加密方案。建议安装: pip install cryptography")


class CredentialError(Exception):
    """账号凭证相关错误的基类"""
    pass


class CredentialNotFoundError(CredentialError):
    """账号凭证未找到"""
    pass


class AuthenticationError(CredentialError):
    """认证失败"""
    pass


class AccessDeniedError(CredentialError):
    """访问被拒绝"""
    pass


class OperationType(Enum):
    """操作类型枚举"""
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
    QUERY = "query"
    EXPORT = "export"
    IMPORT = "import"
    LOGIN = "login"
    LOGOUT = "logout"


class AccessLevel(Enum):
    """访问权限级别"""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    ADMIN = "admin"


@dataclass
class Credential:
    """
    账号凭证数据类
    
    【字段说明】
    - id: 唯一标识符
    - platform: 关联平台/服务名称
    - username: 用户名/账号ID
    - password: 密码（加密存储）
    - alias: 账号别名
    - notes: 备注说明
    - tags: 标签列表
    - created_at: 创建时间
    - updated_at: 更新时间
    - last_used_at: 最后使用时间
    - use_count: 使用次数
    """
    id: str
    platform: str
    username: str
    password: str
    alias: str = ""
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    last_used_at: str = ""
    use_count: int = 0
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Credential':
        """从字典创建"""
        return cls(**data)
    
    def get_display_info(self, show_password: bool = False) -> Dict[str, Any]:
        """
        获取展示信息（支持数据脱敏）
        
        【参数】
        show_password: 是否显示密码明文
        
        【返回值】
        脱敏后的信息字典
        """
        info = {
            "id": self.id,
            "platform": self.platform,
            "username": self.username,
            "alias": self.alias,
            "notes": self.notes,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_used_at": self.last_used_at,
            "use_count": self.use_count
        }
        
        if show_password:
            info["password"] = self.password
        else:
            if len(self.password) > 4:
                info["password"] = self.password[:2] + "*" * (len(self.password) - 4) + self.password[-2:]
            else:
                info["password"] = "****"
        
        return info


@dataclass
class AccessLog:
    """
    访问日志数据类
    
    【字段说明】
    - timestamp: 时间戳
    - operation: 操作类型
    - credential_id: 目标凭证ID
    - credential_platform: 目标平台
    - result: 操作结果
    - details: 详细信息
    """
    timestamp: str
    operation: str
    credential_id: str = ""
    credential_platform: str = ""
    result: str = "success"
    details: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EncryptionManager:
    """
    加密管理器 - 处理所有加密相关操作
    
    【加密方案】
    1. 密钥派生：使用 PBKDF2 从用户密码派生密钥
    2. 数据加密：使用 AES-256-GCM 进行对称加密
    3. 密码哈希：使用 SHA-256 + 盐值进行单向哈希
    """
    
    def __init__(self):
        self._master_key: Optional[bytes] = None
        self._salt: Optional[bytes] = None
        self._is_initialized: bool = False
    
    def initialize(self, master_password: str, salt: Optional[bytes] = None) -> bytes:
        """
        初始化加密管理器
        
        【参数】
        master_password: 主密码
        salt: 盐值（可选，用于恢复）
        
        【返回值】
        盐值（需要保存）
        """
        if salt is None:
            self._salt = secrets.token_bytes(32)
        else:
            self._salt = salt
        
        self._master_key = self._derive_key(master_password, self._salt)
        self._is_initialized = True
        
        return self._salt
    
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """
        从密码派生加密密钥
        
        【设计思路】
        使用 PBKDF2 算法，迭代次数设置为 100000 次，
        增加暴力破解的难度。
        """
        if HAS_CRYPTOGRAPHY:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
                backend=default_backend()
            )
            return kdf.derive(password.encode('utf-8'))
        else:
            return hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt,
                100000,
                dklen=32
            )
    
    def encrypt(self, plaintext: str) -> str:
        """
        加密数据
        
        【参数】
        plaintext: 明文字符串
        
        【返回值】
        Base64 编码的密文
        """
        if not self._is_initialized:
            raise AuthenticationError("加密管理器未初始化")
        
        nonce = secrets.token_bytes(12)
        
        if HAS_CRYPTOGRAPHY:
            aesgcm = AESGCM(self._master_key)
            ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        else:
            key = self._master_key
            data = plaintext.encode('utf-8')
            simple_cipher = self._simple_xor_encrypt(key, data)
            ciphertext = nonce + simple_cipher
            nonce = b''
        
        result = nonce + ciphertext
        return base64.b64encode(result).decode('utf-8')
    
    def decrypt(self, ciphertext_b64: str) -> str:
        """
        解密数据
        
        【参数】
        ciphertext_b64: Base64 编码的密文
        
        【返回值】
        明文字符串
        """
        if not self._is_initialized:
            raise AuthenticationError("加密管理器未初始化")
        
        try:
            data = base64.b64decode(ciphertext_b64)
            
            if HAS_CRYPTOGRAPHY:
                nonce = data[:12]
                ciphertext = data[12:]
                aesgcm = AESGCM(self._master_key)
                plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            else:
                nonce = data[:12]
                ciphertext = data[12:]
                plaintext = self._simple_xor_decrypt(self._master_key, ciphertext)
            
            return plaintext.decode('utf-8')
        except Exception as e:
            raise AuthenticationError(f"解密失败: {e}")
    
    def _simple_xor_encrypt(self, key: bytes, data: bytes) -> bytes:
        """简单的 XOR 加密（备用方案）"""
        result = bytearray(len(data))
        for i, byte in enumerate(data):
            result[i] = byte ^ key[i % len(key)]
        return bytes(result)
    
    def _simple_xor_decrypt(self, key: bytes, data: bytes) -> bytes:
        """简单的 XOR 解密（备用方案）"""
        return self._simple_xor_encrypt(key, data)
    
    @staticmethod
    def hash_password(password: str, salt: Optional[str] = None) -> tuple:
        """
        对密码进行单向哈希
        
        【参数】
        password: 原始密码
        salt: 盐值（可选）
        
        【返回值】
        (哈希值, 盐值)
        """
        if salt is None:
            salt = secrets.token_hex(16)
        
        hash_value = hashlib.sha256(
            (password + salt).encode('utf-8')
        ).hexdigest()
        
        return hash_value, salt
    
    @staticmethod
    def verify_password(password: str, hash_value: str, salt: str) -> bool:
        """
        验证密码
        
        【参数】
        password: 待验证密码
        hash_value: 存储的哈希值
        salt: 盐值
        
        【返回值】
        是否匹配
        """
        computed_hash, _ = EncryptionManager.hash_password(password, salt)
        return secrets.compare_digest(computed_hash, hash_value)
    
    def get_salt(self) -> Optional[bytes]:
        """获取当前盐值"""
        return self._salt


class SessionManager:
    """
    会话管理器 - 管理访问令牌和权限
    
    【功能】
    1. 生成和验证访问令牌
    2. 管理会话超时
    3. 控制访问权限
    """
    
    def __init__(self, session_timeout: int = 3600):
        """
        初始化会话管理器
        
        【参数】
        session_timeout: 会话超时时间（秒），默认1小时
        """
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._session_timeout = session_timeout
    
    def create_session(self, access_level: AccessLevel = AccessLevel.READ_WRITE) -> str:
        """
        创建新会话
        
        【参数】
        access_level: 访问权限级别
        
        【返回值】
        会话令牌
        """
        token = secrets.token_urlsafe(32)
        self._sessions[token] = {
            "created_at": time.time(),
            "last_activity": time.time(),
            "access_level": access_level.value
        }
        return token
    
    def validate_session(self, token: str) -> bool:
        """
        验证会话是否有效
        
        【参数】
        token: 会话令牌
        
        【返回值】
        是否有效
        """
        if token not in self._sessions:
            return False
        
        session = self._sessions[token]
        current_time = time.time()
        
        if current_time - session["last_activity"] > self._session_timeout:
            del self._sessions[token]
            return False
        
        session["last_activity"] = current_time
        return True
    
    def get_access_level(self, token: str) -> Optional[AccessLevel]:
        """
        获取会话的访问权限级别
        
        【参数】
        token: 会话令牌
        
        【返回值】
        访问权限级别，无效会话返回 None
        """
        if not self.validate_session(token):
            return None
        
        return AccessLevel(self._sessions[token]["access_level"])
    
    def destroy_session(self, token: str) -> bool:
        """
        销毁会话
        
        【参数】
        token: 会话令牌
        
        【返回值】
        是否成功销毁
        """
        if token in self._sessions:
            del self._sessions[token]
            return True
        return False
    
    def cleanup_expired_sessions(self) -> int:
        """
        清理过期会话
        
        【返回值】
        清理的会话数量
        """
        current_time = time.time()
        expired_tokens = [
            token for token, session in self._sessions.items()
            if current_time - session["last_activity"] > self._session_timeout
        ]
        
        for token in expired_tokens:
            del self._sessions[token]
        
        return len(expired_tokens)


class AuditLogger:
    """
    审计日志记录器 - 记录所有操作
    
    【功能】
    1. 记录所有账号库操作
    2. 支持日志查询和导出
    3. 异常访问检测
    """
    
    def __init__(self, log_dir: str = "logs/credential_audit"):
        """
        初始化审计日志记录器
        
        【参数】
        log_dir: 日志存储目录
        """
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._logs: List[AccessLog] = []
        self._current_log_file = self._log_dir / f"audit_{datetime.now().strftime('%Y%m%d')}.json"
        self._load_today_logs()
    
    def _load_today_logs(self):
        """加载当天的日志"""
        if self._current_log_file.exists():
            try:
                with open(self._current_log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._logs = [AccessLog(**log) for log in data]
            except Exception:
                self._logs = []
    
    def log(self, operation: OperationType, credential_id: str = "",
            credential_platform: str = "", result: str = "success",
            details: str = "") -> AccessLog:
        """
        记录操作日志
        
        【参数】
        operation: 操作类型
        credential_id: 目标凭证ID
        credential_platform: 目标平台
        result: 操作结果
        details: 详细信息
        
        【返回值】
        创建的日志记录
        """
        log_entry = AccessLog(
            timestamp=datetime.now().isoformat(),
            operation=operation.value,
            credential_id=credential_id,
            credential_platform=credential_platform,
            result=result,
            details=details
        )
        
        self._logs.append(log_entry)
        self._save_logs()
        
        return log_entry
    
    def _save_logs(self):
        """保存日志到文件"""
        with open(self._current_log_file, 'w', encoding='utf-8') as f:
            json.dump([log.to_dict() for log in self._logs], f, ensure_ascii=False, indent=2)
    
    def query_logs(self, start_time: Optional[str] = None,
                   end_time: Optional[str] = None,
                   operation: Optional[OperationType] = None,
                   credential_id: Optional[str] = None) -> List[AccessLog]:
        """
        查询日志
        
        【参数】
        start_time: 开始时间（ISO格式）
        end_time: 结束时间（ISO格式）
        operation: 操作类型过滤
        credential_id: 凭证ID过滤
        
        【返回值】
        匹配的日志列表
        """
        results = []
        
        for log in self._logs:
            if start_time and log.timestamp < start_time:
                continue
            if end_time and log.timestamp > end_time:
                continue
            if operation and log.operation != operation.value:
                continue
            if credential_id and log.credential_id != credential_id:
                continue
            
            results.append(log)
        
        return results
    
    def detect_anomalies(self, time_window: int = 3600,
                         threshold: int = 10) -> List[Dict[str, Any]]:
        """
        检测异常访问
        
        【参数】
        time_window: 时间窗口（秒）
        threshold: 阈值次数
        
        【返回值】
        异常记录列表
        """
        current_time = datetime.now()
        anomalies = []
        
        recent_logs = [
            log for log in self._logs
            if (current_time - datetime.fromisoformat(log.timestamp)).total_seconds() < time_window
        ]
        
        failed_operations = [log for log in recent_logs if log.result == "failure"]
        if len(failed_operations) >= threshold:
            anomalies.append({
                "type": "excessive_failures",
                "count": len(failed_operations),
                "details": f"在 {time_window} 秒内有 {len(failed_operations)} 次失败操作"
            })
        
        query_operations = [log for log in recent_logs if log.operation == OperationType.QUERY.value]
        if len(query_operations) >= threshold * 2:
            anomalies.append({
                "type": "excessive_queries",
                "count": len(query_operations),
                "details": f"在 {time_window} 秒内有 {len(query_operations)} 次查询操作"
            })
        
        return anomalies
    
    def export_logs(self, output_path: str, start_time: Optional[str] = None,
                    end_time: Optional[str] = None) -> int:
        """
        导出日志
        
        【参数】
        output_path: 输出文件路径
        start_time: 开始时间
        end_time: 结束时间
        
        【返回值】
        导出的日志数量
        """
        logs = self.query_logs(start_time, end_time)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump([log.to_dict() for log in logs], f, ensure_ascii=False, indent=2)
        
        return len(logs)


class CredentialManager:
    """
    账号凭证管理器 - 主管理类
    
    【功能】
    1. 账号信息的增删改查
    2. 智能查询与自动填充
    3. 数据导入/导出
    4. 备份与恢复
    """
    
    def __init__(self, data_dir: str = "credential_data"):
        """
        初始化账号凭证管理器
        
        【参数】
        data_dir: 数据存储目录
        """
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        
        self._credentials_file = self._data_dir / "credentials.json"
        self._config_file = self._data_dir / "config.json"
        
        self._encryption = EncryptionManager()
        self._session = SessionManager()
        self._audit = AuditLogger(str(self._data_dir / "audit"))
        
        self._credentials: Dict[str, Credential] = {}
        self._platform_index: Dict[str, List[str]] = {}
        self._tag_index: Dict[str, List[str]] = {}
        
        self._is_initialized = False
        self._current_session: Optional[str] = None
        
        self._load_config()
    
    def _load_config(self):
        """加载配置"""
        if self._config_file.exists():
            try:
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            except Exception:
                self._config = {
                    "salt": None,
                    "password_hash": None,
                    "password_salt": None
                }
        else:
            self._config = {
                "salt": None,
                "password_hash": None,
                "password_salt": None
            }
    
    def _save_config(self):
        """保存配置"""
        with open(self._config_file, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, ensure_ascii=False, indent=2)
    
    def is_setup_complete(self) -> bool:
        """检查是否已完成初始化设置"""
        return self._config.get("password_hash") is not None
    
    def setup(self, master_password: str) -> bool:
        """
        初始化设置（首次使用）
        
        【参数】
        master_password: 主密码
        
        【返回值】
        是否设置成功
        """
        if self.is_setup_complete():
            raise CredentialError("已经完成初始化设置")
        
        salt = self._encryption.initialize(master_password)
        
        password_hash, password_salt = EncryptionManager.hash_password(master_password)
        
        self._config["salt"] = base64.b64encode(salt).decode('utf-8')
        self._config["password_hash"] = password_hash
        self._config["password_salt"] = password_salt
        
        self._save_config()
        
        self._is_initialized = True
        self._current_session = self._session.create_session(AccessLevel.ADMIN)
        
        self._audit.log(OperationType.LOGIN, result="success", details="首次初始化设置")
        
        return True
    
    def login(self, master_password: str) -> str:
        """
        登录验证
        
        【参数】
        master_password: 主密码
        
        【返回值】
        会话令牌
        
        【异常】
        AuthenticationError: 认证失败
        """
        if not self.is_setup_complete():
            raise CredentialError("请先完成初始化设置")
        
        if not EncryptionManager.verify_password(
            master_password,
            self._config["password_hash"],
            self._config["password_salt"]
        ):
            self._audit.log(OperationType.LOGIN, result="failure", details="密码错误")
            raise AuthenticationError("主密码错误")
        
        salt = base64.b64decode(self._config["salt"])
        self._encryption.initialize(master_password, salt)
        
        self._load_credentials()
        
        self._is_initialized = True
        self._current_session = self._session.create_session(AccessLevel.ADMIN)
        
        self._audit.log(OperationType.LOGIN, result="success", details="登录成功")
        
        return self._current_session
    
    def logout(self):
        """登出"""
        if self._current_session:
            self._session.destroy_session(self._current_session)
            self._audit.log(OperationType.LOGOUT, result="success")
            self._current_session = None
            self._is_initialized = False
    
    def _check_auth(self, require_level: AccessLevel = AccessLevel.READ_ONLY):
        """检查认证状态"""
        if not self._is_initialized or not self._current_session:
            raise AuthenticationError("请先登录")
        
        if not self._session.validate_session(self._current_session):
            raise AuthenticationError("会话已过期，请重新登录")
        
        current_level = self._session.get_access_level(self._current_session)
        
        level_hierarchy = {
            AccessLevel.READ_ONLY: 1,
            AccessLevel.READ_WRITE: 2,
            AccessLevel.ADMIN: 3
        }
        
        if level_hierarchy.get(current_level, 0) < level_hierarchy.get(require_level, 0):
            raise AccessDeniedError("权限不足")
    
    def _load_credentials(self):
        """加载凭证数据"""
        if not self._credentials_file.exists():
            self._credentials = {}
            self._rebuild_index()
            return
        
        try:
            with open(self._credentials_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._credentials = {
                cred_id: Credential.from_dict(cred_data)
                for cred_id, cred_data in data.items()
            }
            
            self._rebuild_index()
        except Exception as e:
            raise CredentialError(f"加载凭证数据失败: {e}")
    
    def _save_credentials(self):
        """保存凭证数据"""
        data = {
            cred_id: cred.to_dict()
            for cred_id, cred in self._credentials.items()
        }
        
        with open(self._credentials_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _rebuild_index(self):
        """重建索引"""
        self._platform_index.clear()
        self._tag_index.clear()
        
        for cred_id, cred in self._credentials.items():
            platform_lower = cred.platform.lower()
            if platform_lower not in self._platform_index:
                self._platform_index[platform_lower] = []
            self._platform_index[platform_lower].append(cred_id)
            
            for tag in cred.tags:
                tag_lower = tag.lower()
                if tag_lower not in self._tag_index:
                    self._tag_index[tag_lower] = []
                self._tag_index[tag_lower].append(cred_id)
    
    def add_credential(self, platform: str, username: str, password: str,
                       alias: str = "", notes: str = "",
                       tags: Optional[List[str]] = None) -> Credential:
        """
        添加账号凭证
        
        【参数】
        platform: 平台/服务名称
        username: 用户名
        password: 密码
        alias: 别名
        notes: 备注
        tags: 标签列表
        
        【返回值】
        创建的凭证对象
        """
        self._check_auth(AccessLevel.READ_WRITE)
        
        cred_id = str(uuid.uuid4())
        
        encrypted_password = self._encryption.encrypt(password)
        
        credential = Credential(
            id=cred_id,
            platform=platform,
            username=username,
            password=encrypted_password,
            alias=alias,
            notes=notes,
            tags=tags or []
        )
        
        self._credentials[cred_id] = credential
        
        platform_lower = platform.lower()
        if platform_lower not in self._platform_index:
            self._platform_index[platform_lower] = []
        self._platform_index[platform_lower].append(cred_id)
        
        for tag in (tags or []):
            tag_lower = tag.lower()
            if tag_lower not in self._tag_index:
                self._tag_index[tag_lower] = []
            self._tag_index[tag_lower].append(cred_id)
        
        self._save_credentials()
        
        self._audit.log(
            OperationType.ADD,
            credential_id=cred_id,
            credential_platform=platform,
            details=f"添加账号: {alias or username}"
        )
        
        return credential
    
    def update_credential(self, cred_id: str, **kwargs) -> Credential:
        """
        更新账号凭证
        
        【参数】
        cred_id: 凭证ID
        **kwargs: 要更新的字段
        
        【返回值】
        更新后的凭证对象
        """
        self._check_auth(AccessLevel.READ_WRITE)
        
        if cred_id not in self._credentials:
            raise CredentialNotFoundError(f"凭证不存在: {cred_id}")
        
        credential = self._credentials[cred_id]
        old_platform = credential.platform
        
        if 'password' in kwargs:
            kwargs['password'] = self._encryption.encrypt(kwargs['password'])
        
        for key, value in kwargs.items():
            if hasattr(credential, key):
                setattr(credential, key, value)
        
        credential.updated_at = datetime.now().isoformat()
        
        if 'platform' in kwargs:
            self._rebuild_index()
        elif 'tags' in kwargs:
            self._rebuild_index()
        
        self._save_credentials()
        
        self._audit.log(
            OperationType.UPDATE,
            credential_id=cred_id,
            credential_platform=credential.platform,
            details=f"更新字段: {list(kwargs.keys())}"
        )
        
        return credential
    
    def delete_credential(self, cred_id: str) -> bool:
        """
        删除账号凭证
        
        【参数】
        cred_id: 凭证ID
        
        【返回值】
        是否删除成功
        """
        self._check_auth(AccessLevel.ADMIN)
        
        if cred_id not in self._credentials:
            raise CredentialNotFoundError(f"凭证不存在: {cred_id}")
        
        credential = self._credentials[cred_id]
        platform = credential.platform
        
        del self._credentials[cred_id]
        
        self._rebuild_index()
        self._save_credentials()
        
        self._audit.log(
            OperationType.DELETE,
            credential_id=cred_id,
            credential_platform=platform,
            details="删除账号"
        )
        
        return True
    
    def get_credential(self, cred_id: str, show_password: bool = False) -> Dict[str, Any]:
        """
        获取账号凭证详情
        
        【参数】
        cred_id: 凭证ID
        show_password: 是否显示密码明文
        
        【返回值】
        凭证信息字典
        """
        self._check_auth()
        
        if cred_id not in self._credentials:
            raise CredentialNotFoundError(f"凭证不存在: {cred_id}")
        
        credential = self._credentials[cred_id]
        
        self._audit.log(
            OperationType.QUERY,
            credential_id=cred_id,
            credential_platform=credential.platform
        )
        
        result = credential.get_display_info(show_password=False)
        
        if show_password:
            result["password"] = self._encryption.decrypt(credential.password)
        
        return result
    
    def get_credential_by_platform(self, platform: str,
                                    show_password: bool = False) -> Optional[Dict[str, Any]]:
        """
        根据平台名称获取凭证
        
        【参数】
        platform: 平台名称
        show_password: 是否显示密码明文
        
        【返回值】
        凭证信息字典，未找到返回 None
        """
        self._check_auth()
        
        platform_lower = platform.lower()
        
        matched_ids = []
        for p_lower, ids in self._platform_index.items():
            if platform_lower in p_lower or p_lower in platform_lower:
                matched_ids.extend(ids)
        
        if not matched_ids:
            self._audit.log(
                OperationType.QUERY,
                credential_platform=platform,
                result="not_found"
            )
            return None
        
        cred_id = matched_ids[0]
        credential = self._credentials[cred_id]
        
        credential.last_used_at = datetime.now().isoformat()
        credential.use_count += 1
        self._save_credentials()
        
        self._audit.log(
            OperationType.QUERY,
            credential_id=cred_id,
            credential_platform=credential.platform,
            details=f"按平台查询: {platform}"
        )
        
        result = credential.get_display_info(show_password=False)
        
        if show_password:
            result["password"] = self._encryption.decrypt(credential.password)
        
        return result
    
    def search_credentials(self, keyword: str = "",
                           platform: str = "",
                           tag: str = "") -> List[Dict[str, Any]]:
        """
        搜索账号凭证
        
        【参数】
        keyword: 关键词（搜索平台、用户名、别名）
        platform: 平台过滤
        tag: 标签过滤
        
        【返回值】
        匹配的凭证列表
        """
        self._check_auth()
        
        results = []
        
        for cred_id, credential in self._credentials.items():
            match = True
            
            if keyword:
                keyword_lower = keyword.lower()
                if not (
                    keyword_lower in credential.platform.lower() or
                    keyword_lower in credential.username.lower() or
                    keyword_lower in credential.alias.lower() or
                    keyword_lower in credential.notes.lower()
                ):
                    match = False
            
            if platform:
                platform_lower = platform.lower()
                if platform_lower not in credential.platform.lower():
                    match = False
            
            if tag:
                tag_lower = tag.lower()
                if not any(tag_lower in t.lower() for t in credential.tags):
                    match = False
            
            if match:
                results.append(credential.get_display_info(show_password=False))
        
        self._audit.log(
            OperationType.QUERY,
            details=f"搜索: keyword={keyword}, platform={platform}, tag={tag}"
        )
        
        return results
    
    def list_all_credentials(self) -> List[Dict[str, Any]]:
        """
        列出所有凭证（脱敏）
        
        【返回值】
        凭证列表
        """
        self._check_auth()
        
        return [
            cred.get_display_info(show_password=False)
            for cred in self._credentials.values()
        ]
    
    def export_data(self, output_path: str,
                    include_passwords: bool = False) -> int:
        """
        导出数据
        
        【参数】
        output_path: 输出文件路径
        include_passwords: 是否包含密码
        
        【返回值】
        导出的凭证数量
        """
        self._check_auth(AccessLevel.ADMIN)
        
        export_data = []
        
        for credential in self._credentials.values():
            data = credential.to_dict()
            
            if include_passwords:
                data["password"] = self._encryption.decrypt(credential.password)
            else:
                data["password"] = "[已加密]"
            
            export_data.append(data)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        self._audit.log(
            OperationType.EXPORT,
            details=f"导出 {len(export_data)} 条记录, 包含密码: {include_passwords}"
        )
        
        return len(export_data)
    
    def import_data(self, input_path: str,
                    skip_duplicates: bool = True) -> Dict[str, int]:
        """
        导入数据
        
        【参数】
        input_path: 输入文件路径
        skip_duplicates: 是否跳过重复项
        
        【返回值】
        导入统计 {"added": 添加数, "skipped": 跳过数, "error": 错误数}
        """
        self._check_auth(AccessLevel.ADMIN)
        
        stats = {"added": 0, "skipped": 0, "error": 0}
        
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
        except Exception as e:
            raise CredentialError(f"读取导入文件失败: {e}")
        
        for item in import_data:
            try:
                existing = self.get_credential_by_platform(item.get("platform", ""))
                if existing and skip_duplicates:
                    stats["skipped"] += 1
                    continue
                
                password = item.get("password", "")
                if password == "[已加密]" or not password:
                    password = "需要手动设置"
                
                self.add_credential(
                    platform=item.get("platform", ""),
                    username=item.get("username", ""),
                    password=password,
                    alias=item.get("alias", ""),
                    notes=item.get("notes", ""),
                    tags=item.get("tags", [])
                )
                stats["added"] += 1
                
            except Exception as e:
                stats["error"] += 1
                print(f"导入失败: {e}")
        
        self._audit.log(
            OperationType.IMPORT,
            details=f"导入统计: {stats}"
        )
        
        return stats
    
    def create_backup(self, backup_dir: str = "backups") -> str:
        """
        创建备份
        
        【参数】
        backup_dir: 备份目录
        
        【返回值】
        备份文件路径
        """
        self._check_auth(AccessLevel.ADMIN)
        
        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_path / f"credential_backup_{timestamp}.json"
        
        backup_data = {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "config": {
                "salt": self._config.get("salt"),
                "password_hash": self._config.get("password_hash"),
                "password_salt": self._config.get("password_salt")
            },
            "credentials": {
                cred_id: cred.to_dict()
                for cred_id, cred in self._credentials.items()
            }
        }
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        return str(backup_file)
    
    def restore_backup(self, backup_file: str,
                       master_password: str) -> bool:
        """
        从备份恢复
        
        【参数】
        backup_file: 备份文件路径
        master_password: 主密码
        
        【返回值】
        是否恢复成功
        """
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
        except Exception as e:
            raise CredentialError(f"读取备份文件失败: {e}")
        
        if not EncryptionManager.verify_password(
            master_password,
            backup_data["config"]["password_hash"],
            backup_data["config"]["password_salt"]
        ):
            raise AuthenticationError("主密码与备份不匹配")
        
        self._config["salt"] = backup_data["config"]["salt"]
        self._config["password_hash"] = backup_data["config"]["password_hash"]
        self._config["password_salt"] = backup_data["config"]["password_salt"]
        self._save_config()
        
        salt = base64.b64decode(self._config["salt"])
        self._encryption.initialize(master_password, salt)
        
        self._credentials = {
            cred_id: Credential.from_dict(cred_data)
            for cred_id, cred_data in backup_data["credentials"].items()
        }
        
        self._rebuild_index()
        self._save_credentials()
        
        self._is_initialized = True
        self._current_session = self._session.create_session(AccessLevel.ADMIN)
        
        self._audit.log(
            OperationType.IMPORT,
            details=f"从备份恢复: {backup_file}"
        )
        
        return True
    
    def get_audit_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取审计日志
        
        【参数】
        limit: 返回数量限制
        
        【返回值】
        日志列表
        """
        self._check_auth(AccessLevel.ADMIN)
        
        logs = self._audit.query_logs()
        return [log.to_dict() for log in logs[-limit:]]
    
    def check_anomalies(self) -> List[Dict[str, Any]]:
        """
        检查异常访问
        
        【返回值】
        异常记录列表
        """
        self._check_auth(AccessLevel.ADMIN)
        
        return self._audit.detect_anomalies()
    
    def auto_fill_for_platform(self, platform: str) -> Optional[Dict[str, str]]:
        """
        自动填充接口 - 供 AI Agent 调用
        
        【参数】
        platform: 平台名称
        
        【返回值】
        包含 username 和 password 的字典，未找到返回 None
        """
        try:
            cred = self.get_credential_by_platform(platform, show_password=True)
            if cred:
                return {
                    "username": cred["username"],
                    "password": cred["password"],
                    "platform": cred["platform"],
                    "alias": cred.get("alias", "")
                }
        except Exception as e:
            print(f"自动填充失败: {e}")
        
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取管理器状态
        
        【返回值】
        状态信息字典
        """
        return {
            "is_initialized": self._is_initialized,
            "is_setup_complete": self.is_setup_complete(),
            "credential_count": len(self._credentials),
            "platform_count": len(self._platform_index),
            "tag_count": len(self._tag_index),
            "has_session": self._current_session is not None
        }
