---
name: system-on-an-agent
description: Use the System on an Agent MCP tools to plan and run simple goals through a rule-based planner, long-term memory, a skill library, and local file and echo connectors.
---

# System on an Agent

## When to use

- You want a deterministic plan for a short goal before acting on it (`plan_goal`).
- You want to store or look up facts during a session (`memory_remember`, `memory_recall`).
- You want to read or write a file inside the server's file root, or run one named skill (`run_goal`, `run_skill`).

## Instructions

1. Call `list_skills` to see the skill names and their parameters.
2. Call `plan_goal` first when the goal has several parts. Goal forms the planner understands:
   `echo hello`, `remember <fact>`, `recall <query>`, `read <path>`, `write <text> to <path>`,
   `list skills`, `list connectors`. Join steps with `then`.
3. Call `run_goal` to execute the plan. Check `ok` and each step result; a run stops at the first failed step.
4. File paths are confined to the server's file root. Paths that escape it fail instead of touching other files.
5. Long-term memory lasts for the server process, or across restarts when the server was started with `--memory-file`.
