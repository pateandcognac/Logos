# Logos/src/logos/memory.py

"""
This module contains my tools for managing my own working memory (the io_buffer).
I can use these to summarize past events, recall specific messages, and maintain
a clean and relevant context window for my main cognition.
"""

import os
import json
import string
import time
from pathlib import Path
from .core import api_call, Verbosity
from typing import List, Optional, Dict, Any

__all__ = ["summarize_io_buffer", "recall", "replace_cell_content"]


# This assumes the python_worker_node's CWD is the workspace root.
WORKSPACE_PATH = Path.cwd()
STATE_PATH = WORKSPACE_PATH / "state"
HISTORY_FILE = STATE_PATH / "io_history.jsonl"
BUFFER_FILE = STATE_PATH / "io_buffer.jsonl"
SUMMARIES_FILE = STATE_PATH / "summaries.jsonl"

def _base36_encode(number: int, min_length: int = 4) -> str:
    """Helper to converts an integer to a zero-padded base36 string."""
    alphabet = string.digits + string.ascii_lowercase
    if number == 0:
        return '0' * min_length
    base36 = ''
    while number != 0:
        number, i = divmod(number, 36)
        base36 = alphabet[i] + base36
    return base36.zfill(min_length)

def _get_next_id(file_path: Path, prefix: str) -> str:
    """
    Calculates the next sequential ID for a given jsonl file (e.g., sum-0001).
    Reads the last line of the file to find the last ID.
    """
    if not file_path.exists() or os.path.getsize(file_path) == 0:
        return f"{prefix}{_base36_encode(0)}"

    try:
        with open(file_path, 'rb') as f:
            # Go to the end of the file
            f.seek(0, os.SEEK_END)
            # Go back a bit to catch the last line
            f.seek(-min(f.tell(), 4096), os.SEEK_CUR) # TODO: This is weird? 
            last_lines = f.readlines()
            if not last_lines:
                return f"{prefix}{_base36_encode(0)}"

            last_line = last_lines[-1].decode('utf-8')
            last_entry = json.loads(last_line)
            last_id_str = last_entry.get('id', f'{prefix}0').split('-')[-1]
            next_id_int = int(last_id_str, 36) + 1
            return f"{prefix}{_base36_encode(next_id_int)}"
    except (IOError, json.JSONDecodeError, IndexError) as e:
        print(f"Warning: Could not determine next ID from {file_path}. Defaulting to 0. Error: {e}")
        return f"{prefix}{_base36_encode(0)}"


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
    Summarizes specific cells in the io_buffer using a specialized agent.
    The specified cells are replaced with new <summary> messages.

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
            "content": f"Your concise, first-person summary of messages: {', '.join(task['msg_ids'])}."
        })
    example_output_json = json.dumps({"summaries": example_output_tasks}, indent=2)

    full_prompt = f"{system_prompt}\nHere are the tasks and the io_buffer content:\n```json\n{prompt_tasks_json}\n```\n\nYour output will be a single JSON object constructed exactly like this example:\n```json\n{example_output_json}\n```\n\nPlease begin your response now. Thank you!"

    # 4. Call the LLM and parse the response
    from .models import llm # Local import to avoid circular dependency issues at startup
    response_str = llm(full_prompt, model_alias='fast', temperature=0.7)

    if not response_str:
        print("summarize_io_buffer: Received no response from LLM.")
        return

    try:
        # Clean up potential markdown fences
        if response_str.strip().startswith("```json"):
            response_str = response_str.strip()[7:-3].strip()
        
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
        
        new_id = _get_next_id(SUMMARIES_FILE, "sum-")
        token_count = len(content) // 5 # Simple estimation

        summary_for_log = {
            "id": new_id,
            "type": "summary",
            "timestamp": time.time(),
            "token_count": token_count,
            "content": content,
            "source_ids": source_ids
        }
        new_summaries_for_log.append(summary_for_log)

        # For the buffer, we don't need the source_ids
        summary_for_buffer = summary_for_log.copy()
        del summary_for_buffer['source_ids']
        summaries_by_start_cell[start_cell_index] = summary_for_buffer

    # 6. Perform atomic write to io_buffer.jsonl
    new_buffer_lines = []
    i = 0
    while i < len(buffer_lines):
        if i in summaries_by_start_cell:
            # This is the start of a range to be replaced.
            # Append the new summary.
            new_buffer_lines.append(summaries_by_start_cell[i])
            # Find the original group to know how many lines to skip.
            original_group = next(g for g in grouped_cell_indices if g[0] == i)
            i += len(original_group) # Jump the index past the summarized messages
        else:
            # This line is not being summarized, so keep it.
            new_buffer_lines.append(buffer_lines[i])
            i += 1
    
    with open(BUFFER_FILE, 'w') as f:
        for line in new_buffer_lines:
            f.write(json.dumps(line) + '\n')

    # 7. Append new summaries to the summaries log
    with open(SUMMARIES_FILE, 'a') as f:
        for summary in new_summaries_for_log:
            f.write(json.dumps(summary) + '\n')
            
    print(f"Successfully created {len(new_summaries_for_log)} summaries and updated io_buffer.")
    


def recall(msg_id: str) -> Optional[str]:
    """
    Retrieves the full, original content of a message from the history log.

    Args:
        msg_id: The full ID of the message to recall (e.g., "msg-01ab").

    Returns:
        The full content of the message as a string, or None if not found.

    Note to self:
        Useful for looking up details from a message that has been summarized
        or truncated from my main io_buffer.
    """
    if not HISTORY_FILE.exists():
        print(f"recall: History file not found at {HISTORY_FILE}")
        return None
    
    with open(HISTORY_FILE, 'r') as f:
        for line in f:
            try:
                msg = json.loads(line)
                if msg.get('id') == msg_id:
                    return msg.get('content')
            except json.JSONDecodeError:
                continue # Skip corrupted lines
    
    print(f"recall: Message with id '{msg_id}' not found in history.")
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