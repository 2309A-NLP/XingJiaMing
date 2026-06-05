# API接口文档

## 1. 角色管理接口

### 1.1 获取角色列表
- **URL**: `/api/characters`
- **方法**: GET
- **描述**: 获取系统中所有可用的角色列表
- **请求参数**: 无
- **响应格式**:
  ```json
  {
    "characters": [
      {
        "id": 1,
        "name": "李达",
        "role_type": "律师",
        "description": "温柔、专业、有耐心的刑事律师"
      },
      {
        "id": 2,
        "name": "黄耀",
        "role_type": "心理医生",
        "description": "专业、耐心的心理医生"
      },
      {
        "id": 3,
        "name": "邢佳明",
        "role_type": "医生",
        "description": "医学专家，擅长各种领域"
      }
    ]
  }
  ```

## 2. 聊天接口

### 2.1 核心聊天接口
- **URL**: `/api/chat`
- **方法**: POST
- **描述**: 与指定角色进行聊天，支持多轮对话
- **请求参数**:
  ```json
  {
    "question": "你好，我想咨询一下刑法相关的问题",
    "character_id": 1
  }
  ```
  - `question`: 用户的问题，必填
  - `character_id`: 角色ID，可选，默认为1
- **响应格式**:
  ```json
  {
    "answer": "你好～我是李达，温柔、专业、有耐心的刑事律师，有什么都可以告诉我😊"
  }
  ```

## 3. 知识库管理接口

### 3.1 知识库动态更新接口
- **URL**: `/api/update_knowledge`
- **方法**: POST
- **描述**: 上传PDF文档并更新知识库
- **请求参数**:
  - `file`: PDF文件，必填
  - `collection_name`: 集合名称，可选，默认为"law_rag"
- **响应格式**:
  ```json
  {
    "message": "知识库更新成功，添加了100条数据"
  }
  ```

## 4. 错误响应格式

所有API接口在遇到错误时，会返回以下格式的错误响应：

```json
{
  "error": "错误信息"
}
```

## 5. 示例请求

### 5.1 获取角色列表
```bash
curl http://localhost:8000/api/characters
```

### 5.2 与角色聊天
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "什么是盗窃罪？", "character_id": 1}'
```

### 5.3 更新知识库
```bash
curl -X POST http://localhost:8000/api/update_knowledge \
  -F "file=@path/to/your/document.pdf" \
  -F "collection_name=law_rag"
```
