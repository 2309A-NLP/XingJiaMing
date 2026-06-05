import socket
import time

def test_ports(host, ports):
    """测试多个端口"""
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        status = "OPEN" if result == 0 else "CLOSED"
        print(f"Port {port}: {status}")
        sock.close()

def try_milvus_connection(host, port):
    """尝试连接 Milvus"""
    print("\nTrying to connect to Milvus at %s:%d" % (host, port))
    try:
        from pymilvus import MilvusClient
        client = MilvusClient(uri=f"http://{host}:{port}", timeout=5)
        collections = client.list_collections()
        print("Milvus connected successfully!")
        print("Available collections:", collections)
        return client
    except Exception as e:
        print("Milvus connection failed:", e)
        return None

if __name__ == "__main__":
    host = "192.168.72.128"
    common_ports = [19530, 19121, 9091, 9092, 2181, 8080, 80]
    
    print("Testing connectivity to %s..." % host)
    print("=" * 50)
    
    test_ports(host, common_ports)
    
    client = try_milvus_connection(host, 19530)
    
    if client:
        print("\nMilvus is working!")
    else:
        print("\nMilvus is not accessible. Please check:")
        print("1. Milvus service is running in the VM")
        print("2. Firewall allows port 19530")
        print("3. Port forwarding is configured correctly")