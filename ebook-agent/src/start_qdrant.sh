QDRANT_VERSION="v1.16.2"

# 如果文件不存在
if [ ! -f "qdrant" ]; then
  curl -L -o qdrant.tar.gz "https://github.com/qdrant/qdrant/releases/download/${QDRANT_VERSION}/qdrant-x86_64-apple-darwin.tar.gz"
  tar -xzf qdrant.tar.gz
fi


# 启动（前台）
./qdrant