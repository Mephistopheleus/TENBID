"""NOVA entrypoint.

Main starts the supervisor only. Trading decisions must live in dedicated modules.
"""

from nova.supervisor.system_supervisor import SystemSupervisor


def main() -> None:
    supervisor = SystemSupervisor()
    supervisor.run()


if __name__ == "__main__":
    main()

