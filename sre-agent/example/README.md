Netty Java demos for sre-agent

This folder contains small Java HTTP services (Netty only). Each one provides a
repeatable failure mode you can trigger with curl, then point `sre-agent` at the
process for evidence collection.

All demos expose common endpoints:
- GET  /health
- GET  /pid
- GET  /status

Projects (recommended ports):
- java-netty-cpu-hotspot (8080): CPU/RUNNABLE load (busy compute + controllable burners)
- java-netty-io-wait-load (8081): IO wait style load (large writes + optional fsync)
- java-netty-mem-pressure (8082): heap retention / memory pressure
- java-netty-gc-thrash (8083): allocation thrash / frequent GC
- java-netty-deadlock (8084): JVM-level deadlock
- java-netty-threadpool-starvation (8085): blocked biz threads / tail latency
- java-netty-fd-leak (8086): file descriptor leak (capped) + stop to close

Build (each project):
  mvn -q -DskipTests package

Run (example):
  java -Xms256m -Xmx256m -jar target/<jar-name>.jar --port 8080

Quick smoke (example):
  curl -s http://127.0.0.1:8080/health
  curl -s http://127.0.0.1:8080/pid

Next:
- Use `sre-agent/example/DEPLOY_TEST.md` for a step-by-step runbook that includes
  running `python -m src.cli.sre_agent_cli run ...` against the demo.
