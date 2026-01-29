java-netty-cpu-hotspot

Minimal Netty HTTP server that can generate high CPU / RUNNABLE load.

Build:
  mvn -q -DskipTests package

Run:
  java -Xms256m -Xmx256m -jar target/java-netty-cpu-hotspot-0.1.0.jar --port 8080

Endpoints:
  GET  /health
  GET  /pid
  GET  /status
  POST /burn/start?threads=8&intensity=100
  POST /burn/stop
  GET  /cpu?ms=3000

Quick test:
  curl -s http://127.0.0.1:8080/pid
  curl -s -XPOST "http://127.0.0.1:8080/burn/start?threads=8&intensity=100"
  curl -s http://127.0.0.1:8080/status
  curl -s -XPOST http://127.0.0.1:8080/burn/stop
