from dev_administration.ssh_utils import add_ssh_key, remove_ssh_key


def test_add_ssh_key(tmp_path):
    path = str(tmp_path / "authorized_keys")
    open(path, "w").close()
    add_ssh_key("juan", "ssh-ed25519 AAAA... juan@laptop", path)
    content = open(path).read()
    assert "docker exec -it hermes-juan bash" in content
    assert "ssh-ed25519 AAAA... juan@laptop" in content


def test_add_ssh_key_overwrites_existing(tmp_path):
    path = str(tmp_path / "authorized_keys")
    open(path, "w").close()
    add_ssh_key("juan", "ssh-ed25519 AAAA... old", path)
    add_ssh_key("juan", "ssh-ed25519 AAAA... new", path)
    content = open(path).read()
    assert "old" not in content
    assert "new" in content
    assert content.count("hermes-juan") == 1


def test_remove_ssh_key(tmp_path):
    path = str(tmp_path / "authorized_keys")
    open(path, "w").close()
    add_ssh_key("juan", "ssh-ed25519 AAAA... juan@laptop", path)
    add_ssh_key("ethan", "ssh-ed25519 BBBB... ethan@desktop", path)
    remove_ssh_key("juan", path)
    content = open(path).read()
    assert "juan" not in content
    assert "ethan" in content
