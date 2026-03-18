from tasks.a2a_agent_utils import begin_agent_session, publish_agent_output
from tasks.utils import OUTPUT_DIR, llm, log_task_update, logger, write_text_file



def planner_agent(state):
    active_task, task_content, _ = begin_agent_session(state, "planner_agent")
    log_task_update("Planner", "Analyzing the user request and building a plan.")
    user_query = task_content or state.get("current_objective") or state["user_query"]
    logger.info(f"[Planner] User query: {user_query}")
    prompt=f"""
    You are a planning agent ina multi agent AI system.

    Your job is to read the user's query and create a short plan for how the worker agent should answer.

    User query: {user_query}

    Return only a short actionable plan
    """
    response=llm.invoke(prompt)
    plan=response.content if hasattr(response, "content") else str(response)
    state['plan']=plan
    state["current_objective"] = user_query
    write_text_file("planner_output.txt", plan)
    log_task_update("Planner", f"Plan saved to {OUTPUT_DIR}/planner_output.txt", plan)
    state = publish_agent_output(
        state,
        "planner_agent",
        plan,
        "planner_plan",
        recipients=["orchestrator_agent", "worker_agent"],
    )
    return state
