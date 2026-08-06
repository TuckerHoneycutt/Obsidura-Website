from __future__ import annotations

from pathlib import Path


def add_ssh_key(username: str, ssh_key: str, authorized_keys_path: str) -> None:
    """Add or overwrite an SSH forced-command entry for a developer.
    Removes any existing entry for this username, then appends the new one.
    """
    remove_ssh_key(username, authorized_keys_path)
    entry = (
        f'command="docker exec -it hermes-{username} bash",'
        f'no-port-forwarding,no-X11-forwarding {ssh_key}\n'
    )
    with open(authorized_keys_path, "a") as f:
        f.write(entry)


def remove_ssh_key(username: str, authorized_keys_path: str) -> None:
    """Remove all authorized_keys entries matching hermes-<username>."""
    path = Path(authorized_keys_path)
    if not path.exists():
        return
    lines = path.read_text().splitlines()
    marker = f"hermes-{username}"
    kept = [line for line in lines if marker not in line]
    path.write_text("\n".join(kept) + ("\n" if kept else ""))
