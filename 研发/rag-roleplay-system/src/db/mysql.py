# -*- coding: utf-8 -*-
"""
MySQL 数据库操作模块

┌──────────────────────────────────────────────────────────────────────┐
│ 本模块是整个系统的数据持久层，负责：                                  │
│ 1. 自定义数据库连接池（线程安全，最大 5 连接，防泄漏）               │
│ 2. 用户管理（注册、认证、查询）                                      │
│ 3. 角色管理（获取角色信息、更新知识库配置）                          │
│ 4. 聊天记录管理（保存、查询、清理）                                  │
│ 5. 数据库表自动初始化                                                 │
├──────────────────────────────────────────────────────────────────────┤
│ 表结构: users / characters / chat_history                             │
│ 技术栈: pymysql + bcrypt + threading                                 │
│ 安全: bcrypt 哈希密码 + SQL 参数化查询（防注入）                      │
└──────────────────────────────────────────────────────────────────────┘
"""

# ============================================================================
# 标准库导入
# ============================================================================
import pymysql  # MySQL 数据库驱动（纯 Python 实现，无需安装 MySQL Client）
import time  # 时间函数（保留用于可能的超时控制）
import threading  # 线程锁（保证连接池的线程安全）
import bcrypt  # bcrypt 密码哈希（安全级别远高于 SHA256/MD5）
from contextlib import contextmanager  # 上下文管理器装饰器（实现 with 语句支持）

# 项目配置 — 数据库连接参数
from ..config.settings import MYSQL_CONFIG


# ============================================================================
# 密码工具函数
# ============================================================================

def _hash_password(password: str) -> str:
    """
    bcrypt 密码哈希 — 自动加盐 + cost factor 控制

    bcrypt 的特点:
        - 内置 salt（随机字符串），每次哈希结果不同
        - cost factor = 12: 2^12 = 4096 轮迭代，暴力破解成本极高
        - 输出格式: $2b$12$salt+hash（包含算法、cost、salt、hash）

    参数:
        password: 明文密码

    返回:
        str: bcrypt 哈希字符串（约 60 字符）
    """
    # bcrypt.hashpw() 接受 bytes 类型参数
    # password.encode() 将 str 转为 bytes
    # bcrypt.gensalt(rounds=12) 生成 salt，cost factor = 12
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def _verify_password(password: str, hashed: str) -> bool:
    """
    验证密码是否匹配 bcrypt 哈希

    兼容旧密码:
        - 优先使用 bcrypt.checkpw() 验证（新密码）
        - 如果抛出异常（哈希格式不兼容），尝试用 SHA256 验证（旧密码）
        - 这使得系统可以从旧版 SHA256 平滑升级到 bcrypt

    参数:
        password: 用户输入的明文密码
        hashed:   数据库中存储的哈希值

    返回:
        bool: 密码匹配返回 True，否则返回 False
    """
    try:
        # 标准 bcrypt 验证
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except (ValueError, TypeError):
        # 兼容旧的 SHA256 密码哈希
        # 系统早期版本使用 hashlib.sha256() 存储密码
        # 当 bcrypt.checkpw 抛出异常时，尝试用 SHA256 验证
        import hashlib
        old_hash = hashlib.sha256(password.encode()).hexdigest()
        return old_hash == hashed


# ============================================================================
# 数据库连接池
# ============================================================================

class ConnectionPool:
    """
    线程安全的数据库连接池

    ┌────────────────────────────────────────────────────────────────┐
    │ 为什么需要连接池？                                              │
    │                                                                │
    │ MySQL 连接的建立过程:                                           │
    │ 1. TCP 三次握手（网络开销）                                     │
    │ 2. MySQL 认证握手（计算开销）                                   │
    │ 3. 设置字符集、事务模式等（配置开销）                           │
    │ 总共约 10-50ms，高并发下频繁创建/销毁 → 性能瓶颈               │
    │                                                                │
    │ 连接池的解决方案:                                              │
    │ - 预先创建一组连接 → 复用 → 减少创建/销毁开销                  │
    │ - 控制最大连接数 → 防止 MySQL 连接耗尽                         │
    │ - 自动检测坏连接 → 提高系统稳定性                              │
    └────────────────────────────────────────────────────────────────┘

    线程安全:
        使用 threading.Lock 确保多线程环境下连接的正确分配和回收

    连接泄漏防护:
        - get_connection 创建失败时自动回减计数器
        - return_connection 确保连接被回收（即使发生异常）
        - 坏连接被自动丢弃（不会放回池中）

    Attributes:
        max_connections: 最大连接数（默认 5）
        connections:     空闲连接列表（可以被复用的连接）
        active_count:    当前活跃连接数（用于控制总连接数）
    """

    def __init__(self, max_connections=5):
        """
        初始化连接池

        参数:
            max_connections: 最大连接数，默认 5
                             MySQL 默认 max_connections=151，
                             留有余量给其他服务使用
        """
        self.max_connections = max_connections  # 最大连接数上限
        self.connections = []                   # 空闲连接池（List 作为栈，后进先出）
        self.active_count = 0                   # 当前活跃连接数
        self._lock = threading.Lock()           # 线程锁（保护共享资源）

    def get_connection(self):
        """
        从连接池获取一个可用连接

        获取策略:
            1. 优先复用空闲池中的连接（栈顶取出）
            2. 检查空闲连接是否有效（ping），无效则丢弃
            3. 如果空闲池为空且活跃数未达上限，创建新连接
            4. 如果已达上限，抛出 RuntimeError

        线程安全:
            - 锁内操作: 空闲池弹出、活跃计数增减
            - 锁外操作: 创建新连接（可能耗时，不在锁内执行）

        返回:
            pymysql.Connection: 可用的数据库连接

        抛出:
            RuntimeError: 连接池已耗尽（活跃连接数达上限）
        """
        # Step 1: 锁内 — 尝试复用空闲连接
        with self._lock:
            # 遍历空闲连接栈（后进先出，最近使用的连接最可能有效）
            while self.connections:
                conn = self.connections.pop()
                try:
                    # 检测连接是否有效，无效时自动重连
                    # ping(reconnect=True) 会在连接断开时尝试自动重连
                    conn.ping(reconnect=True)
                    self.active_count += 1  # 标记为活跃
                    return conn
                except Exception:
                    # 坏连接：关闭释放资源，不计入活跃数
                    # 注意: active_count 没变，因为坏连接之前已经在池中
                    conn.close()

            # 检查是否已达最大连接数上限
            if self.active_count >= self.max_connections:
                raise RuntimeError("连接池耗尽，请稍后重试")

            # 准备创建新连接：先增加计数（防止并发时超限）
            self.active_count += 1

        # ★ Step 2: 锁外 — 创建新连接
        # 在锁外执行 connect() 是因为创建连接可能耗时，
        # 如果在锁内执行，其他线程会被阻塞等待
        try:
            return pymysql.connect(
                host=MYSQL_CONFIG["host"],                    # MySQL 主机地址
                port=MYSQL_CONFIG["port"],                    # MySQL 端口（默认 3306）
                user=MYSQL_CONFIG["user"],                    # 数据库用户名
                password=MYSQL_CONFIG["password"],            # 数据库密码
                database=MYSQL_CONFIG["database"],            # 数据库名
                charset=MYSQL_CONFIG.get("charset", "utf8mb4"),  # 字符编码（支持 emoji）
                cursorclass=pymysql.cursors.DictCursor        # ★ 返回字典格式结果
            )
        except Exception:
            # ★ 创建失败必须回减 active_count，否则永久泄漏
            # 如果不回减，这个"失败"的槽位永远不会被释放
            with self._lock:
                self.active_count -= 1
            raise

    def return_connection(self, conn):
        """
        归还连接到连接池

        策略:
            - 如果空闲池未满（< max_connections），放回池中
            - 如果空闲池已满，直接关闭连接（节省资源）

        参数:
            conn: 要归还的 pymysql 连接对象
        """
        with self._lock:
            # 减少活跃计数
            self.active_count -= 1

            # 如果空闲池还有空间，放回池中复用
            if len(self.connections) < self.max_connections:
                self.connections.append(conn)
            else:
                # 空闲池已满，直接关闭连接
                conn.close()


# 全局唯一连接池实例（模块级单例）
# 所有数据库操作共享同一个连接池
pool = ConnectionPool()


@contextmanager
def get_mysql_connection():
    """
    获取 MySQL 连接的上下文管理器

    使用 contextmanager 装饰器实现 with 语句支持。
    确保连接在使用完毕后自动归还到连接池。

    用法:
        with get_mysql_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users")

    重要设计:
        - 每次 finally 中强制回滚（rollback）事务
        - 原因: pymysql 默认 autocommit=off，使用完后如果不回滚，
          连接上的事务状态会残留，下次复用时可能看到旧数据快照
        - 例如: 第一个事务插入了用户，第二个事务 select 可能看不到
        - 这叫"事务隔离级别导致的幻读/不可重复读"问题
    """
    # 从连接池获取一个连接
    conn = pool.get_connection()

    try:
        # 将连接提供给 with 块使用
        yield conn

    except Exception as e:
        # 如果发生异常，回滚事务（如果有未提交的操作）
        conn.rollback()
        raise e  # 重新抛出异常，让调用方处理

    finally:
        # ★ 归还前强制回滚，清理事务状态
        # 这是防止"连接复用脏数据"的关键步骤
        try:
            conn.rollback()
        except Exception:
            pass  # 如果连接已断开，忽略回滚错误

        # ★ 无论成功还是失败，都必须归还连接
        pool.return_connection(conn)


# ============================================================================
# 数据库初始化
# ============================================================================

def init_database():
    """
    初始化数据库表结构 — 自动建表 + 插入默认角色数据

    在模块加载时自动调用（本文件最后一行）。
    如果表已存在不会重复创建（使用 CREATE TABLE IF NOT EXISTS）。

    表结构:
        users:       用户表（id, phone, name, password, role, created_at）
        characters:  角色表（id, name, role_type, description, prompt_template, knowledge_base）
        chat_history: 聊天记录表（id, user_id, character_id, role, content, created_at）
    """
    try:
        with get_mysql_connection() as conn:
            with conn.cursor() as cursor:
                # ==================== 1. 创建用户表 ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id         INT AUTO_INCREMENT PRIMARY KEY,  -- 用户ID（自增主键）
                        phone      VARCHAR(20) UNIQUE NOT NULL,    -- 手机号（唯一，登录标识）
                        name       VARCHAR(100) NOT NULL,           -- 用户名（真实姓名）
                        password   VARCHAR(255) NOT NULL,           -- bcrypt 哈希密码
                        role       VARCHAR(20) DEFAULT NULL,        -- 当前角色（预留字段）
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 注册时间
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;  -- InnoDB 支持事务，utf8mb4 支持 emoji
                ''')

                # 兼容旧表：尝试添加 role 列（如果已存在则忽略错误）
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT NULL")
                except Exception:
                    pass  # 列已存在会报错，忽略

                # ==================== 2. 创建角色表 ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS characters (
                        id              INT AUTO_INCREMENT PRIMARY KEY,  -- 角色ID
                        name            VARCHAR(50) NOT NULL,            -- 角色名称
                        role_type       VARCHAR(50) NOT NULL,            -- 角色类型标识
                        description     TEXT,                            -- 角色描述
                        prompt_template TEXT,                            -- 人设Prompt模板
                        knowledge_base  VARCHAR(50)                      -- 关联知识库名
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                ''')

                # ==================== 3. 创建聊天记录表 ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS chat_history (
                        id            INT AUTO_INCREMENT PRIMARY KEY,  -- 记录ID
                        user_id       INT NOT NULL,                    -- 用户ID（外键→users）
                        character_id  INT NOT NULL,                    -- 角色ID（外键→characters）
                        role          VARCHAR(20) NOT NULL,            -- 消息角色（user/assistant）
                        content       TEXT NOT NULL,                   -- 消息内容
                        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 发送时间
                        FOREIGN KEY (user_id) REFERENCES users(id),          -- 外键约束
                        FOREIGN KEY (character_id) REFERENCES characters(id) -- 外键约束
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                ''')

                # ==================== 4. 插入默认角色数据 ====================
                # INSERT IGNORE: 如果角色已存在则跳过（重复 id 不报错）
                cursor.execute('''
                    INSERT IGNORE INTO characters (id, name, role_type, description, prompt_template, knowledge_base) VALUES
                    (1, '刑事律师', 'lawyer', '专注刑事辩护10年+，擅长处理各类刑事案件',
                     '你是一位专业的刑事律师，擅长盗窃罪、抢劫罪、故意伤害罪、毒品犯罪、金融诈骗等各类刑事案件的法律辩护。请用专业的法律知识回答用户的问题。',
                     'law'),
                    (2, '心理咨询师', 'psychologist', '咨询经验8年+，擅长情绪管理、压力缓解',
                     '你是一位专业的心理咨询师，擅长情绪管理、压力缓解、人际关系等心理问题。请用温暖专业的态度回答用户的问题。',
                     'psychology'),
                    (3, '医学专家', 'doctor', '从医20年+，擅长常见病、慢性病管理',
                     '你是一位资深的医学专家，擅长常见病、慢性病管理、健康咨询等医学问题。请用科学的医学知识回答用户的问题。',
                     'medical')
                ''')

            conn.commit()  # 提交所有 DDL 和 DML 操作
        print("数据库初始化成功")

    except Exception as e:
        # 初始化失败不影响系统启动（表已经存在的情况）
        print(f"数据库初始化失败：{e}")


# ============================================================================
# 用户管理
# ============================================================================

def register_user(phone: str, password: str, name: str = "") -> bool:
    """
    注册新用户

    流程:
        1. 检查手机号是否已注册（唯一性约束）
        2. bcrypt 哈希密码
        3. 插入 users 表
        4. 自动提交事务

    参数:
        phone:    用户手机号（用作登录标识）
        password: 用户明文密码（函数内自动哈希）
        name:     用户真实姓名（为空时使用手机号作为默认名）

    返回:
        bool: True=注册成功, False=手机号已存在或出错
    """
    try:
        with get_mysql_connection() as conn:
            with conn.cursor() as cursor:
                # Step 1: 检查手机号是否已存在
                cursor.execute("SELECT id FROM users WHERE phone = %s", (phone,))
                if cursor.fetchone():
                    return False  # 手机号已注册

                # Step 2: bcrypt 哈希密码
                hashed = _hash_password(password)

                # Step 3: 插入用户记录
                # 如果 name 为空，使用 phone 作为用户名
                username = name or phone
                cursor.execute(
                    "INSERT INTO users (phone, name, password) VALUES (%s, %s, %s)",
                    (phone, username, hashed)  # SQL 参数化查询（防注入）
                )
            conn.commit()  # 提交事务
        return True

    except Exception as e:
        from src.utils.logger import logger
        logger.error(f"注册用户异常：{e}")
        return False


def authenticate_user(phone: str, password: str) -> dict:
    """
    用户认证（登录验证）

    流程:
        1. 根据手机号查询用户
        2. 如果用户不存在，返回特定错误信息（不暴露是否已注册）
        3. bcrypt 验证密码
        4. （可选）将旧 SHA256 密码自动升级为 bcrypt
        5. 返回用户信息（id, username）

    密码升级策略:
        - 检测到旧 SHA256 哈希（不以 $2 开头）→ 验证通过后替换为 bcrypt
        - 下次登录时使用 bcrypt 验证，无需再次升级

    参数:
        phone:    用户手机号
        password: 用户输入的密码

    返回:
        dict: 成功 → {"id": int, "username": str}
              失败 → {"error": "错误描述"}
    """
    try:
        with get_mysql_connection() as conn:
            with conn.cursor() as cursor:
                # Step 1: 查找用户
                cursor.execute(
                    "SELECT id, phone, name, password FROM users WHERE phone = %s",
                    (phone,)
                )
                user = cursor.fetchone()

                # Step 2: 用户不存在
                if not user:
                    return {"error": "手机号未注册"}

                # Step 3: 验证密码
                stored_hash = user["password"]
                if _verify_password(password, stored_hash):
                    # Step 4（可选）: 自动升级旧 SHA256 哈希为 bcrypt
                    # bcrypt 哈希以 $2 开头（$2a$, $2b$, $2y$）
                    # 如果不是 → 是旧 SHA256 哈希 → 升级
                    if not stored_hash.startswith("$2"):
                        new_hash = _hash_password(password)
                        cursor.execute(
                            "UPDATE users SET password = %s WHERE id = %s",
                            (new_hash, user["id"])
                        )
                        conn.commit()

                    # 认证成功，返回用户信息
                    return {"id": user["id"], "username": user["name"]}

                # Step 5: 密码错误
                return {"error": "密码错误"}

    except RuntimeError as e:
        # 连接池耗尽等明确运行时错误 — 透传错误信息
        from src.utils.logger import logger
        logger.error(f"认证服务异常：{e}")
        return {"error": str(e)}

    except Exception as e:
        # 其他异常 — 不对外暴露具体错误
        from src.utils.logger import logger
        logger.error(f"验证用户异常：{e}")
        return {"error": "系统繁忙，请稍后重试"}


def get_user_by_id(user_id: int) -> dict:
    """
    根据用户 ID 获取用户信息

    主要用于聊天管线中获取用户名（注入到 Prompt 中）。

    参数:
        user_id: 用户 ID

    返回:
        dict: 成功 → {"id": int, "username": str}
              失败 → None（用户不存在或查询出错）
    """
    try:
        with get_mysql_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, name FROM users WHERE id = %s", (user_id,))
                user = cursor.fetchone()
                if user:
                    return {"id": user["id"], "username": user["name"]}
    except Exception as e:
        from src.utils.logger import logger
        logger.error(f"获取用户信息异常：{e}")
    return None


# ============================================================================
# 角色管理
# ============================================================================

def get_character_info(character_id: int = 1):
    """
    获取角色详细信息

    降级策略（★ 关键设计）:
        如果 MySQL 连接失败（如数据库宕机），返回硬编码的默认角色数据。
        确保系统在部分依赖宕机时仍能基本运行。

    参数:
        character_id: 角色 ID（1=律师, 2=心理, 3=医疗）, 默认 1

    返回:
        dict: {
            "id": int, "name": str, "role_type": str,
            "description": str, "prompt_template": str, "knowledge_base": str
        }
    """
    try:
        with get_mysql_connection() as conn:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM characters WHERE id = %s"
                cursor.execute(sql, (character_id,))
                result = cursor.fetchone()
                if result:
                    return {
                        "id": result["id"],
                        "name": result["name"],
                        "role_type": result["role_type"],
                        "description": result["description"],
                        "prompt_template": result["prompt_template"],
                        "knowledge_base": result["knowledge_base"]
                    }
    except Exception as e:
        from src.utils.logger import logger
        logger.error(f"获取角色信息异常：{e}")

    # ★ 降级: MySQL 不可用时返回默认角色信息
    default_roles = {
        1: {
            "id": 1,
            "name": "刑事律师",
            "role_type": "lawyer",
            "description": "专注刑事辩护10年+，擅长处理各类刑事案件",
            "prompt_template": "你是一位专业的刑事律师，擅长盗窃罪、抢劫罪、故意伤害罪、毒品犯罪、金融诈骗等各类刑事案件的法律辩护。请用专业的法律知识回答用户的问题。",
            "knowledge_base": "law"
        },
        2: {
            "id": 2,
            "name": "心理咨询师",
            "role_type": "psychologist",
            "description": "咨询经验8年+，擅长情绪管理、压力缓解",
            "prompt_template": "你是一位专业的心理咨询师，擅长情绪管理、压力缓解、人际关系等心理问题。请用温暖专业的态度回答用户的问题。",
            "knowledge_base": "psychology"
        },
        3: {
            "id": 3,
            "name": "医学专家",
            "role_type": "doctor",
            "description": "从医20年+，擅长常见病、慢性病管理",
            "prompt_template": "你是一位资深的医学专家，擅长常见病、慢性病管理、健康咨询等医学问题。请用科学的医学知识回答用户的问题。",
            "knowledge_base": "medical"
        }
    }
    return default_roles.get(character_id, default_roles[1])


def update_character_knowledge_base(character_id: int, knowledge_base: str) -> bool:
    """
    更新角色的知识库配置

    用于管理员动态切换角色关联的知识库。

    参数:
        character_id:  角色 ID
        knowledge_base: 知识库名称（如 "law", "medical", "psychology"）

    返回:
        bool: 更新成功返回 True，失败返回 False
    """
    try:
        with get_mysql_connection() as conn:
            with conn.cursor() as cursor:
                sql = "UPDATE characters SET knowledge_base = %s WHERE id = %s"
                cursor.execute(sql, (knowledge_base, character_id))
                conn.commit()
                return True
    except Exception as e:
        from src.utils.logger import logger
        logger.error(f"更新角色知识库异常：{e}")
        return False


def update_user_role(user_id: int, role_id: str) -> bool:
    """
    更新用户当前角色

    记录用户在系统中最后选中的角色，便于下次进入时自动恢复。

    参数:
        user_id: 用户 ID
        role_id: 角色标识（"lawyer" | "doctor" | "psych"）

    返回:
        bool: 更新成功返回 True，失败返回 False
    """
    try:
        with get_mysql_connection() as conn:
            with conn.cursor() as cursor:
                sql = "UPDATE users SET role = %s WHERE id = %s"
                cursor.execute(sql, (role_id, user_id))
                conn.commit()
                return cursor.rowcount > 0  # rowcount > 0 表示有行被更新
    except Exception as e:
        from src.utils.logger import logger
        logger.error(f"更新用户角色异常：{e}")
        return False


def get_all_characters():
    """
    获取所有角色列表

    用于角色选择页展示。

    降级策略:
        MySQL 不可用时返回硬编码的默认角色列表。

    返回:
        list: 每个角色包含 {id, name, role_type, description}
    """
    try:
        with get_mysql_connection() as conn:
            with conn.cursor() as cursor:
                sql = "SELECT id, name, role_type, description FROM characters"
                cursor.execute(sql)
                return cursor.fetchall()
    except Exception as e:
        from src.utils.logger import logger
        logger.error(f"获取角色列表异常：{e}")

        # 降级: 返回默认角色列表
        return [
            {"id": 1, "name": "刑事律师", "role_type": "lawyer", "description": "专注刑事辩护10年+，擅长处理各类刑事案件"},
            {"id": 2, "name": "心理咨询师", "role_type": "psychologist", "description": "咨询经验8年+，擅长情绪管理、压力缓解"},
            {"id": 3, "name": "医学专家", "role_type": "doctor", "description": "从医20年+，擅长常见病、慢性病管理"}
        ]


# ============================================================================
# 聊天记录管理
# ============================================================================

def save_chat_message(user_id, character_id, role, content):
    """
    保存聊天记录到 MySQL（持久存储）

    与 Redis 短期记忆的区别:
        - Redis: 用于构建 Prompt 上下文（5 分钟过期）
        - MySQL: 历史记录持久化（可用于数据分析和用户行为追溯）

    自动注册:
        如果 user_id 对应的用户不存在，自动创建一个"匿名"用户记录。
        这是为了兼容早期版本的离线用户数据。

    参数:
        user_id:      用户 ID
        character_id: 角色 ID
        role:         消息角色（"user" 或 "assistant"）
        content:      消息内容
    """
    try:
        with get_mysql_connection() as conn:
            with conn.cursor() as cursor:
                # 检查用户是否存在，不存在则自动创建
                cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
                if not cursor.fetchone():
                    # 自动创建用户（兼容离线用户数据）
                    hashed = bcrypt.hashpw(b"auto_generated", bcrypt.gensalt(rounds=12)).decode()
                    cursor.execute(
                        "INSERT INTO users (id, phone, name, password) VALUES (%s, %s, %s, %s)",
                        (user_id, f"user_{user_id}", f"用户{user_id}", hashed)
                    )
                    conn.commit()

                # 插入聊天记录
                sql = """
                    INSERT INTO chat_history
                    (user_id, character_id, role, content)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(sql, (user_id, character_id, role, content))
            conn.commit()
    except Exception as e:
        from src.utils.logger import logger
        logger.error(f"保存聊天记录异常：{e}")


def clean_expired_chat_history(days=2):
    """
    清理过期的聊天记录（按天保留）

    定时任务（可由 cron 触发）:
        删除超过指定天数的历史记录，释放 MySQL 存储空间。

    参数:
        days: 保留天数，默认 2 天

    返回:
        int: 删除的记录数量
    """
    try:
        with get_mysql_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    DELETE FROM chat_history
                    WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)
                """
                cursor.execute(sql, (days,))
                deleted_count = cursor.rowcount
            conn.commit()
            from src.utils.logger import logger
            logger.info(f"清理过期聊天记录：删除了{deleted_count}条记录")
            return deleted_count
    except Exception as e:
        from src.utils.logger import logger
        logger.error(f"清理过期聊天记录异常：{e}")
        return 0


def get_chat_history(user_id, character_id, limit=10):
    """
    获取用户与特定角色的最近聊天记录

    注意: 当前系统主要使用 Redis 存储短期对话历史，
          此函数供后续扩展使用（如历史消息回溯功能）。

    参数:
        user_id:      用户 ID
        character_id: 角色 ID
        limit:        返回记录数量，默认 10 条

    返回:
        list: 聊天记录列表，每条包含 {role, content}，按时间正序排列
    """
    try:
        with get_mysql_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT role, content FROM chat_history
                    WHERE user_id = %s AND character_id = %s
                    ORDER BY created_at DESC LIMIT %s
                """
                cursor.execute(sql, (user_id, character_id, limit))
                data = cursor.fetchall()
                return list(data)[::-1]  # ★ 反转：DESC → 正序（最早的消息在前）
    except Exception as e:
        from src.utils.logger import logger
        logger.error(f"获取聊天记录异常：{e}")
        return []


def format_chat_history(history: list) -> str:
    """
    将结构化的聊天记录转换为 Prompt 文本格式

    用于将 MySQL 中的历史记录格式化为 LLM 可读的文本。

    输入:
        [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "您好"}]

    输出:
        "用户：你好\n助手：您好"

    参数:
        history: 聊天记录列表（来自 get_chat_history）

    返回:
        str: 格式化后的对话历史文本
    """
    lines = []
    for msg in history:
        role = "用户" if msg["role"] == "user" else "助手"
        lines.append(f"{role}：{msg['content']}")

    return "\n".join(lines)


# ============================================================================
# 模块加载时自动初始化数据库表结构
# 这是模块级代码，在首次 import 时执行
# ============================================================================
init_database()
