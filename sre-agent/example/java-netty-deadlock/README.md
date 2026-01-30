Deadlock demo (Netty only)

Endpoints:
- GET  /health
- GET  /pid
- GET  /status
- POST /deadlock/start

Build:
  mvn -q -DskipTests package

Run:
  java -Xms256m -Xmx256m -jar target/java-netty-deadlock-0.1.0.jar --port 8084

Trigger a JVM-level deadlock:
  curl -s -XPOST http://127.0.0.1:8084/deadlock/start | jq

Then use jstack / jcmd Thread.print to confirm.

Notes:
- Deadlocked threads cannot be “stopped” safely; this demo caps how many deadlocks can be created.
