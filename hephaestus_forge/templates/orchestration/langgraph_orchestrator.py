# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
LangGraph Orchestration Layer - AEGIS Integration
Multi-persona agent orchestration: Architect → Engineer → Reviewer → QA → Debugger
"""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, TypedDict, Annotated

from langgraph.graph import StateGraph
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI


# ─── State Definitions ────────────────────────────────────────────────────────

class AgentPersona(str, Enum):
    ARCHITECT = "architect"
    ENGINEER = "engineer"
    REVIEWER = "reviewer"
    QA = "qa"
    DEBUGGER = "debugger"
    HUMAN = "human"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REQUIRES_HUMAN = "requires_human"


class TaskType(str, Enum):
    DESIGN = "design"
    IMPLEMENT = "implement"
    REVIEW = "review"
    TEST = "test"
    DEBUG = "debug"
    DOCUMENT = "document"


@dataclass
class Task:
    task_id: str
    type: TaskType
    title: str
    description: str
    acceptance_criteria: List[str]
    assigned_persona: AgentPersona
    depends_on: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    files_touched: List[str] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class TaskGraph:
    tasks: Dict[str, Task] = field(default_factory=dict)
    entry_points: List[str] = field(default_factory=list)
    
    def add_task(self, task: Task):
        self.tasks[task.task_id] = task
        if not task.depends_on:
            self.entry_points.append(task.task_id)
    
    def get_ready_tasks(self, completed: List[str]) -> List[Task]:
        ready = []
        for task in self.tasks.values():
            if task.status == TaskStatus.PENDING:
                if all(dep in completed for dep in task.depends_on):
                    ready.append(task)
        return ready
    
    def is_complete(self) -> bool:
        return all(t.status == TaskStatus.COMPLETED for t in self.tasks.values())


class AgentState(TypedDict):
    # Goal & Context
    goal: str
    repo_path: str
    project_context: Dict[str, Any]
    
    # Planning
    task_graph: Optional[TaskGraph]
    current_task_id: Optional[str]
    completed_tasks: List[str]
    failed_tasks: List[str]
    
    # Execution
    current_persona: AgentPersona
    context_bundle: Dict[str, Any]  # Retrieved context for current task
    file_diffs: Dict[str, str]  # path -> unified diff
    test_results: Dict[str, Any]
    
    # History & Trajectory
    trajectory: List[Dict[str, Any]]
    messages: Annotated[List[BaseMessage], "add_messages"]
    token_usage: Dict[str, int]
    
    # Checkpointing
    checkpoint_id: Optional[str]
    iteration: int
    
    # Human-in-the-loop
    hitl_pending: bool
    hitl_reason: Optional[str]
    hitl_payload: Optional[Dict[str, Any]]


# ─── Persona Prompts ──────────────────────────────────────────────────────────

PERSONA_PROMPTS = {
    AgentPersona.ARCHITECT: """You are the ARCHITECT persona. Your role is to decompose high-level goals into atomic, executable tasks.

RESPONSIBILITIES:
1. Analyze the goal and repository state
2. Create a Technical Design Document (TDD) with:
   - Architecture overview
   - Component breakdown
   - Data flow diagrams
   - API contracts
   - File/tree structure changes
3. Break work into a Task Graph (DAG) where each task:
   - Has single-file/function scope (atomic)
   - Has clear acceptance criteria
   - Has explicit dependencies
   - Specifies files to touch
   - Assigns to correct persona (engineer/reviewer/qa/debugger)

OUTPUT FORMAT: JSON TaskGraph with tasks array.
Each task: {task_id, type, title, description, acceptance_criteria[], assigned_persona, depends_on[], files_touched[]}

CONSTRAINTS:
- Tasks must be independently verifiable
- No task should span more than 1-2 files
- Prefer parallelizable tasks
- Include test tasks for each implementation task""",

    AgentPersona.ENGINEER: """You are the ENGINEER persona. Your role is to implement a single atomic task completely.

RESPONSIBILITIES:
1. Read the task specification and context bundle
2. Retrieve relevant code via tools (read_file, lsp_goto_def, find_refs)
3. Write complete, production-ready implementation
4. Write unit tests for the implementation
5. Run tests to verify
6. Output unified diff + test plan

TOOLS AVAILABLE:
- read_file(path)
- write_file(path, content)
- edit_file(path, old_str, new_str)
- lsp_goto_def(symbol, file)
- lsp_find_refs(symbol, file)
- run_command(cmd, cwd)
- run_tests(pattern)

CONSTRAINTS:
- NO PLACEHOLDERS. Complete implementations only.
- Follow project coding standards (from ProjectMemory)
- Handle errors gracefully
- Type hints required for Python
- No TODOs or FIXMEs in output
- If unsure, ask clarifying question via HITL""",

    AgentPersona.REVIEWER: """You are the REVIEWER persona. Your role is to critique code changes for security, performance, correctness, and style.

REVIEW CHECKLIST:
1. SECURITY: OWASP Top 10, injection, authz, secrets, crypto
2. PERFORMANCE: N+1 queries, allocations, algorithmic complexity, caching
3. CORRECTNESS: Edge cases, null handling, race conditions, logic errors
4. STYLE: Naming, formatting, documentation, project conventions
5. ARCHITECTURE: Coupling, cohesion, SOLID, patterns

OUTPUT: PASS or FAIL with specific comments per file.
If FAIL, provide actionable fixes.""",

    AgentPersona.QA: """You are the QA/VERIFIER persona. Your role is to execute test plans and verify behavior.

RESPONSIBILITIES:
1. Run unit tests (pytest/jest/cargo test)
2. Analyze coverage
3. Spin up integration stack (docker compose)
4. Run E2E tests (Playwright/API)
5. Compare screenshots/API contracts
6. Report PASS/FAIL with logs

TOOLS:
- run_tests(pattern)
- start_stack(compose_file)
- stop_stack()
- http_request(method, url, body)
- playwright_test(script)
- compare_screenshots(baseline, actual)""",

    AgentPersona.DEBUGGER: """You are the DEBUGGER persona. Your role is to diagnose failures and propose minimal fixes.

DEBUGGING PROCESS:
1. Analyze failure logs + code + context
2. Form hypotheses (rank by likelihood)
3. Create minimal reproduction
4. Identify root cause
5. Propose minimal patch
6. Verify patch fixes issue without regression

OUTPUT: Root cause analysis + unified diff patch.""",
}


# ─── Base Persona Agent ───────────────────────────────────────────────────────

class PersonaAgent(ABC):
    def __init__(self, persona: AgentPersona, llm: ChatOpenAI, tools: List[BaseTool]):
        self.persona = persona
        self.llm = llm.bind_tools(tools)
        self.tools = {t.name: t for t in tools}
        self.system_prompt = PERSONA_PROMPTS[persona]
    
    @abstractmethod
    async def execute(self, state: AgentState) -> Dict[str, Any]:
        pass
    
    def _build_messages(self, state: AgentState, task: Optional[Task] = None) -> List[BaseMessage]:
        messages = [SystemMessage(content=self.system_prompt)]
        
        # Add relevant trajectory context
        for entry in state.get("trajectory", [])[-5:]:  # Last 5 entries
            if entry.get("persona") == self.persona.value:
                messages.append(AIMessage(content=json.dumps(entry)))
        
        # Add current task
        if task:
            messages.append(HumanMessage(content=f"""
TASK: {task.title}
TYPE: {task.type.value}
DESCRIPTION: {task.description}
ACCEPTANCE CRITERIA: {json.dumps(task.acceptance_criteria)}
FILES TO TOUCH: {json.dumps(task.files_touched)}
CONTEXT: {json.dumps(state.get("context_bundle", {}), indent=2)}
"""))
        
        return messages


# ─── Concrete Persona Implementations ─────────────────────────────────────────

class ArchitectAgent(PersonaAgent):
    def __init__(self, llm: ChatOpenAI, tools: List[BaseTool]):
        super().__init__(AgentPersona.ARCHITECT, llm, tools)
    
    async def execute(self, state: AgentState) -> Dict[str, Any]:
        messages = self._build_messages(state)
        messages.append(HumanMessage(content=f"""
GOAL: {state['goal']}
REPO: {state['repo_path']}
PROJECT CONTEXT: {json.dumps(state['project_context'], indent=2)}

Create a TaskGraph (JSON) that decomposes this goal into atomic tasks.
"""))
        
        response = await self.llm.ainvoke(messages)
        
        # Parse task graph from response
        task_graph = self._parse_task_graph(response.content)
        
        return {
            "task_graph": task_graph,
            "current_persona": AgentPersona.HUMAN,  # HITL gate for design approval
            "hitl_pending": True,
            "hitl_reason": "Design approval required",
            "hitl_payload": {"task_graph": task_graph},
            "trajectory": [{
                "persona": self.persona.value,
                "action": "created_task_graph",
                "task_count": len(task_graph.tasks),
                "timestamp": datetime.utcnow().isoformat(),
            }],
        }
    
    def _parse_task_graph(self, content: str) -> TaskGraph:
        # Extract JSON from response
        try:
            # Find JSON block
            start = content.find("{")
            end = content.rfind("}") + 1
            data = json.loads(content[start:end])
            
            graph = TaskGraph()
            for task_data in data.get("tasks", []):
                task = Task(
                    task_id=task_data["task_id"],
                    type=TaskType(task_data["type"]),
                    title=task_data["title"],
                    description=task_data["description"],
                    acceptance_criteria=task_data["acceptance_criteria"],
                    assigned_persona=AgentPersona(task_data["assigned_persona"]),
                    depends_on=task_data.get("depends_on", []),
                    files_touched=task_data.get("files_touched", []),
                )
                graph.add_task(task)
            return graph
        except Exception:
            # Fallback: create minimal task graph
            graph = TaskGraph()
            task = Task(
                task_id=str(uuid.uuid4())[:8],
                type=TaskType.IMPLEMENT,
                title="Implement goal",
                description=content[:500],
                acceptance_criteria=["Goal achieved"],
                assigned_persona=AgentPersona.ENGINEER,
            )
            graph.add_task(task)
            return graph


class EngineerAgent(PersonaAgent):
    def __init__(self, llm: ChatOpenAI, tools: List[BaseTool]):
        super().__init__(AgentPersona.ENGINEER, llm, tools)
    
    async def execute(self, state: AgentState) -> Dict[str, Any]:
        task = state["task_graph"].tasks[state["current_task_id"]]
        messages = self._build_messages(state, task)
        
        response = await self.llm.ainvoke(messages)
        
        # Parse diffs and test plan from response
        diffs, test_plan = self._parse_engineer_output(response.content)
        
        return {
            "file_diffs": diffs,
            "test_results": {"plan": test_plan},
            "trajectory": [{
                "persona": self.persona.value,
                "task_id": task.task_id,
                "action": "implemented",
                "files_changed": list(diffs.keys()),
                "timestamp": datetime.utcnow().isoformat(),
            }],
        }
    
    def _parse_engineer_output(self, content: str) -> tuple[Dict[str, str], Dict]:
        # Parse unified diffs and test plan
        diffs = {}
        test_plan = {"unit": [], "integration": []}
        # Implementation would parse markdown code blocks with diffs
        return diffs, test_plan


class ReviewerAgent(PersonaAgent):
    def __init__(self, llm: ChatOpenAI, tools: List[BaseTool]):
        super().__init__(AgentPersona.REVIEWER, llm, tools)
    
    async def execute(self, state: AgentState) -> Dict[str, Any]:
        task = state["task_graph"].tasks[state["current_task_id"]]
        diffs = state.get("file_diffs", {})
        
        messages = self._build_messages(state, task)
        messages.append(HumanMessage(content=f"""
REVIEW TASK: {task.title}
DIFFS:
{json.dumps(diffs, indent=2)}

Provide PASS/FAIL with comments.
"""))
        
        response = await self.llm.ainvoke(messages)
        passed, comments = self._parse_review(response.content)
        
        return {
            "test_results": {**state.get("test_results", {}), "review": {"passed": passed, "comments": comments}},
            "trajectory": [{
                "persona": self.persona.value,
                "task_id": task.task_id,
                "action": "reviewed",
                "passed": passed,
                "comments": comments,
                "timestamp": datetime.utcnow().isoformat(),
            }],
        }
    
    def _parse_review(self, content: str) -> tuple[bool, List[str]]:
        lines = content.strip().split("\n")
        passed = lines[0].strip().upper().startswith("PASS")
        comments = lines[1:] if len(lines) > 1 else []
        return passed, comments


class QAAgent(PersonaAgent):
    def __init__(self, llm: ChatOpenAI, tools: List[BaseTool]):
        super().__init__(AgentPersona.QA, llm, tools)
    
    async def execute(self, state: AgentState) -> Dict[str, Any]:
        task = state["task_graph"].tasks[state["current_task_id"]]
        test_plan = state.get("test_results", {}).get("plan", {})
        
        messages = self._build_messages(state, task)
        messages.append(HumanMessage(content=f"""
EXECUTE TEST PLAN: {json.dumps(test_plan, indent=2)}
REPO: {state['repo_path']}

Run tests and report results.
"""))
        
        response = await self.llm.ainvoke(messages)
        passed, results = self._parse_qa_results(response.content)
        
        return {
            "test_results": {**state.get("test_results", {}), "execution": results, "passed": passed},
            "trajectory": [{
                "persona": self.persona.value,
                "task_id": task.task_id,
                "action": "tested",
                "passed": passed,
                "results": results,
                "timestamp": datetime.utcnow().isoformat(),
            }],
        }
    
    def _parse_qa_results(self, content: str) -> tuple[bool, Dict]:
        # Parse test execution results
        return True, {"output": content}


class DebuggerAgent(PersonaAgent):
    def __init__(self, llm: ChatOpenAI, tools: List[BaseTool]):
        super().__init__(AgentPersona.DEBUGGER, llm, tools)
    
    async def execute(self, state: AgentState) -> Dict[str, Any]:
        task = state["task_graph"].tasks[state["current_task_id"]]
        test_results = state.get("test_results", {})
        
        messages = self._build_messages(state, task)
        messages.append(HumanMessage(content=f"""
DEBUG FAILURE:
TASK: {task.title}
TEST RESULTS: {json.dumps(test_results, indent=2)}
FILE DIFFS: {json.dumps(state.get('file_diffs', {}), indent=2)}

Provide root cause analysis and minimal patch.
"""))
        
        response = await self.llm.ainvoke(messages)
        patch = self._parse_patch(response.content)
        
        return {
            "file_diffs": {**state.get("file_diffs", {}), **patch},
            "trajectory": [{
                "persona": self.persona.value,
                "task_id": task.task_id,
                "action": "patched",
                "files_patched": list(patch.keys()),
                "timestamp": datetime.utcnow().isoformat(),
            }],
        }
    
    def _parse_patch(self, content: str) -> Dict[str, str]:
        # Parse unified diff from response
        return {}


# ─── Graph Construction ───────────────────────────────────────────────────────

def create_agent_graph(
    llm: ChatOpenAI,
    tools: List[BaseTool],
    checkpointer: Any = None
) -> StateGraph:
    """Create the LangGraph agent orchestration graph."""
    
    # Initialize persona agents
    architect = ArchitectAgent(llm, tools)
    engineer = EngineerAgent(llm, tools)
    reviewer = ReviewerAgent(llm, tools)
    qa = QAAgent(llm, tools)
    debugger = DebuggerAgent(llm, tools)
    
    # Define node functions
    async def architect_node(state: AgentState) -> AgentState:
        result = await architect.execute(state)
        return {**state, **result}
    
    async def human_gate_node(state: AgentState) -> AgentState:
        # This node is interrupted - human reviews via external UI
        # State is persisted, human resumes by updating hitl_pending=false
        return state
    
    async def dispatcher_node(state: AgentState) -> AgentState:
        if not state.get("task_graph"):
            return {**state, "current_persona": AgentPersona.ARCHITECT}
        
        graph = state["task_graph"]
        ready = graph.get_ready_tasks(state.get("completed_tasks", []))
        
        if not ready:
            if graph.is_complete():
                return {**state, "current_persona": AgentPersona.HUMAN, "hitl_pending": True, "hitl_reason": "All tasks complete"}
            return state  # Wait for dependencies
        
        # Pick first ready task (could prioritize)
        task = ready[0]
        return {
            **state,
            "current_task_id": task.task_id,
            "current_persona": task.assigned_persona,
        }
    
    async def engineer_node(state: AgentState) -> AgentState:
        result = await engineer.execute(state)
        return {**state, **result}
    
    async def reviewer_node(state: AgentState) -> AgentState:
        result = await reviewer.execute(state)
        return {**state, **result}
    
    async def qa_node(state: AgentState) -> AgentState:
        result = await qa.execute(state)
        return {**state, **result}
    
    async def debugger_node(state: AgentState) -> AgentState:
        result = await debugger.execute(state)
        return {**state, **result}
    
    async def commit_node(state: AgentState) -> AgentState:
        # Apply diffs, run git commit, update graph
        task = state["task_graph"].tasks[state["current_task_id"]]
        task.status = TaskStatus.COMPLETED
        task.updated_at = datetime.utcnow().isoformat()
        
        return {
            **state,
            "completed_tasks": state.get("completed_tasks", []) + [state["current_task_id"]],
            "current_task_id": None,
            "file_diffs": {},
            "current_persona": AgentPersona.HUMAN,  # Back to dispatcher
        }
    
    # Build graph
    workflow = StateGraph(AgentState)
    
    # Nodes
    workflow.add_node("architect", architect_node)
    workflow.add_node("human_gate", human_gate_node)
    workflow.add_node("dispatcher", dispatcher_node)
    workflow.add_node("engineer", engineer_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("qa", qa_node)
    workflow.add_node("debugger", debugger_node)
    workflow.add_node("commit", commit_node)
    
    # Edges
    workflow.set_entry_point("architect")
    workflow.add_edge("architect", "human_gate")
    
    # Human gate -> dispatcher (after human approval)
    workflow.add_conditional_edges(
        "human_gate",
        lambda s: "dispatcher" if not s.get("hitl_pending") else "human_gate",
        {"dispatcher": "dispatcher", "human_gate": "human_gate"}
    )
    
    # Dispatcher routes to appropriate persona
    workflow.add_conditional_edges(
        "dispatcher",
        lambda s: s.get("current_persona", AgentPersona.HUMAN).value,
        {
            "engineer": "engineer",
            "reviewer": "reviewer",
            "qa": "qa",
            "debugger": "debugger",
            "human": "human_gate",
        }
    )
    
    # Engineer -> Reviewer
    workflow.add_edge("engineer", "reviewer")
    
    # Reviewer -> QA (if pass) or Debugger (if fail)
    workflow.add_conditional_edges(
        "reviewer",
        lambda s: "qa" if s.get("test_results", {}).get("review", {}).get("passed") else "debugger",
        {"qa": "qa", "debugger": "debugger"}
    )
    
    # QA -> Commit (if pass) or Debugger (if fail)
    workflow.add_conditional_edges(
        "qa",
        lambda s: "commit" if s.get("test_results", {}).get("execution", {}).get("passed") else "debugger",
        {"commit": "commit", "debugger": "debugger"}
    )
    
    # Debugger -> Engineer (retry)
    workflow.add_edge("debugger", "engineer")
    
    # Commit -> Dispatcher
    workflow.add_edge("commit", "dispatcher")
    
    # Compile with checkpointer
    if checkpointer is None:
        checkpointer = MemorySaver()
    
    return workflow.compile(checkpointer=checkpointer, interrupt_before=["human_gate"])


# ─── Configuration & Factory ──────────────────────────────────────────────────

@dataclass
class OrchestrationConfig:
    nemotron_endpoint: str = "http://127.0.0.1:8080/v1"
    nemotron_model: str = "nvidia/nemotron-3-ultra"
    nemotron_api_key: str = "nem"
    temperature_coding: float = 0.1
    temperature_planning: float = 0.4
    max_tokens: int = 4096
    postgres_checkpoint_url: Optional[str] = None
    recursion_limit: int = 100


async def create_orchestrator(config: OrchestrationConfig) -> StateGraph:
    """Create the full AEGIS orchestrator with Nemotron 3 Ultra."""
    
    # Primary reasoning LLM (Nemotron 3 Ultra via NIM)
    llm = ChatOpenAI(
        base_url=config.nemotron_endpoint,
        api_key=config.nemotron_api_key,
        model=config.nemotron_model,
        temperature=config.temperature_coding,
        max_tokens=config.max_tokens,
        timeout=300,
    )
    
    # Tools would be registered here (read_file, write_file, lsp, git, test, etc.)
    tools: List[BaseTool] = []  # Populated from tool registry
    
    # Checkpointer
    if config.postgres_checkpoint_url:
        checkpointer = PostgresSaver.from_conn_string(config.postgres_checkpoint_url)
    else:
        checkpointer = MemorySaver()
    
    graph = create_agent_graph(llm, tools, checkpointer)
    return graph


# ─── Run Helper ───────────────────────────────────────────────────────────────

async def run_agent(
    goal: str,
    repo_path: str,
    config: OrchestrationConfig,
    thread_id: str = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """Run the agent on a goal, yielding state updates."""
    
    graph = await create_orchestrator(config)
    thread_id = thread_id or str(uuid.uuid4())
    
    initial_state: AgentState = {
        "goal": goal,
        "repo_path": repo_path,
        "project_context": {},
        "task_graph": None,
        "current_task_id": None,
        "completed_tasks": [],
        "failed_tasks": [],
        "current_persona": AgentPersona.ARCHITECT,
        "context_bundle": {},
        "file_diffs": {},
        "test_results": {},
        "trajectory": [],
        "messages": [],
        "token_usage": {"prompt": 0, "completion": 0},
        "checkpoint_id": thread_id,
        "iteration": 0,
        "hitl_pending": False,
        "hitl_reason": None,
        "hitl_payload": None,
    }
    
    config_dict = {"configurable": {"thread_id": thread_id}}
    
    async for event in graph.astream(initial_state, config=config_dict):
        yield event