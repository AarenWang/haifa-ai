GC thrash demo (Netty only)

Endpoints:
- GET  /health
- GET  /pid
- GET  /status
- POST /gc/start?threads=4&allocMbPerSec=512&chunkKb=64
- POST /gc/stop

Build:
  mvn -q -DskipTests package

Run:
  java -Xms256m -Xmx256m -jar target/java-netty-gc-thrash-0.1.0.jar --port 8083

Trigger:
  curl -s -XPOST "http://127.0.0.1:8083/gc/start?threads=4&allocMbPerSec=800" | jq

Stop:
  curl -s -XPOST http://127.0.0.1:8083/gc/stop | jq
