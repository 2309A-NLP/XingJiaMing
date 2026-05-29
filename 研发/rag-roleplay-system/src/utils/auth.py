# -*- coding: utf-8 -*-  # 指定文件编码为 utf-8，支持中文注释
"""
JWT 认证工具模块

本模块提供完整的 JWT（JSON Web Token）认证功能，包括：
1. Token 生成 —— 用户登录/注册成功后签发
2. Token 验证 —— 解码并校验 Token 的有效性
3. 依赖注入 —— FastAPI 中间件自动从请求头提取并验证 Token

工作流程：
用户登录 → 服务端验证身份 → 签发 JWT Token → 客户端存储 Token →
后续请求在 Authorization 头携带 Token → 服务端解码验证 → 获取用户信息

JWT 结构：
- Header: 算法类型（HS256）
- Payload: 用户信息（user_id, phone, username）+ 过期时间（exp）+ 签发时间（iat）
- Signature: 使用 SECRET_KEY 对前两部分签名，防止篡改
"""

import os           # 用于读取环境变量（SECRET_KEY）
import time         # 时间模块，用于 Token 签发和过期时间戳
from typing import Optional, Dict  # 类型提示
from datetime import datetime, timedelta  # 日期时间计算
# python-jose 库：JWT 编码和解码的标准实现
# 相比 PyJWT，jose 支持更多加密算法，但本系统仅使用 HS256
from jose import JWTError, jwt
# FastAPI 依赖注入和 HTTP 异常
from fastapi import HTTPException, Depends
# HTTPBearer: 自动从 Authorization 头提取 Bearer Token
# HTTPAuthorizationCredentials: 包含凭证信息的类型
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ==================== JWT 配置 ====================
# SECRET_KEY: 用于签名 JWT 的密钥（生产环境必须修改，建议 32 位以上随机字符串）
# 从环境变量读取，若未设置则使用开发环境的默认值
SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
# ALGORITHM: 签名算法，HS256 是对称加密（同一个密钥签名和验证）
ALGORITHM = "HS256"
# ACCESS_TOKEN_EXPIRE_HOURS: Token 有效期（72 小时）
# 较长的有效期减少了用户频繁登录的困扰，适合咨询类应用场景
ACCESS_TOKEN_EXPIRE_HOURS = 72

# HTTPBearer 实例：告诉 FastAPI 从 HTTP Authorization 头中提取 Bearer Token
# auto_error=False 表示不自动返回 401，让自定义逻辑决定是否拒绝访问
# 这样做的目的是支持可选认证（某些接口允许匿名访问）
security = HTTPBearer(auto_error=False)


def create_access_token(user_id: int, phone: str, username: str) -> str:
    """生成 JWT access token

    Args:
        user_id: 用户 ID（数据库中的主键）
        phone: 用户手机号
        username: 用户名（真实姓名）

    Returns:
        str: 编码后的 JWT 字符串（base64url 编码的三段式 token）
    """
    # 计算过期时间：当前 UTC 时间 + 有效小时数
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    # 构建 JWT Payload（载荷）：携带用户身份信息
    # 包含标准声明（exp, iat）和自定义声明（user_id, phone, username）
    payload = {
        "user_id": user_id,          # 用户 ID（数字）
        "phone": phone,              # 手机号（用于标识）
        "username": username,         # 用户名（用于显示）
        "exp": expire,               # 过期时间（UNIX 时间戳）
        "iat": datetime.utcnow(),     # 签发时间（Issued At）
    }
    # jwt.encode: 使用 HS256 算法对 payload 签名，生成最终的 JWT 字符串
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[Dict]:
    """验证 JWT token，返回 payload

    解码并校验 Token 的签名和过期时间。
    如果 Token 有效，返回包含用户信息的字典；
    如果无效（签名错误、过期、格式错误），返回 None。

    Args:
        token: JWT 字符串

    Returns:
        dict | None: 解码后的 payload（包含 user_id, phone, username 等），无效返回 None
    """
    try:
        # jwt.decode: 解码并验证签名和过期时间
        # 如果签名不匹配或已过期，会抛出 JWTError
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload  # 返回用户信息字典
    except JWTError:
        return None  # Token 无效，返回 None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict:
    """FastAPI 依赖注入 —— 从 Bearer token 中提取当前用户

    这是 FastAPI 的依赖注入函数，用于保护需要认证的 API 端点。
    使用方式：
        @router.post("/api/protected")
        async def protected_route(current_user: Dict = Depends(get_current_user)):
            ...

    工作流程：
    1. FastAPI 自动调用 security（HTTPBearer）从 Authorization 头提取 Token
    2. 如果请求头中没有 Token，抛出 401 异常
    3. 调用 verify_token 解码 Token
    4. 如果 Token 无效或过期，抛出 401 异常
    5. 返回用户信息给路由处理函数

    Args:
        credentials: FastAPI 自动注入的认证凭证（包含 Token 字符串）

    Returns:
        dict: 用户信息字典（user_id, phone, username, exp, iat）

    Raises:
        HTTPException 401: 缺少认证令牌
        HTTPException 401: 令牌无效或已过期
    """
    if credentials is None:  # 请求头中没有 Authorization 或格式错误
        raise HTTPException(status_code=401, detail="缺少认证令牌")
    payload = verify_token(credentials.credentials)  # 解码验证 Token
    if payload is None:  # Token 解码失败或已过期
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    return payload  # 返回用户身份信息


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[Dict]:
    """可选的用户认证 —— 不强制要求 token

    与 get_current_user 不同，此函数不要求请求必须携带 Token。
    如果提供了有效 Token，返回用户信息；
    如果没有 Token，返回 None 而不是抛出异常。

    适用于部分需要区分匿名用户和已登录用户的接口。

    Args:
        credentials: FastAPI 自动注入的认证凭证

    Returns:
        dict | None: 用户信息（有有效 Token 时）或 None（无 Token 时）
    """
    if credentials is None:  # 没有提供 Token，允许匿名访问
        return None
    return verify_token(credentials.credentials)  # 有 Token 就验证并返回用户信息
