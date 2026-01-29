Deploy test guide (java demos + sre-agent)

Prereq
- Python deps: use venv in `sre-agent/.venv`
- Java demo jars: build under `sre-agent/example/*/target/*.jar`

1) Activate venv
  cd sre-agent
  source .venv/bin/activate
  python -c "import claude_agent_sdk; print('claude_agent_sdk ok')"

2) Run one demo on target host

CPU demo:
  java -Xms256m -Xmx256m -jar java-netty-cpu-hotspot-0.1.0.jar --port 8080
  curl -XPOST "http://127.0.0.1:8080/burn/start?threads=8&intensity=100"

IO demo:
  java -Xms256m -Xmx256m -jar java-netty-io-wait-load-0.1.0.jar --port 8081
  curl -XPOST "http://127.0.0.1:8081/io/start?threads=4&mbPerOp=128&fsync=true&dir=/tmp"

3) Run sre-agent collection
  python diag_load_agent.py --host <host> --service <service>
