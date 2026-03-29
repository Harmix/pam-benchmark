"""
LongMemEval Benchmark Runner

Runs the LongMemEval benchmark: sends full conversation history to an LLM,
generates answers, then evaluates with an LLM-as-judge.
Saves per-category results to MongoDB.

Based on agents/LongMemEval by Di Wu (2024).
"""

import builtins
import os
import sys
import json
import time
import argparse
import functools
from datetime import datetime
from typing import Dict, List, Optional

import io
import math

# Force unbuffered output so progress logs appear immediately in log files.
print = functools.partial(builtins.print, flush=True)

import backoff
import numpy as np
import openai
from openai import OpenAI
import requests
import tiktoken
from tqdm import tqdm

from pymongo import MongoClient


def load_secrets():
    """Load API keys from secrets.env file."""
    secrets_path = '/workspace/secrets.env'
    if os.path.exists(secrets_path):
        with open(secrets_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
        print("Loaded secrets from secrets.env")
    else:
        print("Warning: secrets.env not found, using existing environment variables")


###############################################################################
# PAM Agent API Client
###############################################################################

class PAMClient:
    """Client for the PAM API used when MODEL=pam.

    Requires an admin login to obtain a token before creating benchmark
    user accounts.
    """

    MAX_FILES_PER_REQUEST = 5
    SSE_TIMEOUT = 600

    def __init__(self, api_host: str):
        self.host = api_host.rstrip("/")
        self.base_url = f"{self.host}/v1"
        self.session = requests.Session()
        self.admin_token: Optional[str] = None
        self.access_token: Optional[str] = None
        self.user_id: Optional[int] = None
        self._admin_email: Optional[str] = None
        self._admin_password: Optional[str] = None
        self._user_email: Optional[str] = None
        self._user_password: Optional[str] = None

    def _headers(self) -> dict:
        h = {}
        if self.access_token:
            h["Authorization"] = f"Bearer {self.access_token}"
        elif self.admin_token:
            h["Authorization"] = f"Bearer {self.admin_token}"
        return h

    # --- 0. Admin login ---------------------------------------------------------

    def login(self, email: str, password: str) -> str:
        """Authenticate and store the admin token."""
        self._admin_email = email
        self._admin_password = password
        resp = self.session.post(
            f"{self.host}/v1/auth/login",
            json={"email": email, "password": password},
            timeout=180,
        )
        resp.raise_for_status()
        data = resp.json()
        self.admin_token = data["tokens"]["access_token"]
        return self.admin_token

    def _login_as(self, email: str, password: str) -> str:
        """Login with arbitrary credentials and return the access token."""
        resp = self.session.post(
            f"{self.host}/v1/auth/login",
            json={"email": email, "password": password},
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["tokens"]["access_token"]

    def refresh_token(self) -> None:
        """Refresh both admin and user tokens using stored credentials."""
        if self._admin_email and self._admin_password:
            print("        Refreshing admin token ...")
            self.admin_token = self._login_as(self._admin_email, self._admin_password)
        if self._user_email and self._user_password:
            print("        Refreshing user token ...")
            self.access_token = self._login_as(self._user_email, self._user_password)

    # --- 1. Account lifecycle ---------------------------------------------------

    def create_account(
        self,
        email: str,
        password: str,
        name: str,
        company_name: str = "Acme Inc",
        position: str = "Engineer",
    ) -> dict:
        url = f"{self.base_url}/admin/create-account"
        body = {
            "email": email,
            "password": password,
            "name": name,
            "company_name": company_name,
            "position": position,
        }
        headers = {**self._headers(), "Content-Type": "application/json"}
        print(f"        POST {url}")
        print(f"        Headers: { {k: (v[:20] + '…' if len(v) > 20 else v) for k, v in headers.items()} }")
        print(f"        Body: {body}")
        resp = self.session.post(url, json=body, headers=headers, timeout=180)
        if not resp.ok:
            print(f"        Response {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["tokens"]["access_token"]
        self.user_id = data["user"]["id"]
        self._user_email = email
        self._user_password = password
        return data

    def delete_account(self) -> None:
        url = f"{self.base_url}/admin/delete-account/{self.user_id}"
        resp = self.session.delete(url, headers=self._headers(), timeout=180)
        if resp.status_code == 401:
            self.refresh_token()
            resp = self.session.delete(url, headers=self._headers(), timeout=180)
        resp.raise_for_status()

    def backup_workspace(self) -> dict:
        url = f"{self.base_url}/admin/backup-workspace/{self.user_id}"
        resp = self.session.post(url, headers=self._headers(), timeout=300)
        if resp.status_code == 401:
            self.refresh_token()
            resp = self.session.post(url, headers=self._headers(), timeout=300)
        resp.raise_for_status()
        return resp.json()

    # --- 2. File upload ---------------------------------------------------------

    def upload_generic_files(self, file_tuples: List[tuple]) -> list:
        """Upload files in batches of MAX_FILES_PER_REQUEST.

        Args:
            file_tuples: list of (filename, file_bytes) pairs.

        Returns:
            Aggregated list of upload result dicts.
        """
        all_results = []
        for batch_start in range(0, len(file_tuples), self.MAX_FILES_PER_REQUEST):
            batch = file_tuples[batch_start:batch_start + self.MAX_FILES_PER_REQUEST]
            files_payload = [
                ("files", (fname, io.BytesIO(fbytes), "text/plain"))
                for fname, fbytes in batch
            ]
            resp = self.session.post(
                f"{self.base_url}/files/upload-generic/{self.user_id}",
                headers=self._headers(),
                files=files_payload,
                timeout=180,
            )
            resp.raise_for_status()
            all_results.extend(resp.json())
        return all_results

    # --- 3. Memory creation (async pipeline) ------------------------------------

    MEMORY_POLL_INTERVAL = 30      # seconds between status checks
    TERMINAL_STATUSES = {"completed", "failed", "stopped", "cancelled"}

    PIPELINE_TYPE = "benchmark_memory"

    def trigger_memory_pipeline(
        self, max_files: Optional[int] = None, batch_size: int = 500,
    ) -> str:
        """Start the async benchmark_memory pipeline. Returns the run_id."""
        url = f"{self.base_url}/memory/pipeline/{self.PIPELINE_TYPE}/run"
        body = {
            "sync_type": "initial",
            "params": {
                "max_files": max_files,
                "batch_size": batch_size,
            },
        }
        print(f"        POST {url}?user_id={self.user_id}")
        print(f"        Body: {json.dumps(body)}")
        kwargs = dict(
            params={"user_id": self.user_id},
            json=body,
            headers=self._headers(),
            timeout=180,
        )
        resp = self.session.post(url, **kwargs)
        if resp.status_code == 401:
            self.refresh_token()
            kwargs["headers"] = self._headers()
            resp = self.session.post(url, **kwargs)
        if resp.status_code not in (200, 202):
            print(f"        Response {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        data = resp.json()
        return data["run_id"]

    def poll_memory_status(self) -> dict:
        """Get the current status of the benchmark_memory pipeline.

        Automatically refreshes the auth token on 401 and retries once.
        """
        url = f"{self.base_url}/memory/pipeline/{self.PIPELINE_TYPE}/status"
        resp = self.session.get(
            url,
            params={"user_id": self.user_id},
            headers=self._headers(),
            timeout=120,
        )
        if resp.status_code == 401:
            self.refresh_token()
            resp = self.session.get(
                url,
                params={"user_id": self.user_id},
                headers=self._headers(),
                timeout=120,
            )
        resp.raise_for_status()
        return resp.json()

    def create_memory(self, max_files: Optional[int] = None, batch_size: int = 500) -> dict:
        """Trigger the memory pipeline and poll until a terminal status is reached."""
        run_id = self.trigger_memory_pipeline(max_files=max_files, batch_size=batch_size)
        print(f"        Pipeline triggered (run_id={run_id}), polling every "
              f"{self.MEMORY_POLL_INTERVAL}s ...")

        start = time.time()
        last_status = "pending"
        while True:
            time.sleep(self.MEMORY_POLL_INTERVAL)

            status_resp = self.poll_memory_status()
            run_info = status_resp.get("run", status_resp)
            last_status = run_info.get("run_status", run_info.get("status", "unknown"))
            elapsed_min = (time.time() - start) / 60
            print(f"        [{elapsed_min:.1f}m] status={last_status}")

            if last_status in self.TERMINAL_STATUSES:
                if last_status != "completed":
                    error_msg = run_info.get("run_error_message", "no details")
                    raise RuntimeError(
                        f"Memory pipeline {last_status}: {error_msg}"
                    )
                return status_resp

    # --- 4. Chat (SSE) ----------------------------------------------------------

    def send_message(self, prompt: str, conversation_id: Optional[str] = None) -> str:
        """Send a message and return the **last** assistant text turn from the SSE stream.

        PAM may produce multiple assistant text turns separated by tool-use
        cycles.  Only the final assistant text turn contains the actual answer;
        earlier ones are intermediate messages like "I'll search for …".

        Turn tracking:
          - ``role "assistant"`` + ``content_new.type "text"`` → append to
            the *current* turn buffer.
          - ``role "tool_use"`` or ``role "tool_result"`` → save the current
            turn and start a fresh buffer (the next assistant text is a new
            turn).
          - ``role "result"`` / ``event: stream_stopped`` → terminal, stop.
        """
        body = {
            "prompt": prompt,
            "conversation_id": conversation_id,
        }
        url = f"{self.base_url}/messages/stream"
        resp = self.session.post(
            url, json=body, headers=self._headers(),
            stream=True, timeout=self.SSE_TIMEOUT,
        )
        if resp.status_code == 401:
            self.refresh_token()
            resp = self.session.post(
                url, json=body, headers=self._headers(),
                stream=True, timeout=self.SSE_TIMEOUT,
            )
        resp.raise_for_status()

        all_turns: List[List[str]] = []
        current_turn: List[str] = []

        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("event: stream_stopped"):
                break
            if not line.startswith("data: "):
                continue

            try:
                payload = json.loads(line[len("data: "):])
            except json.JSONDecodeError:
                continue

            if payload.get("type") == "resume_conversation":
                continue

            role = payload.get("role")
            if role == "assistant":
                content_new = payload.get("content_new", {})
                if content_new.get("type") == "text" and content_new.get("text"):
                    current_turn.append(content_new["text"])
            elif role in ("tool_use", "tool_result"):
                if current_turn:
                    all_turns.append(current_turn)
                    current_turn = []
            elif role == "result":
                break

        if current_turn:
            all_turns.append(current_turn)

        for idx, turn in enumerate(all_turns):
            turn_text = "".join(turn)
            print(f"        [SSE turn {idx+1}/{len(all_turns)}] "
                  f"{turn_text[:200]}{'…' if len(turn_text) > 200 else ''}")

        if not all_turns:
            return ""
        return "".join(all_turns[-1])


def _date_to_filename_prefix(date_str: str) -> str:
    """Convert '2023/05/20 (Sat) 02:21' → '2023-05-20_02-21'."""
    parts = date_str.split()
    day_part = parts[0].replace("/", "-")       # '2023-05-20'
    time_part = parts[-1].replace(":", "-")      # '02-21'
    return f"{day_part}_{time_part}"


def serialize_sessions_to_files(entry: dict) -> List[tuple]:
    """Convert a question's haystack sessions into (filename, bytes) pairs.

    Each session becomes a plain-text file whose name encodes the
    chronological order and timestamp so PAM can reconstruct the timeline:
        session_001_2023-05-20_02-21_sharegpt_yywfIrx_0.txt

    The file body starts with a metadata header (session number, date,
    total sessions) followed by the conversation turns.
    """
    total = len(entry["haystack_sessions"])
    file_tuples = []
    for idx, (sid, date, session) in enumerate(zip(
        entry["haystack_session_ids"],
        entry["haystack_dates"],
        entry["haystack_sessions"],
    )):
        date_prefix = _date_to_filename_prefix(date)
        filename = f"session_{idx+1:03d}_{date_prefix}_{sid}.txt"

        lines = [
            f"Session {idx+1} of {total}",
            f"Session Date: {date}",
            f"Session ID: {sid}",
            "",
        ]
        for turn in session:
            lines.append(f"{turn['role']}: {turn['content'].strip()}")
            lines.append("")
        text = "\n".join(lines)
        file_tuples.append((filename, text.encode("utf-8")))
    return file_tuples


def process_question_pam(
    pam_host: str,
    admin_email: str,
    admin_password: str,
    entry: dict,
    question_idx: int,
    total: int,
    qid2type: dict,
    debug: bool = False,
    debug_user_id: Optional[int] = None,
) -> dict:
    """Run the full PAM pipeline for a single LongMemEval question.

    0. Login to obtain admin token
    1. Create benchmark user account  (skipped when debug_user_id is set)
    2. Upload haystack sessions       (skipped when debug_user_id is set)
    3. Create memory                  (skipped when debug_user_id is set)
    4. Send the question via SSE chat
    5. Backup workspace               (skipped in debug mode)
    6. Delete account                 (skipped in debug mode)
    """
    qid = entry["question_id"]
    qtype = qid2type.get(qid, "unknown")
    run_ts = int(time.time())
    email = f"longmemeval-{qid}-{run_ts}@benchmark.local"
    reuse_user = debug_user_id is not None
    print(f"\n[{question_idx+1}/{total}] Question {qid} ({qtype})"
          + (f" [DEBUG user_id={debug_user_id}]" if reuse_user else "")
          + (" [DEBUG]" if debug and not reuse_user else ""))
    print(f"        Expected answer:\n{str(entry.get('answer', ''))}")

    pam = PAMClient(pam_host)
    answer = ""
    memory_creation_sec = 0.0
    generation_sec = 0.0

    try:
        # Step 0: Login to get admin token
        print(f"  [0/6] Logging in as {admin_email} ...")
        pam.login(admin_email, admin_password)

        if reuse_user:
            pam.user_id = debug_user_id
            pam.access_token = pam.admin_token
            print(f"  [1/6] Reusing existing user_id={debug_user_id} (debug)")
            print(f"  [2/6] Skipping file upload (debug)")
            print(f"  [3/6] Skipping memory creation (debug)")
        else:
            # Step 1: Create account
            print(f"  [1/6] Creating account {email} ...")
            pam.create_account(email=email, password="benchmark-run", name=f"LongMemEval {qid}")
            print(f"        user_id={pam.user_id}")

            # Step 2: Upload haystack sessions as files
            file_tuples = serialize_sessions_to_files(entry)
            num_batches = math.ceil(len(file_tuples) / PAMClient.MAX_FILES_PER_REQUEST)
            print(f"  [2/6] Uploading {len(file_tuples)} session files ({num_batches} batches) ...")
            upload_results = pam.upload_generic_files(file_tuples)
            print(f"        Uploaded {len(upload_results)} files")

            # Step 3: Create memory (timed separately)
            print(f"  [3/6] Creating memory (this may take a while) ...")
            mem_start = time.time()
            mem_result = pam.create_memory()
            memory_creation_sec = round(time.time() - mem_start, 2)
            print(f"        Memory created: {mem_result.get('message', 'ok')} "
                  f"({memory_creation_sec}s)")

        # Step 4: Ask the question (timed separately)
        prompt = (
            f"Current Date: {entry['question_date']}\n"
            f"Question: {entry['question']}\n"
            f"Answer:"
        )
        print(f"  [4/6] Sending question: {entry['question'][:80]}...")
        gen_start = time.time()
        answer = pam.send_message(prompt)
        generation_sec = round(time.time() - gen_start, 2)
        print(f"        Final answer ({generation_sec}s):\n{answer}")

        if not debug:
            # Step 5: Backup workspace
            print(f"  [5/6] Backing up workspace ...")
            backup = pam.backup_workspace()
            print(f"        Backup: {backup.get('backup_path', 'done')}")
        else:
            print(f"  [5/6] Skipping backup (debug)")

    except Exception as e:
        print(f"  ERROR for {qid}: {repr(e)}")

    finally:
        if not debug and pam.user_id:
            try:
                print(f"  [6/6] Deleting account (user_id={pam.user_id}) ...")
                pam.delete_account()
                print(f"        Account deleted")
            except Exception as e:
                print(f"        Warning: cleanup failed: {repr(e)}")
        elif debug:
            print(f"  [6/6] Skipping account deletion (debug)")

    return {
        "question_id": qid,
        "question_type": qtype,
        "hypothesis": answer.strip(),
        "generation_duration_sec": generation_sec,
        "memory_creation_duration_sec": memory_creation_sec,
    }


def generate_answers_pam(
    pam_host: str,
    admin_email: str,
    admin_password: str,
    data: list,
    qid2type: dict,
    debug: bool = False,
    debug_user_id: Optional[int] = None,
) -> list:
    """Generate answers for all questions using the PAM Agent API."""
    predictions = []
    for i, entry in enumerate(data):
        pred = process_question_pam(
            pam_host, admin_email, admin_password,
            entry, i, len(data), qid2type,
            debug=debug, debug_user_id=debug_user_id,
        )
        predictions.append(pred)
    return predictions


def parse_args():
    parser = argparse.ArgumentParser(description='Run LongMemEval benchmark')
    parser.add_argument('--data-file', type=str,
                        default='/task_data/data/longmemeval_s_cleaned.json',
                        help='Path to LongMemEval dataset')
    parser.add_argument('--out-dir', type=str, default='/outputs',
                        help='Directory for output files')
    parser.add_argument('--model', type=str, default='gpt-4o',
                        help='Model for answer generation')
    parser.add_argument('--eval-model', type=str, default='gpt-4o',
                        help='Model for LLM-as-judge evaluation')
    parser.add_argument('--history-format', type=str, default='nl',
                        choices=['json', 'nl'],
                        help='Format for conversation history')
    parser.add_argument('--max-questions', type=int, default=0,
                        help='Max questions to process (0 = all)')
    parser.add_argument('--question-id', type=str, default=None,
                        help='Process a single question by ID')
    parser.add_argument('--cot', action='store_true',
                        help='Use chain-of-thought prompting')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing predictions')
    parser.add_argument('--skip-eval', action='store_true',
                        help='Skip LLM-as-judge evaluation')
    parser.add_argument('--debug', action='store_true',
                        help='PAM debug mode: skip backup and account deletion')
    parser.add_argument('--debug-user-id', type=int, default=None,
                        help='PAM debug: reuse existing user/memory instead of creating new ones')
    parser.add_argument('--question-range-start', type=int, default=None,
                        help='1-based inclusive start index in dataset order (after QUESTION_ID filter)')
    parser.add_argument('--question-range-end', type=int, default=None,
                        help='1-based inclusive end index in dataset order (after QUESTION_ID filter)')

    args = parser.parse_args()

    if os.environ.get("DEBUG", "").lower() in ("true", "1"):
        args.debug = True
    env_debug_uid = os.environ.get("DEBUG_USER_ID", "")
    if env_debug_uid and args.debug_user_id is None:
        args.debug_user_id = int(env_debug_uid)

    env_qrs = os.environ.get("QUESTION_RANGE_START", "").strip()
    env_qre = os.environ.get("QUESTION_RANGE_END", "").strip()
    if env_qrs and args.question_range_start is None:
        args.question_range_start = int(env_qrs)
    if env_qre and args.question_range_end is None:
        args.question_range_end = int(env_qre)

    return args


MODEL_MAX_LENGTHS = {
    'gpt-4o': 128000,
    'gpt-4o-2024-08-06': 128000,
    'gpt-4o-mini': 128000,
    'gpt-4o-mini-2024-07-18': 128000,
    'gpt-4.1': 1047576,
}

QUESTION_TYPES = [
    'single-session-user',
    'single-session-assistant',
    'single-session-preference',
    'multi-session',
    'temporal-reasoning',
    'knowledge-update',
]


@backoff.on_exception(backoff.constant, (openai.RateLimitError,), interval=5)
def chat_completions_with_backoff(client, **kwargs):
    return client.chat.completions.create(**kwargs)


def format_history_nl(sessions, dates):
    """Format conversation sessions in natural language."""
    parts = []
    for i, (session, date) in enumerate(zip(sessions, dates)):
        lines = [f"### Session {i+1}:", f"Session Date: {date}", "Session Content:"]
        for turn in session:
            lines.append(f"\n{turn['role']}: {turn['content'].strip()}")
        parts.append('\n'.join(lines))
    return '\n\n'.join(parts)


def format_history_json(sessions, dates):
    """Format conversation sessions as JSON."""
    parts = []
    for i, (session, date) in enumerate(zip(sessions, dates)):
        header = f"### Session {i+1}:\nSession Date: {date}\nSession Content:"
        parts.append(header + '\n' + json.dumps(session))
    return '\n\n'.join(parts)


def build_prompt(entry, history_format='nl', cot=False, tokenizer=None, max_context_tokens=None):
    """Build the generation prompt for a single question."""
    if cot:
        template = (
            'I will give you several history chats between you and a user. '
            'Please answer the question based on the relevant chat history. '
            'Answer the question step by step: first extract all the relevant '
            'information, and then reason over the information to get the answer.'
            '\n\n\nHistory Chats:\n\n{}\n\nCurrent Date: {}\nQuestion: {}\n'
            'Answer (step by step):'
        )
    else:
        template = (
            'I will give you several history chats between you and a user. '
            'Please answer the question based on the relevant chat history.'
            '\n\n\nHistory Chats:\n\n{}\n\nCurrent Date: {}\nQuestion: {}\n'
            'Answer:'
        )

    if history_format == 'nl':
        history = format_history_nl(entry['haystack_sessions'], entry['haystack_dates'])
    else:
        history = format_history_json(entry['haystack_sessions'], entry['haystack_dates'])

    if tokenizer and max_context_tokens:
        tokens = tokenizer.encode(history, allowed_special={'<|endoftext|>'})
        if len(tokens) > max_context_tokens:
            print(f'  Truncating history from {len(tokens)} to {max_context_tokens} tokens')
            history = tokenizer.decode(tokens[:max_context_tokens])

    return template.format(history, entry['question_date'], entry['question'])


def generate_answers(client, data, args, tokenizer, qid2type):
    """Generate answers for all questions. Returns predictions with per-question timing."""
    model_name = args.model
    gen_length = 800 if args.cot else 500
    model_max = MODEL_MAX_LENGTHS.get(model_name, 128000)
    max_context_tokens = model_max - gen_length - 1000

    predictions = []
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for entry in tqdm(data, desc="Generating answers"):
        print(f"  [{entry['question_id']}] Expected answer:\n{str(entry.get('answer', ''))}")
        prompt = build_prompt(
            entry,
            history_format=args.history_format,
            cot=args.cot,
            tokenizer=tokenizer,
            max_context_tokens=max_context_tokens,
        )

        q_start = time.time()
        try:
            kwargs = {
                'model': model_name,
                'messages': [{"role": "user", "content": prompt}],
                'n': 1,
                'temperature': 0,
                'max_tokens': gen_length,
            }
            completion = chat_completions_with_backoff(client, **kwargs)
            answer = completion.choices[0].message.content.strip()
            total_prompt_tokens += completion.usage.prompt_tokens
            total_completion_tokens += completion.usage.completion_tokens

            predictions.append({
                'question_id': entry['question_id'],
                'question_type': qid2type.get(entry['question_id'], 'unknown'),
                'hypothesis': answer,
                'generation_duration_sec': round(time.time() - q_start, 2),
            })
            print(f"  [{entry['question_id']}] Q: {entry['question'][:80]}...")
            print(f"  A: {answer[:120]}...")
        except Exception as e:
            print(f"  Error for {entry['question_id']}: {repr(e)}")
            predictions.append({
                'question_id': entry['question_id'],
                'question_type': qid2type.get(entry['question_id'], 'unknown'),
                'hypothesis': '',
                'generation_duration_sec': round(time.time() - q_start, 2),
            })

    print(f"\nToken usage — prompt: {total_prompt_tokens}, completion: {total_completion_tokens}")
    return predictions


def get_eval_prompt(task, question, answer, response, abstention=False):
    """Build the LLM-as-judge evaluation prompt (from LongMemEval)."""
    if not abstention:
        if task in ['single-session-user', 'single-session-assistant', 'multi-session']:
            template = (
                "I will give you a question, a correct answer, and a response from a model. "
                "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                "If the response is equivalent to the correct answer or contains all the intermediate "
                "steps to get the correct answer, you should also answer yes. If the response only "
                "contains a subset of the information required by the answer, answer no. "
                "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
        elif task == 'temporal-reasoning':
            template = (
                "I will give you a question, a correct answer, and a response from a model. "
                "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                "If the response is equivalent to the correct answer or contains all the intermediate "
                "steps to get the correct answer, you should also answer yes. If the response only "
                "contains a subset of the information required by the answer, answer no. "
                "In addition, do not penalize off-by-one errors for the number of days. If the question "
                "asks for the number of days/weeks/months, etc., and the model makes off-by-one errors "
                "(e.g., predicting 19 days when the answer is 18), the model's response is still correct. "
                "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
        elif task == 'knowledge-update':
            template = (
                "I will give you a question, a correct answer, and a response from a model. "
                "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                "If the response contains some previous information along with an updated answer, "
                "the response should be considered as correct as long as the updated answer is the "
                "required answer."
                "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
        elif task == 'single-session-preference':
            template = (
                "I will give you a question, a rubric for desired personalized response, and a response "
                "from a model. Please answer yes if the response satisfies the desired response. "
                "Otherwise, answer no. The model does not need to reflect all the points in the rubric. "
                "The response is correct as long as it recalls and utilizes the user's personal information "
                "correctly."
                "\n\nQuestion: {}\n\nRubric: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
        else:
            raise ValueError(f"Unknown question type: {task}")
    else:
        template = (
            "I will give you an unanswerable question, an explanation, and a response from a model. "
            "Please answer yes if the model correctly identifies the question as unanswerable. "
            "The model could say that the information is incomplete, or some other information is "
            "given but the asked information is not."
            "\n\nQuestion: {}\n\nExplanation: {}\n\nModel Response: {}\n\n"
            "Does the model correctly identify the question as unanswerable? Answer yes or no only."
        )
    return template.format(question, answer, response)


def get_explanation_prompt(question, expected_answer, model_response, question_type):
    """Ask the judge to explain why the model's answer is incorrect."""
    return (
        "A model was asked the following question and gave an incorrect response. "
        "Briefly explain why the model's response is wrong (2-3 sentences max)."
        f"\n\nQuestion type: {question_type}"
        f"\n\nQuestion: {question}"
        f"\n\nExpected Answer: {expected_answer}"
        f"\n\nModel Response: {model_response}"
        f"\n\nExplanation:"
    )


def evaluate_predictions(client, predictions, ref_data, eval_model):
    """Run LLM-as-judge evaluation. Returns evaluated entries with judge explanation for incorrect ones."""
    qid2ref = {e['question_id']: e for e in ref_data}
    type2results = {t: [] for t in QUESTION_TYPES}
    evaluated = []

    for entry in tqdm(predictions, desc="Evaluating"):
        qid = entry['question_id']
        if qid not in qid2ref:
            print(f"  Warning: {qid} not in reference data, skipping")
            continue

        ref = qid2ref[qid]
        qtype = ref['question_type']
        question = ref['question']
        answer = str(ref['answer'])
        hypothesis = entry['hypothesis']

        abstention = '_abs' in qid
        prompt = get_eval_prompt(qtype, question, answer, hypothesis, abstention=abstention)

        eval_start = time.time()
        eval_explanation = ""
        try:
            kwargs = {
                'model': eval_model,
                'messages': [{"role": "user", "content": prompt}],
                'n': 1,
                'temperature': 0,
                'max_tokens': 10,
            }
            completion = chat_completions_with_backoff(client, **kwargs)
            eval_response = completion.choices[0].message.content.strip()
            label = 'yes' in eval_response.lower()

            if not label:
                expl_prompt = get_explanation_prompt(question, answer, hypothesis, qtype)
                expl_kwargs = {
                    'model': eval_model,
                    'messages': [{"role": "user", "content": expl_prompt}],
                    'n': 1,
                    'temperature': 0,
                    'max_tokens': 200,
                }
                expl_completion = chat_completions_with_backoff(client, **expl_kwargs)
                eval_explanation = expl_completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"  Eval error for {qid}: {repr(e)}")
            label = False
            eval_explanation = f"Evaluation error: {repr(e)}"

        eval_duration = round(time.time() - eval_start, 2)

        entry['autoeval_label'] = {
            'model': eval_model,
            'label': label,
            'eval_duration_sec': eval_duration,
        }
        if not label:
            entry['autoeval_label']['explanation'] = eval_explanation

        entry['question_type'] = qtype
        entry['question'] = question
        entry['expected_answer'] = answer
        evaluated.append(entry)

        if qtype in type2results:
            type2results[qtype].append({
                'question_id': qid,
                'label': label,
                'generation_duration_sec': entry.get('generation_duration_sec', 0),
                'memory_creation_duration_sec': entry.get('memory_creation_duration_sec', 0),
                'eval_duration_sec': eval_duration,
            })

    return evaluated, type2results


def build_category_records(type2results, evaluated, args, total_execution_time):
    """Build one MongoDB record per question category."""
    experiment_name = os.environ.get("EXPERIMENT_NAME", "")
    records = []

    evaluated_by_qid = {e['question_id']: e for e in evaluated}

    for qtype in QUESTION_TYPES:
        results = type2results.get(qtype, [])
        if not results:
            continue

        correct = sum(1 for r in results if r['label'])
        incorrect = len(results) - correct
        accuracy = round(correct / len(results), 4) if results else 0.0

        total_gen_duration = sum(r['generation_duration_sec'] for r in results)
        total_eval_duration = sum(r['eval_duration_sec'] for r in results)
        total_mem_duration = sum(r.get('memory_creation_duration_sec', 0) for r in results)
        total_duration = round(total_gen_duration + total_eval_duration, 2)
        avg_duration = round(total_duration / len(results), 2) if results else 0.0

        correct_answers = []
        incorrect_answers = []
        for r in results:
            entry = evaluated_by_qid.get(r['question_id'], {})
            answer_record = {
                'question_id': r['question_id'],
                'question': entry.get('question', ''),
                'expected_answer': entry.get('expected_answer', ''),
                'model_answer': entry.get('hypothesis', ''),
                'generation_duration_sec': r['generation_duration_sec'],
                'memory_creation_duration_sec': r.get('memory_creation_duration_sec', 0),
            }
            if r['label']:
                correct_answers.append(answer_record)
            else:
                answer_record['judge_explanation'] = (
                    entry.get('autoeval_label', {}).get('explanation', '')
                )
                incorrect_answers.append(answer_record)

        record = {
            'experiment_name': experiment_name,
            'model': args.model,
            'eval_model': args.eval_model,
            'dataset_name': os.environ.get('DATASET_NAME', 'longmemeval@1.0'),
            'task_name': os.environ.get('TASK_NAME', 'longmemeval'),
            'question_category': qtype,
            'total_questions': len(results),
            'correct_count': correct,
            'incorrect_count': incorrect,
            'accuracy': accuracy,
            'total_duration_sec': total_duration,
            'avg_duration_sec': avg_duration,
            'total_generation_duration_sec': round(total_gen_duration, 2),
            'total_memory_creation_duration_sec': round(total_mem_duration, 2),
            'avg_memory_creation_duration_sec': round(total_mem_duration / len(results), 2) if results else 0.0,
            'avg_generation_duration_sec': round(total_gen_duration / len(results), 2) if results else 0.0,
            'total_eval_duration_sec': round(total_eval_duration, 2),
            'correct_answers': correct_answers,
            'incorrect_answers': incorrect_answers,
            'config': {
                'history_format': args.history_format,
                'cot': args.cot,
                'max_questions': args.max_questions,
                'question_range_start': args.question_range_start,
                'question_range_end': args.question_range_end,
            },
            'total_execution_time_sec': round(total_execution_time, 2),
            'timestamp': datetime.utcnow(),
            'created_at': datetime.utcnow().isoformat(),
        }
        records.append(record)

    return records


def save_to_mongodb(records: List[Dict], db_name: str, connection_string: str) -> bool:
    """Save per-category records to MongoDB."""
    if not records:
        print("Warning: no records to save")
        return False

    try:
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')

        db = client[db_name]
        collection = db["longmemeval_results"]

        result = collection.insert_many(records)
        print(f"\nMongoDB: saved {len(result.inserted_ids)} category records")
        for rec in records:
            print(f"  {rec['question_category']}: "
                  f"accuracy={rec['accuracy']} "
                  f"({rec['correct_count']}/{rec['total_questions']}), "
                  f"avg_duration={rec['avg_duration_sec']}s")

        client.close()
        return True
    except Exception as e:
        print(f"Warning: Failed to save to MongoDB: {str(e)}")
        return False


def print_metrics(type2results):
    """Print accuracy metrics by question type."""
    all_acc = []
    task_acc = []

    has_memory_times = any(
        r.get('memory_creation_duration_sec', 0) > 0
        for results in type2results.values()
        for r in results
    )

    print("\n" + "=" * 60)
    print("Evaluation Results by Question Type")
    print("=" * 60)

    for qtype in QUESTION_TYPES:
        results = type2results.get(qtype, [])
        if results:
            correct = sum(1 for r in results if r['label'])
            acc = round(correct / len(results), 4)
            task_acc.append(acc)
            all_acc.extend([1 if r['label'] else 0 for r in results])

            avg_gen = round(
                sum(r['generation_duration_sec'] for r in results) / len(results), 2
            )
            if has_memory_times:
                avg_mem = round(
                    sum(r.get('memory_creation_duration_sec', 0) for r in results) / len(results), 2
                )
                print(f"  {qtype}: {acc} ({correct}/{len(results)}) "
                      f"— avg memory {avg_mem}s, avg generation {avg_gen}s")
            else:
                avg_eval = round(
                    sum(r['eval_duration_sec'] for r in results) / len(results), 2
                )
                print(f"  {qtype}: {acc} ({correct}/{len(results)}) "
                      f"— avg {round(avg_gen + avg_eval, 2)}s/question")
        else:
            print(f"  {qtype}: N/A (0 questions)")

    if task_acc:
        print(f"\n  Task-averaged Accuracy: {round(np.mean(task_acc), 4)}")
    if all_acc:
        print(f"  Overall Accuracy: {round(np.mean(all_acc), 4)} ({sum(all_acc)}/{len(all_acc)})")
    print("=" * 60)


def main():
    start_time = time.time()
    load_secrets()
    args = parse_args()

    is_pam = args.model.lower() == "pam"

    print("=" * 60)
    print("LongMemEval Benchmark")
    print("=" * 60)
    print(f"  Model: {args.model}" + (" (PAM Agent pipeline)" if is_pam else ""))
    print(f"  Eval model: {args.eval_model}")
    print(f"  Data file: {args.data_file}")
    if not is_pam:
        print(f"  History format: {args.history_format}")
        print(f"  Chain-of-thought: {args.cot}")
    if args.max_questions > 0:
        print(f"  Max questions: {args.max_questions}")
    if args.question_id:
        print(f"  Single question: {args.question_id}")
    if args.question_range_start is not None or args.question_range_end is not None:
        _s = args.question_range_start if args.question_range_start is not None else 1
        _e = args.question_range_end if args.question_range_end is not None else "…"
        print(f"  Question range (1-based): {_s}-{_e}")
    if is_pam and args.debug:
        print(f"  Debug mode: ON")
        if args.debug_user_id is not None:
            print(f"  Debug user_id: {args.debug_user_id}")
    print("=" * 60)

    if is_pam:
        pam_host = os.environ.get("PAM_API_HOST")
        pam_api_user = os.environ.get("PAM_API_USER")
        pam_api_password = os.environ.get("PAM_API_PASSWORD")
        missing = []
        if not pam_host:
            missing.append("PAM_API_HOST")
        if not pam_api_user:
            missing.append("PAM_API_USER")
        if not pam_api_password:
            missing.append("PAM_API_PASSWORD")
        if missing:
            print(f"Error: {', '.join(missing)} not set (required when MODEL=pam)")
            sys.exit(1)
        print(f"  PAM API host: {pam_host}")
        print(f"  PAM admin user: {pam_api_user}")
    else:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            print("Error: OPENAI_API_KEY not set")
            sys.exit(1)

    if not is_pam:
        client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
        tokenizer = tiktoken.get_encoding('o200k_base')

    print(f"\nLoading dataset from {args.data_file}...")
    with open(args.data_file) as f:
        data = json.load(f)
    print(f"Loaded {len(data)} questions")

    qid2type = {e['question_id']: e['question_type'] for e in data}

    if args.question_id:
        data = [e for e in data if e['question_id'] == args.question_id]
        if not data:
            print(f"Error: question_id '{args.question_id}' not found")
            sys.exit(1)
        print(f"Filtered to question: {args.question_id}")

    qrs, qre = args.question_range_start, args.question_range_end
    if qrs is not None or qre is not None:
        n = len(data)
        start_1 = qrs if qrs is not None else 1
        end_1 = qre if qre is not None else n
        if start_1 < 1 or end_1 < 1:
            print("Error: QUESTION_RANGE_START / QUESTION_RANGE_END must be >= 1 (1-based)")
            sys.exit(1)
        if start_1 > end_1:
            print("Error: QUESTION_RANGE_START must be <= QUESTION_RANGE_END")
            sys.exit(1)
        if start_1 > n:
            print(f"Error: QUESTION_RANGE_START ({start_1}) is past dataset size ({n})")
            sys.exit(1)
        if end_1 > n:
            print(f"Warning: QUESTION_RANGE_END ({end_1}) clipped to dataset size ({n})")
            end_1 = n
        # 1-based inclusive → Python slice [start_1 - 1 : end_1]
        data = data[start_1 - 1 : end_1]
        print(f"Question range (1-based): {start_1}-{end_1} → {len(data)} question(s)")

    if args.max_questions > 0:
        data = data[:args.max_questions]
        print(f"Limited to {len(data)} questions")

    os.makedirs(args.out_dir, exist_ok=True)
    predictions_file = os.path.join(args.out_dir, 'longmemeval_predictions.jsonl')
    eval_file = os.path.join(args.out_dir, 'longmemeval_eval_results.jsonl')
    stats_file = os.path.join(args.out_dir, 'longmemeval_stats.json')

    existing_preds = {}
    if os.path.exists(predictions_file) and not args.overwrite:
        with open(predictions_file) as f:
            for line in f:
                entry = json.loads(line)
                existing_preds[entry['question_id']] = entry
        print(f"Loaded {len(existing_preds)} existing predictions")

    to_generate = [e for e in data if e['question_id'] not in existing_preds]
    print(f"Questions to generate: {len(to_generate)} "
          f"(skipping {len(data) - len(to_generate)} existing)")

    if to_generate:
        if is_pam:
            new_predictions = generate_answers_pam(
                pam_host, pam_api_user, pam_api_password,
                to_generate, qid2type,
                debug=args.debug, debug_user_id=args.debug_user_id,
            )
        else:
            new_predictions = generate_answers(client, to_generate, args, tokenizer, qid2type)
        for pred in new_predictions:
            existing_preds[pred['question_id']] = pred

        with open(predictions_file, 'w') as f:
            for pred in existing_preds.values():
                f.write(json.dumps(pred) + '\n')
        print(f"\nPredictions saved to {predictions_file}")

    all_predictions = [
        existing_preds[e['question_id']]
        for e in data
        if e['question_id'] in existing_preds
    ]

    if args.skip_eval:
        print("\nSkipping evaluation (--skip-eval)")
    else:
        eval_api_key = os.environ.get('OPENAI_API_KEY')
        if not eval_api_key:
            print("Error: OPENAI_API_KEY not set (required for LLM-as-judge evaluation)")
            sys.exit(1)
        eval_client = OpenAI(api_key=eval_api_key)

        print(f"\nRunning LLM-as-judge evaluation with {args.eval_model}...")
        evaluated, type2results = evaluate_predictions(
            eval_client, all_predictions, data, args.eval_model
        )

        with open(eval_file, 'w') as f:
            for entry in evaluated:
                f.write(json.dumps(entry, default=str) + '\n')
        print(f"Evaluation results saved to {eval_file}")

        print_metrics(type2results)

        execution_time = time.time() - start_time

        # Build per-category stats for local file
        stats = {
            'model': args.model,
            'eval_model': args.eval_model,
            'history_format': args.history_format,
            'cot': args.cot,
            'max_questions': args.max_questions,
            'question_range_start': args.question_range_start,
            'question_range_end': args.question_range_end,
            'execution_time_seconds': round(execution_time, 2),
            'timestamp': datetime.utcnow().isoformat(),
            'categories': {},
        }
        all_correct = 0
        all_total = 0
        for qtype in QUESTION_TYPES:
            results = type2results.get(qtype, [])
            if results:
                correct = sum(1 for r in results if r['label'])
                total_gen = sum(r['generation_duration_sec'] for r in results)
                total_mem = sum(r.get('memory_creation_duration_sec', 0) for r in results)
                total_eval = sum(r['eval_duration_sec'] for r in results)
                cat_stats = {
                    'total_questions': len(results),
                    'correct_count': correct,
                    'incorrect_count': len(results) - correct,
                    'accuracy': round(correct / len(results), 4),
                    'total_generation_duration_sec': round(total_gen, 2),
                    'avg_generation_duration_sec': round(total_gen / len(results), 2),
                    'total_eval_duration_sec': round(total_eval, 2),
                }
                if total_mem > 0:
                    cat_stats['total_memory_creation_duration_sec'] = round(total_mem, 2)
                    cat_stats['avg_memory_creation_duration_sec'] = round(total_mem / len(results), 2)
                stats['categories'][qtype] = cat_stats
                all_correct += correct
                all_total += len(results)

        stats['overall_accuracy'] = round(all_correct / all_total, 4) if all_total else 0.0
        stats['total_questions'] = all_total
        stats['correct_count'] = all_correct

        with open(stats_file, 'w') as f:
            json.dump(stats, f, indent=2)
        print(f"Statistics saved to {stats_file}")

        # Save to MongoDB (one record per category)
        db_name = os.environ.get("DB_NAME")
        connection_string = os.environ.get("CONNECTION_STRING")
        experiment_name = os.environ.get("EXPERIMENT_NAME")

        if experiment_name and db_name and connection_string:
            records = build_category_records(
                type2results, evaluated, args, execution_time
            )
            save_to_mongodb(records, db_name, connection_string)
        elif not experiment_name:
            print("\nEXPERIMENT_NAME not set, skipping MongoDB save")
        else:
            print("\nMongoDB not fully configured (missing DB_NAME or CONNECTION_STRING), "
                  "skipping save")

    execution_time = time.time() - start_time
    print(f"\nTotal execution time: {execution_time:.1f}s")
    print("Done.")


if __name__ == '__main__':
    main()
