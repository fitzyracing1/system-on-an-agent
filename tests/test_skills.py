from __future__ import annotations

import pytest

from soa.skills import Skill, SkillError, SkillLibrary, builtin_skills
from soa.types import Result


def test_register_list_get_and_run():
    library = SkillLibrary()
    library.register(Skill("greet", "Say hello.", lambda text="": f"hello {text}", ("text",)))
    assert library.has("Greet")
    assert library.names() == ["greet"]
    assert library.get("greet").description == "Say hello."
    result = library.run("greet", text="world")
    assert result.ok is True
    assert result.data == "hello world"
    assert len(library) == 1


def test_unknown_skill_raises():
    library = SkillLibrary()
    with pytest.raises(SkillError, match="unknown skill"):
        library.get("missing")


def test_duplicate_skill_requires_overwrite():
    library = SkillLibrary()
    skill = Skill("echo", "one", lambda: "one")
    library.register(skill)
    with pytest.raises(SkillError, match="already registered"):
        library.register(Skill("echo", "two", lambda: "two"))
    library.register(Skill("echo", "two", lambda: "two"), overwrite=True)
    assert library.get("echo").description == "two"


def test_empty_name_is_rejected():
    with pytest.raises(ValueError):
        SkillLibrary().register(Skill("  ", "empty", lambda: None))


def test_handler_may_return_a_result():
    library = SkillLibrary()
    library.register(Skill("ok", "already a result", lambda: Result(ok=True, data="yes")))
    assert library.run("ok").data == "yes"


def test_positional_text_fallback():
    library = SkillLibrary()
    library.register(Skill("shout", "upper", lambda text: text.upper(), ("text",)))
    assert library.run("shout", text="hey").data == "HEY"


def test_type_error_inside_a_handler_is_not_mistaken_for_a_signature():
    def broken(**kwargs):
        raise TypeError("handler bug")

    library = SkillLibrary()
    library.register(Skill("broken", "raises", broken))
    with pytest.raises(TypeError, match="handler bug"):
        library.run("broken", text="x")


def test_undeclared_kwargs_are_not_forwarded_to_a_narrow_handler():
    library = SkillLibrary()
    library.register(Skill("ping", "no arguments", lambda: "pong"))
    assert library.run("ping", text="ignored").data == "pong"


def test_builtin_skill_names():
    names = {skill.name for skill in builtin_skills()}
    assert names == {"echo", "remember", "recall", "read_file", "write_file"}
