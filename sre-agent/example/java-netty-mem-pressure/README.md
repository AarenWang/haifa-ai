Mem pressure demo (Netty only)

Endpoints:
- GET  /health
- GET  /pid
- GET  /status
- POST /mem/start?targetMb=512&chunkMb=4&intervalMs=50&mode=heap
- POST /mem/stop

Build:
  mvn -q -DskipTests package

Run:
  java -Xms256m -Xmx256m -jar target/java-netty-mem-pressure-0.1.0.jar --port 8082

Trigger memory pressure:
  curl -s -XPOST "http://127.0.0.1:8082/mem/start?targetMb=800&chunkMb=4&intervalMs=10" | jq

Stop:
  curl -s -XPOST http://127.0.0.1:8082/mem/stop | jq

Notes:
- `targetMb` is capped in code to avoid accidentally killing the host.
