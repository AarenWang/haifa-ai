java-netty-io-wait-load

Minimal Netty HTTP server that can generate IO wait style load (large writes + optional fsync).

Build:
  mvn -q -DskipTests package

Run:
  java -Xms256m -Xmx256m -jar target/java-netty-io-wait-load-0.1.0.jar --port 8081

Endpoints:
  GET  /health
  GET  /pid
  GET  /status
  POST /io/start?threads=4&mbPerOp=64&fsync=true&dir=/tmp
  POST /io/stop
  GET  /io/once?mb=256&fsync=true&dir=/tmp

Quick test:
  curl -s http://127.0.0.1:8081/pid
  curl -s -XPOST "http://127.0.0.1:8081/io/start?threads=4&mbPerOp=128&fsync=true&dir=/tmp"
  curl -s http://127.0.0.1:8081/status
  curl -s -XPOST http://127.0.0.1:8081/io/stop
