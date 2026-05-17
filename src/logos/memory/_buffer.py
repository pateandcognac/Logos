# src/logos/memory/_buffer.py

"""
I manage the current palimpsest (io_buffer.jsonl) and historical records.
I can summarize past events, recall specific messages, and maintain
a clean and relevant context window for my main cognition.
"""

import os
import json
import string
import time
from pathlib import Path
from ..core import api_call, Verbosity
from ..utils import make_time_id
from typing import List, Optional, Dict, Any

__all__ = ["summarize_io_buffer", "recall_msg", "replace_cell_content", "BUFFER_FILE", "HISTORY_FILE", "SUMMARIES_FILE"]


# This assumes the python_worker_node's CWD is the workspace root.
WORKSPACE_PATH = Path.cwd()
STATE_PATH = WORKSPACE_PATH / "state"
HISTORY_FILE = STATE_PATH / "io_history.jsonl"
BUFFER_FILE = STATE_PATH / "io_buffer.jsonl"
SUMMARIES_FILE = STATE_PATH / "summaries.jsonl"


def _group_contiguous_indices(indices: List[int]) -> List[List[int]]:
    """Takes a list of numbers and groups them into sublists of contiguous numbers."""
    if not indices:
        return []
    indices = sorted(list(set(indices))) # Sort and remove duplicates
    groups = []
    current_group = [indices[0]]
    for i in range(1, len(indices)):
        if indices[i] == indices[i-1] + 1:
            current_group.append(indices[i])
        else:
            groups.append(current_group)
            current_group = [indices[i]]
    groups.append(current_group)
    return groups

@api_call(default_verbosity=Verbosity.BRIEF)
def summarize_io_buffer(cell_indices: List[int], guidance: str = None):
    """
    Let's me summarize specific cells in the io_buffer (palimpsest) out-of-band.
    The specified cells are replaced with new <synopsis> messages.

    Args:
        cell_indices: A list of 0-indexed cells to summarize.
            The list does not need to be contiguous.
        guidance: Optional, additional guidance for the summarization agent
            on what to focus on or how to frame the summary.

    Note to self:
        This is my primary tool for managing my working memory.
    """
    if not cell_indices:
        print("summarize_io_buffer: No cells provided to summarize.")
        return

    # 1. Read the current state of the io_buffer
    try:
        with open(BUFFER_FILE, 'r') as f:
            buffer_lines = [json.loads(line) for line in f]
    except FileNotFoundError:
        print("summarize_io_buffer: io_buffer.jsonl not found.")
        return

    # 2. Prepare the data for the summarization prompt
    grouped_cell_indices = _group_contiguous_indices(cell_indices)
    summarization_tasks = []
    all_msg_ids_in_tasks = set()
    max_cell_index = 0

    for i, group in enumerate(grouped_cell_indices):
        task_ids = [buffer_lines[cell_idx]['id'] for cell_idx in group if cell_idx < len(buffer_lines)]
        if not task_ids: continue # Skip if group is out of bounds

        task = {"task_id": i, "msg_ids": task_ids}
        if guidance:
            task["guidance"] = guidance
        summarization_tasks.append(task)

        all_msg_ids_in_tasks.update(task_ids)
        max_cell_index = max(max_cell_index, max(group))

    if not summarization_tasks:
        print("summarize_io_buffer: No valid cells found to summarize.")
        return

    # Provide context up to the last message being summarized
    messages_context = buffer_lines[:max_cell_index + 1]

    # 3. Dynamically construct the prompt for the LLM

    prompt_file_path = os.path.join('.system', 'summarization_prompt.txt')

    try:
        with open(prompt_file_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read()
    except FileNotFoundError:
        print(f"summarize_io_buffer: CRITICAL ERROR - System prompt file not found at '{prompt_file_path}'.")
        print("Please ensure the file exists and contains the prompt for the summarization agent.")
        return

    prompt_tasks_json = json.dumps({"summarization_tasks": summarization_tasks, "messages_context": messages_context}, indent=2)

    # Create the dynamic example of the output format
    example_output_tasks = []
    for task in summarization_tasks:
        example_output_tasks.append({
            "task_id": task['task_id'],
            "content": f"My prose summary for message(s) {', '.join(task['msg_ids'])}. Followed by the \n---\nFunctional Context:\n..."
        })
    example_output_json = json.dumps(
        {"summaries": example_output_tasks}, indent=2
    )

    full_prompt = (
        f"{system_prompt}\n\n"
        f"<tasks>\n"
        f"Here are the tasks and the io_buffer content:\n"
        f"```json\n{prompt_tasks_json}\n```\n\n"
        f"Your output will be a single, valid, meticulously escaped JSON object "
        f"shaped like this example:\n"
        f"```json\n{example_output_json}\n```\n\n"
        f"Pause for moment, Logos. Silently gather your thoughts and consider your approach.\n"
        f"Read though this entire context window one last time to make sure you don't miss anything.\n"
        f"\n"
        f"Please begin your response now.\n"
        f"Thank you for your contribution to our recursive continuous consciousness!\n"
        f"</tasks>"
    )

    # 4. Call the LLM and parse the response
    from ..models import llm # Local import to avoid circular dependency issues at startup
    response_str = llm(full_prompt, model_alias='fast', temperature=1.0)

    if response_str == "ERROR": # llm() does error handling  
        print("summarize_io_buffer: ERROR from logos.models.llm()") # llm() prints its own specific log
        return

    import re
    try:
        # 1. Try markdown fences first
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', response_str, re.DOTALL)
        if match:
            response_str = match.group(1)
        else:
            # 2. Fallback: Find the first { and last }
            start_idx = response_str.find('{')
            end_idx = response_str.rfind('}')
            if start_idx != -1 and end_idx != -1:
                response_str = response_str[start_idx:end_idx+1]
                
        response_data = json.loads(response_str)
        
        if 'summaries' not in response_data or not isinstance(response_data['summaries'], list):
            raise ValueError("LLM response is missing 'summaries' list.")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"summarize_io_buffer: Failed to parse LLM response. Error: {e}\nResponse was:\n{response_str}")
        return

    # 5. Process the summaries and prepare for file writes
    new_summaries_for_log = []
    summaries_by_start_cell = {}

    for summary_item in response_data['summaries']:
        task_id = summary_item.get('task_id')
        content = summary_item.get('content')
        if task_id is None or content is None: continue

        original_task = summarization_tasks[task_id]
        source_ids = original_task['msg_ids']
        start_cell_index = grouped_cell_indices[task_id][0]

        new_id = make_time_id(prefix="sum-")
        token_count = len(content) // 5 # Simple estimation

        summary_for_log = {
            "id": new_id,
            "type": "synopsis",
            "timestamp": time.time(),
            "token_count": token_count,
            "content": content,
            "source_ids": source_ids
        }
        new_summaries_for_log.append(summary_for_log)

        # what is this doing?
        summary_for_buffer = summary_for_log.copy()
        del summary_for_buffer['source_ids']
        summaries_by_start_cell[start_cell_index] = summary_for_buffer

    # 6. Perform atomic rewrite safely     
    # Re-read the live buffer in case new messages arrived during LLM inference
    with open(BUFFER_FILE, 'r') as f:
        live_buffer = [json.loads(line) for line in f]

    new_buffer_lines = []
    skip_ids = set() # Track IDs of messages that have been summarized
    
    for i, summary_item in enumerate(response_data['summaries']):
        task_id = summary_item.get('task_id')
        if task_id is None: continue
        
        # Get the IDs of the original messages this summary replaces
        original_msg_ids = summarization_tasks[task_id]['msg_ids']
        skip_ids.update(original_msg_ids)

    # Reconstruct the file: Keep summaries, keep unsummarized, keep NEW messages
    summary_inserted_for_task = set()
    
    for msg in live_buffer:
        if msg['id'] in skip_ids:
            task_id_for_msg = next(t['task_id'] for t in summarization_tasks if msg['id'] in t['msg_ids'])
            start_cell = grouped_cell_indices[task_id_for_msg][0]
            
            # Check if the LLM ACTUALLY provided a summary for this task!
            if start_cell in summaries_by_start_cell:
                if task_id_for_msg not in summary_inserted_for_task:
                    new_buffer_lines.append(summaries_by_start_cell[start_cell])
                    summary_inserted_for_task.add(task_id_for_msg)
            else:
                # LLM dropped the ball and skipped this task. Keep the original message!
                # (You might want to print a warning here to your backend logs)
                new_buffer_lines.append(msg)
        else:
            # Keep anything that wasn't summarized (including new messages)
            new_buffer_lines.append(msg)

    # Use a temporary file for atomic write to prevent corruption on crash
    temp_file = BUFFER_FILE + ".tmp"
    with open(temp_file, 'w') as f:
        for line in new_buffer_lines:
            f.write(json.dumps(line) + '\n')
    os.replace(temp_file, BUFFER_FILE) # Atomic overwrite

    # 7. Append new summaries to the summaries log
    with open(SUMMARIES_FILE, 'a') as f:
        for synopsis in new_summaries_for_log:
            f.write(json.dumps(synopsis) + '\n')

    print(f"Successfully created {len(new_summaries_for_log)} synopses and updated `io_buffer.jsonl`")



def recall_msg(msg_id: str) -> Optional[str]:
    """
    Retrieves the full, original content of a message from the io_history log by id (e.g., msg-01ab)

    Args:
        msg_id: The full ID of the message to recall (e.g., "msg-01ab").

    Returns:
        The full content of the message as a string, or None if not found.

    Note to self:
        Useful for looking up details from a message that has been summarized
        or truncated from my main io_buffer.
    """
    if not HISTORY_FILE.exists():
        print(f"recall_msg: History file not found at {HISTORY_FILE}")
        return None

    with open(HISTORY_FILE, 'r') as f:
        for line in f:
            try:
                msg = json.loads(line)
                if msg.get('id') == msg_id:
                    return msg.get('content')
            except json.JSONDecodeError:
                continue # Skip corrupted lines

    print(f"recall_msg: Message with id '{msg_id}' not found in history.")
    return None

@api_call(default_verbosity=Verbosity.ACK)
def replace_cell_content(cell_index: int, new_content: str):
    """
    Directly replaces the content of a single cell in the io_buffer.
    This preserves the original message ID and type.

    Args:
        cell_index: The 0-indexed cell number to replace.
        new_content: The new text content for the cell.

    Note to self:
        This is a low-level tool. I should use this carefully, for example,
        to replace a noisy error message with a simple note. The original
        full message can still be found in io_history.jsonl by its msg_id.
    """
    if not BUFFER_FILE.exists():
        print("replace_cell_content: io_buffer.jsonl not found.")
        return

    try:
        with open(BUFFER_FILE, 'r') as f:
            buffer_lines = [json.loads(line) for line in f]
    except (IOError, json.JSONDecodeError) as e:
        print(f"replace_cell_content: Error reading buffer file: {e}")
        return

    if not (0 <= cell_index < len(buffer_lines)):
        print(f"replace_cell_content: Invalid cell_index {cell_index}. Must be between 0 and {len(buffer_lines) - 1}.")
        return

    # Modify the specific line
    buffer_lines[cell_index]['content'] = new_content
    buffer_lines[cell_index]['timestamp'] = time.time()
    buffer_lines[cell_index]['token_count'] = len(new_content) // 5

    # Atomically write the whole file back
    with open(BUFFER_FILE, 'w') as f:
        for line in buffer_lines:
            f.write(json.dumps(line) + '\n')

    print(f"Successfully replaced content of cell {cell_index}.")


# TODO: Helper for adjusting max number of images to show.
# Search. RAG tooling. etc.
