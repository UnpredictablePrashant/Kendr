import json

from tasks.a2a_agent_utils import begin_agent_session, publish_agent_output
from tasks.utils import OUTPUT_DIR, llm, log_task_update, write_text_file


def review_scientific_literature(state):
    active_task, task_content, _ = begin_agent_session(state, "review_scientific_literature")
    state["review_scientific_literature_calls"] = state.get("review_scientific_literature_calls", 0) + 1
    call_number = state["review_scientific_literature_calls"]

    request_text = state.get("topic_query") or task_content or state.get("current_objective") or state.get("user_query", "")
    context = {
        "request_text": request_text,
        "current_objective": state.get("current_objective", ""),
        "user_query": state.get("user_query", ""),
        "skills": ["natural_language_processing", "information_extraction"],
        "requirements": ["python", "nltk", "scikit-learn"],
        "notes": "Need to implement sentiment analysis for identifying biased literature",
    }

    log_task_update("review_scientific_literature", f"Generated agent pass #{call_number} started.")
    prompt = f"""
You are the review_scientific_literature in a multi-agent ecosystem.

Description:
Reviews scientific literature to assess risks

Primary task:
Review the latest research on a given topic to assess potential risks and provide an output with risk assessment result.

Context:
{json.dumps(context, indent=2, ensure_ascii=False)}

Return a concise but useful result for the requested work. If external setup is missing, say exactly what is required.
""".strip()

    response = llm.invoke(prompt)
    output_text = normalize_llm_text(response.content if hasattr(response, "content") else response)
    state["risk_assessment_result"] = output_text
    state["draft_response"] = output_text
    write_text_file("review_scientific_literature_output_" + str(call_number) + ".txt", output_text)
    log_task_update("review_scientific_literature", f"Generated agent output saved to {OUTPUT_DIR}/review_scientific_literature_output_{call_number}.txt")
    return publish_agent_output(
        state,
        "review_scientific_literature",
        output_text,
        "review_scientific_literature_result_" + str(call_number),
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent"],
    )
