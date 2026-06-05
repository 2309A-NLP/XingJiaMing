import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logger.info("Step 1: Testing basic imports...")
try:
    from src.config.settings import BASE_DIR, LOG_DIR, LLM_CONFIG, MILVUS_CONFIG, REDIS_CONFIG
    logger.info("✓ Settings imported successfully")
except Exception as e:
    logger.error(f"✗ Failed to import settings: {e}")
    exit(1)

logger.info("Step 2: Testing MySQL connection...")
try:
    from src.db.mysql import register_user, authenticate_user
    logger.info("✓ MySQL module imported successfully")
except Exception as e:
    logger.error(f"✗ Failed to import MySQL: {e}")

logger.info("Step 3: Testing Redis connection...")
try:
    from src.db.redis import save_message, get_history
    logger.info("✓ Redis module imported successfully")
except Exception as e:
    logger.error(f"✗ Failed to import Redis: {e}")

logger.info("Step 4: Testing RAG modules...")
try:
    from src.rag.embedding import embed_query
    logger.info("✓ Embedding module imported successfully")
except Exception as e:
    logger.error(f"✗ Failed to import embedding: {e}")

try:
    from src.rag.retrieval import search_vector
    logger.info("✓ Retrieval module imported successfully")
except Exception as e:
    logger.error(f"✗ Failed to import retrieval: {e}")

logger.info("Step 5: Testing Milvus connection...")
import socket

def test_port(host, port, timeout=2):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.error(f"Socket error: {e}")
        return False

milvus_host = MILVUS_CONFIG['host']
milvus_port = MILVUS_CONFIG['port']
logger.info(f"Testing Milvus port {milvus_host}:{milvus_port}...")

port_open = test_port(milvus_host, milvus_port)
if port_open:
    logger.info("✓ Milvus port is open")
    try:
        from pymilvus import MilvusClient
        logger.info("✓ pymilvus imported successfully")
        try:
            milvus_client = MilvusClient(uri=f"http://{milvus_host}:{milvus_port}", timeout=5)
            collections = milvus_client.list_collections()
            logger.info(f"✓ Milvus connected successfully, collections: {collections}")
        except Exception as e:
            logger.error(f"✗ Milvus connection failed: {e}")
    except Exception as e:
        logger.error(f"✗ Failed to import pymilvus: {e}")
else:
    logger.warning(f"✗ Milvus port {milvus_host}:{milvus_port} is NOT open")

logger.info("Debug completed!")