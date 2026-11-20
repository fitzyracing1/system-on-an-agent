from __future__ import annotations

from soa.planner import LLMProvider, Planner


class FakeLLM(LLMProvider):
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.prompts.append(prompt)
        return self.response


def test_echo_goal():
    plan = Planner().plan("echo hello from system on an agent")
    assert plan.source == "rules"
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.action == "connector.send"
    assert step.args["connector"] == "echo"
    assert step.args["payload"] == "hello from system on an agent"


def test_say_is_an_echo_alias():
    plan = Planner().plan('say "ping"')
    assert plan.steps[0].args["payload"] == "ping"


def test_remember_and_recall():
    remember = Planner().plan("remember the sky is blue")
    assert remember.steps[0].action == "memory.remember"
    assert remember.steps[0].args["fact"] == "the sky is blue"

    recall = Planner().plan("recall sky")
    assert recall.steps[0].action == "memory.recall"
    assert recall.steps[0].args["query"] == "sky"


def test_what_do_you_know_about_is_recall():
    plan = Planner().plan("what do you know about sky")
    assert plan.steps[0].action == "memory.recall"
    assert plan.steps[0].args["query"] == "sky"


def test_read_and_write_file():
    read = Planner().plan("read notes.txt")
    assert read.steps[0].action == "connector.call"
    assert read.steps[0].args["method"] == "read"
    assert read.steps[0].args["path"] == "notes.txt"

    write = Planner().plan("write hello to notes.txt")
    assert write.steps[0].args["method"] == "write"
    assert write.steps[0].args["path"] == "notes.txt"
    assert write.steps[0].args["content"] == "hello"

    colon = Planner().plan("write notes.txt: hello")
    assert colon.steps[0].args["path"] == "notes.txt"
    assert colon.steps[0].args["content"] == "hello"


def test_list_skills_and_connectors():
    skills = Planner().plan("list skills")
    assert skills.steps[0].action == "system.list_skills"
    connectors = Planner().plan("list connectors")
    assert connectors.steps[0].action == "system.list_connectors"


def test_then_splits_into_multiple_steps():
    plan = Planner().plan("echo hi then remember hi was said")
    assert len(plan.steps) == 2
    assert plan.steps[0].action == "connector.send"
    assert plan.steps[1].action == "memory.remember"
    assert plan.steps[1].args["fact"] == "hi was said"


def test_and_then_is_also_a_sequencer():
    plan = Planner().plan("echo one and then echo two")
    assert [s.args["payload"] for s in plan.steps] == ["one", "two"]


def test_run_skill_and_named_skill():
    run = Planner().plan("run echo hello", skill_names=["echo"])
    assert run.steps[0].action == "skill.run"
    assert run.steps[0].args["name"] == "echo"
    assert run.steps[0].args["text"] == "hello"

    named = Planner().plan("echo hello", skill_names=["echo"])
    # "echo hello" matches the echo verb first, which is intended.
    assert named.steps[0].action == "connector.send"

    custom = Planner().plan("greet world", skill_names=["greet"])
    assert custom.steps[0].action == "skill.run"
    assert custom.steps[0].args["name"] == "greet"
    assert custom.steps[0].args["text"] == "world"


def test_empty_goal_is_noop():
    plan = Planner().plan("   ")
    assert plan.steps[0].action == "system.noop"


def test_unknown_goal_falls_back_to_echo():
    plan = Planner().plan("do something mysterious")
    assert plan.steps[0].action == "connector.send"
    assert plan.steps[0].args["payload"] == "do something mysterious"


def test_llm_plan_is_used_when_valid():
    llm = FakeLLM(
        '[{"action": "memory.remember", "args": {"fact": "ok"}, "description": "store"}]'
    )
    plan = Planner(llm=llm).plan("remember ok")
    assert plan.source == "llm"
    assert plan.steps[0].action == "memory.remember"
    assert plan.steps[0].args["fact"] == "ok"
    assert llm.prompts


def test_invalid_llm_response_falls_back_to_rules():
    llm = FakeLLM("not json at all")
    plan = Planner(llm=llm).plan("echo hello")
    assert plan.source == "rules"
    assert plan.steps[0].args["payload"] == "hello"


def test_empty_or_malformed_llm_list_falls_back():
    assert Planner(llm=FakeLLM("[]")).plan("echo x").source == "rules"
    assert Planner(llm=FakeLLM('[{"nope": 1}]')).plan("echo x").source == "rules"
    assert Planner(llm=FakeLLM('{"action": "x"}')).plan("echo x").source == "rules"


def test_describe_uses_step_descriptions():
    planner = Planner()
    plan = planner.plan("echo hello")
    assert planner.describe(plan) == [plan.steps[0].description]


class RaisingLLM(LLMProvider):
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        raise ConnectionError("provider down")


def test_raising_provider_falls_back_to_rules():
    plan = Planner(llm=RaisingLLM()).plan("echo hello")
    assert plan.source == "rules"
    assert plan.steps[0].args["payload"] == "hello"


def test_unknown_action_from_the_model_falls_back_to_rules():
    llm = FakeLLM('[{"action": "shell.exec", "args": {"cmd": "rm -rf /"}}]')
    plan = Planner(llm=llm).plan("echo hello")
    assert plan.source == "rules"
    assert plan.steps[0].args["payload"] == "hello"
