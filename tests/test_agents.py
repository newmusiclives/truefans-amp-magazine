"""Tests for AI agent task system."""
import pytest


def test_create_agent(repo):
    """Test creating an agent record."""
    agent_id = repo.create_agent("writer", "Test Writer", persona="Test persona")
    assert agent_id > 0
    agent = repo.get_agent(agent_id)
    assert agent["name"] == "Test Writer"
    assert agent["agent_type"] == "writer"


def test_create_and_get_task(repo):
    """Test creating and retrieving an agent task."""
    agent_id = repo.create_agent("writer", "Task Test Writer")
    task_id = repo.create_agent_task(agent_id, "write_section", priority=3)
    assert task_id > 0
    task = repo.get_task(task_id)
    assert task["agent_id"] == agent_id
    assert task["task_type"] == "write_section"
    assert task["state"] == "assigned"


def test_task_state_transitions(repo):
    """Test task state machine transitions."""
    agent_id = repo.create_agent("researcher", "State Test Agent")
    task_id = repo.create_agent_task(agent_id, "discover_content")

    repo.update_task_state(task_id, "assigned")
    assert repo.get_task(task_id)["state"] == "assigned"

    repo.update_task_state(task_id, "working")
    assert repo.get_task(task_id)["state"] == "working"

    repo.update_task_state(task_id, "complete", output_json='{"result": "done"}')
    task = repo.get_task(task_id)
    assert task["state"] == "complete"
