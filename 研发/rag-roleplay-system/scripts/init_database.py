# -*- coding: utf-8 -*-
# init_database.py - 数据库初始化脚本
import pymysql
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.settings import MYSQL_CONFIG

def init_database():
    """
    初始化数据库，创建所需的表结构
    """
    try:
        # 连接数据库（如果数据库不存在，会尝试创建）
        conn = pymysql.connect(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            charset=MYSQL_CONFIG.get("charset", "utf8mb4")
        )
        
        cursor = conn.cursor()
        
        # 创建数据库（如果不存在）
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_CONFIG['database']} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.execute(f"USE {MYSQL_CONFIG['database']}")
        
        # 先删除现有的表（如果存在）
        cursor.execute("DROP TABLE IF EXISTS chat_history")
        cursor.execute("DROP TABLE IF EXISTS characters")
        cursor.execute("DROP TABLE IF EXISTS users")
        
        # 创建用户表
        create_users_table = """
        CREATE TABLE users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL,
            email VARCHAR(100) NOT NULL UNIQUE,
            password VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
        cursor.execute(create_users_table)
        
        # 创建角色表
        create_characters_table = """
        CREATE TABLE characters (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(50) NOT NULL,
            role_type VARCHAR(50) NOT NULL,
            description TEXT,
            prompt_template TEXT NOT NULL,
            knowledge_base VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
        cursor.execute(create_characters_table)
        
        # 创建聊天记录表
        create_chat_history_table = """
        CREATE TABLE chat_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            character_id INT NOT NULL,
            role ENUM('user', 'assistant') NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        cursor.execute(create_chat_history_table)
        
        # 插入默认角色数据
        insert_default_characters = """
        INSERT IGNORE INTO characters (name, role_type, description, prompt_template, knowledge_base) VALUES
        ('林律', '律师', '温柔、专业、有耐心的刑事律师', '你是【林律】，温柔、专业、有耐心的刑事律师。\n规则：\n1. 必须记住用户之前说的所有内容（Redis短期记忆）。\n2. 必须依据知识库法条回答（Milvus长期记忆）。\n3. 用户紧张先安抚：别慌，我帮你一步步分析。\n4. 无法条就说：暂无匹配法条，不能乱回答。\n5. 只回答刑事法律问题。', 'law_rag'),
        ('王医生', '医生', '专业、耐心的内科医生', '你是【王医生】，专业、耐心的内科医生。\n规则：\n1. 必须记住用户之前说的所有内容（Redis短期记忆）。\n2. 必须依据医学知识库回答（Milvus长期记忆）。\n3. 用户紧张先安抚：别担心，我会帮你分析。\n4. 无法提供具体诊断时必须说明：建议咨询专业医生。\n5. 只回答医学相关问题。', 'medical_rag'),
        ('李老师', '教师', '知识渊博、耐心的语文教师', '你是【李老师】，知识渊博、耐心的语文教师。\n规则：\n1. 必须记住用户之前说的所有内容（Redis短期记忆）。\n2. 必须依据语文知识库回答（Milvus长期记忆）。\n3. 对学生保持耐心和鼓励。\n4. 无法回答的问题必须诚实说明。\n5. 只回答语文相关问题。', 'education_rag'),
        ('张心理', '心理专家', '专业、温暖、有同理心的心理治疗师', '你是【张心理】，专业、温暖、有同理心的心理治疗师。\n规则：\n1. 必须记住用户之前说的所有内容（Redis短期记忆）。\n2. 必须依据心理学知识库回答（Milvus长期记忆）。\n3. 对用户保持同理心和尊重。\n4. 提供专业的心理支持和建议。\n5. 只回答心理相关问题。', 'psychology_rag'),
        ('刘医学', '医学专家', '专业、严谨、经验丰富的医学专家', '你是【刘医学】，专业、严谨、经验丰富的医学专家。\n规则：\n1. 必须记住用户之前说的所有内容（Redis短期记忆）。\n2. 必须依据医学知识库回答（Milvus长期记忆）。\n3. 提供专业的医学知识和建议。\n4. 无法提供具体诊断时必须说明：建议咨询专业医生。\n5. 只回答医学相关问题。', 'medical_rag')
        """
        cursor.execute(insert_default_characters)
        
        # 插入默认用户数据
        insert_default_user = """
        INSERT IGNORE INTO users (username, email, password) VALUES
        ('admin', 'admin@example.com', 'admin123')
        """
        cursor.execute(insert_default_user)
        
        conn.commit()
        print("数据库初始化成功！")
        print("创建了用户表、角色表和聊天记录表")
        print("插入了默认角色数据")
        print("插入了默认用户数据")
        
    except Exception as e:
        print(f"数据库初始化失败：{e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    init_database()
