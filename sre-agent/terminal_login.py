import getpass
import os
import sys


def _prompt(prompt: str, default: str = "") -> str:
    if default:
        v = input(f"{prompt} [{default}]: ").strip()
        return v or default
    return input(f"{prompt}: ").strip()


def main() -> int:
    host = _prompt("Linux host (IP or hostname)")
    if not host:
        print("host is required", file=sys.stderr)
        return 2

    user = _prompt("Linux user", default="root")
    port = _prompt("SSH port", default="22")
    try:
        int(port)
    except ValueError:
        print("invalid port", file=sys.stderr)
        return 2

    password = getpass.getpass("Linux password (input hidden): ")
    if not password:
        print("password is required", file=sys.stderr)
        return 2

    # Connectivity check via paramiko (same as MCP will use when password is set)
    try:
        import paramiko  # type: ignore
    except Exception as e:
        print(f"paramiko not installed: {e}", file=sys.stderr)
        print("Run: source .venv/bin/activate && pip install -r requirements.txt", file=sys.stderr)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(hostname=host, port=int(port), username=user, password=password, timeout=10)
        _, stdout, stderr = client.exec_command("uname -a && uptime", timeout=10)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if out:
            print(out.strip())
        if err:
            print("[stderr]\n" + err.strip(), file=sys.stderr)
    except Exception as e:
        print(f"SSH login failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        try:
            client.close()
        except Exception:
            pass

    print("\nNote: this script cannot export env vars into your current shell.")
    print("Run diag with inline env vars (recommended):")
    print(f"  SRE_SSH_USER={user} SRE_SSH_PORT={port} SRE_SSH_PASSWORD='<your-password>' \\")
    print(f"    python diag_load_agent.py --host {host} --service <systemd-service-name>")
    print("\nOr export them in your current shell:")
    print(f"  export SRE_SSH_USER={user}")
    print(f"  export SRE_SSH_PORT={port}")
    print("  export SRE_SSH_PASSWORD='<your-password>'")
    print(f"  python diag_load_agent.py --host {host} --service <systemd-service-name>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
