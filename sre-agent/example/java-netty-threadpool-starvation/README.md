Threadpool starvation demo (Netty only)

Endpoints:
- GET  /health
- GET  /pid
- GET  /status
- GET  /work?ms=50
- POST /block/start?sleepMs=3000
- POST /block/stop

Build:
  mvn -q -DskipTests package

Run:
  java -Xms256m -Xmx256m -jar target/java-netty-threadpool-starvation-0.1.0.jar --port 8085 --biz-threads 4

Trigger starvation (all /work handlers will sleep):
  curl -s -XPOST "http://127.0.0.1:8085/block/start?sleepMs=5000" | jq

Generate load:
  for i in $(seq 1 50); do curl -s "http://127.0.0.1:8085/work?ms=10" >/dev/null & done

Stop:
  curl -s -XPOST http://127.0.0.1:8085/block/stop | jq
