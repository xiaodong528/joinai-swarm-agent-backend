from __future__ import annotations

from e2b import Sandbox


def main() -> None:
    sandbox = Sandbox.create(timeout=120)
    try:
        print(f"sandbox_id={sandbox.sandbox_id}")
        result = sandbox.commands.run("echo hello && pwd && printenv HOME", timeout=30)
        print("command_stdout_start")
        print(result.stdout.strip())
        print("command_stdout_end")
        print("command_stderr_start")
        print((result.stderr or "").strip())
        print("command_stderr_end")

        print(f"files_type={type(sandbox.files)!r}")
        print(f"commands_type={type(sandbox.commands)!r}")

        sandbox.files.write("/tmp/opencode-e2b-smoke.txt", "ok\n")
        read_result = sandbox.commands.run("cat /tmp/opencode-e2b-smoke.txt", timeout=30)
        print(f"file_readback={read_result.stdout.strip()}")
    finally:
        sandbox.kill()
        print("sandbox_killed=true")


if __name__ == "__main__":
    main()

