# main.py 完整版 RAG 智能律师
import sys
from src.config.settings import DATA_DIR
from src.rag.load_pdf import load_pdf
from src.rag.chunking import chunk_text
from src.rag.embedding import embed_query
from src.rag.retrieval import search_vector
from src.rag.rerank import rerank
from src.db.redis import save_message, get_history
from src.db.mysql import save_chat_message
from src.rag.llm_chat import chat_with_law

def retrieve_law_context(query: str):
    try:
        vec = embed_query(query)
        res = search_vector(vec, top_k=10)
        docs = [hit["entity"]["text"] for hit in res[0]]
        docs = rerank(query, docs)
        return "\n".join(docs[:3])
    except:
        return "未检索到相关法条"

def run_chatbot():
    USER_ID = 1
    CHAR_ID = 1

    print("=" * 60)
    print("🧑‍⚖️ 智能刑事法律顾问（完整版RAG）")
    print("已启用：BGE-M3 | Milvus | 重排序 | Redis | MySQL")
    print("=" * 60)

    while True:
        q = input("\n💬 你：").strip()
        if q.lower() in ["exit", "quit", "q"]:
            print("👋 再见！")
            break

        ctx = retrieve_law_context(q)
        history = get_history(USER_ID, CHAR_ID)

        ans = chat_with_law(q, ctx, history)

        print("\n" + "="*60)
        print(f"📜 律师：\n{ans}")
        print("="*60)

        save_message(USER_ID, CHAR_ID, "user", q)
        save_message(USER_ID, CHAR_ID, "assistant", ans)
        save_chat_message(USER_ID, CHAR_ID, "user", q)
        save_chat_message(USER_ID, CHAR_ID, "assistant", ans)

if __name__ == "__main__":
    run_chatbot()