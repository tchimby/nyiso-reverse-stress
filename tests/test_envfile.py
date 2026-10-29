from revstress import envfile


def test_parse_env_line_variants():
    assert envfile.parse_env_line("ANTHROPIC_API_KEY=abc") == ("ANTHROPIC_API_KEY", "abc")
    assert envfile.parse_env_line('export ANTHROPIC_API_KEY="abc"') == ("ANTHROPIC_API_KEY", "abc")
    assert envfile.parse_env_line("ANTHROPIC_API_KEY = 'abc' ") == ("ANTHROPIC_API_KEY", "abc")
    assert envfile.parse_env_line("# comment") is None
    assert envfile.parse_env_line("") is None
    assert envfile.parse_env_line("no_equals") is None


def test_load_sets_only_when_unset_and_never_returns_the_value(tmp_path):
    f = tmp_path / ".env"
    f.write_text("OTHER=1\nANTHROPIC_API_KEY=sk-ant-test\n", encoding="utf-8")
    env: dict[str, str] = {}
    assert envfile.load_api_key(f, env) is True
    assert env == {"ANTHROPIC_API_KEY": "sk-ant-test"}
    assert "OTHER" not in env
    env2 = {"ANTHROPIC_API_KEY": "from-environment"}
    assert envfile.load_api_key(f, env2) is True
    assert env2["ANTHROPIC_API_KEY"] == "from-environment"


def test_missing_or_keyless_file(tmp_path):
    assert envfile.load_api_key(tmp_path / "absent.env", {}) is False
    f = tmp_path / ".env"
    f.write_text("OTHER=1\n", encoding="utf-8")
    assert envfile.load_api_key(f, {}) is False


def test_key_status_is_masked():
    status = envfile.key_status({"ANTHROPIC_API_KEY": "sk-ant-secretvalue"})
    assert status == {"present": True, "length": 18, "prefix_ok": True}
    assert "secretvalue" not in repr(status)
    assert envfile.key_status({}) == {"present": False, "length": 0, "prefix_ok": False}
