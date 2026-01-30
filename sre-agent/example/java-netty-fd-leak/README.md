FD leak demo (Netty only)

Endpoints:
- GET  /health
- GET  /pid
- GET  /status
- POST /fd/start?openPerSec=20&max=256&dir=/tmp
- POST /fd/stop

Build:
  mvn -q -DskipTests package

Run:
  java -Xms256m -Xmx256m -jar target/java-netty-fd-leak-0.1.0.jar --port 8086

Trigger:
  curl -s -XPOST "http://127.0.0.1:8086/fd/start?openPerSec=50&max=512" | jq

Stop (closes all open fds):
  curl -s -XPOST http://127.0.0.1:8086/fd/stop | jq

Notes:
- This demo has a max cap to reduce risk of affecting the host.
