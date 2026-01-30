Deploy test guide (java demos + sre-agent)

Prereq
- Python deps: use venv in `sre-agent/.venv`
- Java demo jars: build under `sre-agent/example/*/target/*.jar`

0) Activate venv
  cd sre-agent
  source .venv/bin/activate

1) Build one demo
  cd sre-agent/example/<demo>
  mvn -q -DskipTests package

2) Run one demo on target host

CPU demo (8080):
  java -Xms256m -Xmx256m -jar target/java-netty-cpu-hotspot-0.1.0.jar --port 8080
  curl -s -XPOST "http://127.0.0.1:8080/burn/start?threads=8&intensity=100"

IO demo (8081):
  java -Xms256m -Xmx256m -jar target/java-netty-io-wait-load-0.1.0.jar --port 8081
  curl -s -XPOST "http://127.0.0.1:8081/io/start?threads=4&mbPerOp=128&fsync=true&dir=/tmp"

Mem pressure demo (8082):
  java -Xms256m -Xmx256m -jar target/java-netty-mem-pressure-0.1.0.jar --port 8082
  curl -s -XPOST "http://127.0.0.1:8082/mem/start?targetMb=800&chunkMb=4&intervalMs=10"

GC thrash demo (8083):
  java -Xms256m -Xmx256m -jar target/java-netty-gc-thrash-0.1.0.jar --port 8083
  curl -s -XPOST "http://127.0.0.1:8083/gc/start?threads=4&allocMbPerSec=800"

Deadlock demo (8084):
  java -Xms256m -Xmx256m -jar target/java-netty-deadlock-0.1.0.jar --port 8084
  curl -s -XPOST http://127.0.0.1:8084/deadlock/start

Threadpool starvation demo (8085):
  java -Xms256m -Xmx256m -jar target/java-netty-threadpool-starvation-0.1.0.jar --port 8085 --biz-threads 4
  curl -s -XPOST "http://127.0.0.1:8085/block/start?sleepMs=5000"
  for i in $(seq 1 50); do curl -s "http://127.0.0.1:8085/work?ms=10" >/dev/null & done

FD leak demo (8086):
  java -Xms256m -Xmx256m -jar target/java-netty-fd-leak-0.1.0.jar --port 8086
  curl -s -XPOST "http://127.0.0.1:8086/fd/start?openPerSec=50&max=512&dir=/tmp"

3) Identify pid (on the target)
  curl -s http://127.0.0.1:<port>/pid

4) Run sre-agent evidence collection
  cd sre-agent

  # If the demo runs on the same machine, use --exec-mode local.
  python -m src.cli.sre_agent_cli run \
    --host 127.0.0.1 \
    --service netty-demo \
    --pid <pid> \
    --exec-mode local \
    --window-minutes 10 \
    --output report/evidence.json

5) (Optional) Generate a report from evidence
  python -m src.cli.sre_agent_cli report \
    --evidence report/evidence.json \
    --schema schemas/report_schema.json \
    > report/report.json
