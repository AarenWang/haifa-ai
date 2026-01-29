Netty Java high-load demos for sre-agent

This folder contains two minimal Java HTTP servers (Netty only) used to create
repeatable "high load" situations for SRE diagnostics (CPU hot loops, IO wait).

Projects:
- java-netty-cpu-hotspot: CPU/RUNNABLE load (busy compute + controllable burners)
- java-netty-io-wait-load: IO wait / D-state style load (large writes + optional fsync)

Build (each project):
  mvn -q -DskipTests package

Run (example):
  java -jar target/<jar-name>.jar --port 8080
