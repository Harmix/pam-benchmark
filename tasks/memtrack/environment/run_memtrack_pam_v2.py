"""
MemTrack PAM v2 Benchmark Runner

Runs the MemTrack benchmark using the PAM API endpoints, similar to the PAM
agent in the LongMemEval task. Key difference: MemTrack creates one memory per
config/event-history and asks multiple questions against it.

Pipeline per config:
  0. Admin login
  1. Create benchmark user account  (skipped when --debug-user-id is set)
  2. Upload event history files      (skipped when --debug-user-id is set)
  3. Create memory via benchmark_memory pipeline (async, polled every 30s)
  4. Answer each benchmark question via SSE chat
  5. Backup workspace                (skipped in --debug mode)
  6. Delete account                  (skipped in --debug mode)

Metrics tracked (same as LongMemEval pam agent):
  - memory_creation_duration_sec (wall time for pipeline, one per config)
  - generation_duration_sec per question
  - injected_tokens per question (from memory retrieval)
  - LLM-as-judge score, confidence, is_correct, reasoning per question

Environment variables:
  PAM_API_HOST        URL of the PAM API (e.g. http://localhost:8000)
  PAM_API_USER        Admin email for PAM login
  PAM_API_PASSWORD    Admin password for PAM login
  OPENAI_API_KEY      Required for LLM-as-judge evaluation
  EXPERIMENT_NAME     MongoDB experiment identifier
  DB_NAME             MongoDB database name
  CONNECTION_STRING   MongoDB connection string
  DEBUG               Set to "true" to enable debug mode
  DEBUG_USER_ID       Reuse an existing PAM user (skips account/memory creation)
  QUESTION_RANGE_START  1-based inclusive start question index
  QUESTION_RANGE_END    1-based inclusive end question index
  TASK_CONFIGS        Comma-separated config names to run (e.g. "config_1,config_2")
  DATASET_NAME        Dataset label stored in MongoDB (default: memtrack@1.0)
  PAM_AGENT_NAME      Agent label stored in MongoDB (default: pam_v2)
  TASK_NAME           Task label stored in MongoDB (default: memtrack)
"""

import builtins
import os
import sys
import json
import time
import argparse
import functools
import io
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Force unbuffered output so progress logs appear immediately in log files.
print = functools.partial(builtins.print, flush=True)

import backoff
import openai
from openai import OpenAI
import requests
import yaml
from pydantic import BaseModel, Field
from pymongo import MongoClient


def load_secrets() -> None:
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
    """Client for the PAM API used when running the pam_v2 benchmark agent.

    Requires an admin login to obtain a token before creating benchmark
    user accounts. Identical to the client in run_longmemeval.py.
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

    MAX_CONSECUTIVE_POLL_ERRORS = 3

    def create_memory(self, max_files: Optional[int] = None, batch_size: int = 500) -> dict:
        """Trigger the memory pipeline and poll until a terminal status is reached.

        Transient poll errors (timeouts, connection drops) are tolerated up to
        MAX_CONSECUTIVE_POLL_ERRORS times in a row before the whole pipeline is
        considered failed.
        """
        run_id = self.trigger_memory_pipeline(max_files=max_files, batch_size=batch_size)
        print(f"        Pipeline triggered (run_id={run_id}), polling every "
              f"{self.MEMORY_POLL_INTERVAL}s ...")

        start = time.time()
        consecutive_errors = 0
        while True:
            time.sleep(self.MEMORY_POLL_INTERVAL)

            try:
                status_resp = self.poll_memory_status()
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                elapsed_min = (time.time() - start) / 60
                print(f"        [{elapsed_min:.1f}m] poll error "
                      f"({consecutive_errors}/{self.MAX_CONSECUTIVE_POLL_ERRORS}): {repr(e)}")
                if consecutive_errors >= self.MAX_CONSECUTIVE_POLL_ERRORS:
                    raise
                continue

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

    def send_message(self, prompt: str, conversation_id: Optional[str] = None) -> Tuple[str, int]:
        """Send a message and return ``(answer_text, injected_tokens)`` from the SSE stream.

        PAM may produce multiple assistant text turns separated by tool-use
        cycles.  Only the final assistant text turn contains the actual answer.

        Turn tracking:
          - ``role "assistant"`` + ``content_new.type "text"`` → append to
            the *current* turn buffer.
          - ``role "tool_use"`` or ``role "tool_result"`` → save the current
            turn and start a fresh buffer (the next assistant text is a new turn).
          - ``role "result"`` / ``event: stream_stopped`` → terminal, stop.

        Returns:
            (answer_text, injected_tokens) where injected_tokens is the number
            of tokens injected from memory retrieval into the answering model
            (0 if not reported by the server).
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
        injected_tokens: int = 0

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
                usage = payload.get("usage") or {}
                injected_tokens = (
                    payload.get("injected_tokens")
                    or usage.get("injected_tokens")
                    or 0
                )
                break

        if current_turn:
            all_turns.append(current_turn)

        for idx, turn in enumerate(all_turns):
            turn_text = "".join(turn)
            print(f"        [SSE turn {idx+1}/{len(all_turns)}] "
                  f"{turn_text[:200]}{'…' if len(turn_text) > 200 else ''}")

        answer = "".join(all_turns[-1]) if all_turns else ""
        print(f"        Injected tokens: {injected_tokens}")
        return answer, injected_tokens


###############################################################################
# Config / Data Loading
###############################################################################

def load_config(config_path: str) -> dict:
    """Load a benchmark YAML config file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def serialize_event_history_files(event_history_path: str, config: dict) -> List[tuple]:
    """Prepare event history and linear config as (filename, bytes) pairs for upload.

    Uploads:
      - event_history.json  — raw event history (Linear + Slack events)
      - linear_config.yaml  — Linear team/user config extracted from the YAML config
                              (omitted if not present)
    """
    file_tuples = []

    # Upload event history JSON
    with open(event_history_path, 'rb') as f:
        file_tuples.append(("event_history.json", f.read()))

    # Upload linear config if present in the config YAML
    linear_config = config.get("linear")
    if linear_config:
        linear_yaml = yaml.dump({"linear": linear_config}, default_flow_style=False)
        file_tuples.append(("linear_config.yaml", linear_yaml.encode("utf-8")))

    return file_tuples


###############################################################################
# PAM Pipeline
###############################################################################

def process_config_pam(
    pam_host: str,
    admin_email: str,
    admin_password: str,
    config_name: str,
    config: dict,
    event_history_path: str,
    questions: List[str],
    debug: bool = False,
    debug_user_id: Optional[int] = None,
    max_questions: int = 0,
    question_range_start: Optional[int] = None,
    question_range_end: Optional[int] = None,
) -> dict:
    """Run the full PAM pipeline for one MemTrack config.

    Unlike LongMemEval (one memory per question), MemTrack creates ONE memory
    per config/event-history and answers MULTIPLE questions against it:

    0. Admin login
    1. Create benchmark user account  (skipped when debug_user_id is set)
    2. Upload event history files      (skipped when debug_user_id is set)
    3. Create memory                   (skipped when debug_user_id is set)
    4. Answer each question via SSE chat
    5. Backup workspace                (skipped in debug mode)
    6. Delete account                  (skipped in debug mode)

    Returns:
        {
            "predictions": list of per-question dicts with hypothesis/timing/injected_tokens,
            "memory_creation_duration_sec": float,
        }
    """
    run_ts = int(time.time())
    email = f"memtrack-{config_name}-{run_ts}@benchmark.local"
    reuse_user = debug_user_id is not None

    print(f"\n[Config: {config_name}]"
          + (f" [DEBUG user_id={debug_user_id}]" if reuse_user else "")
          + (" [DEBUG]" if debug and not reuse_user else ""))
    print(f"  Event history: {event_history_path}")
    print(f"  Questions: {len(questions)}")

    pam = PAMClient(pam_host)
    predictions: List[dict] = []
    memory_creation_sec = 0.0

    try:
        # Step 0: Login
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
            pam.create_account(
                email=email,
                password="benchmark-run",
                name=f"MemTrack {config_name}",
            )
            print(f"        user_id={pam.user_id}")

            # Step 2: Upload event history files
            file_tuples = serialize_event_history_files(event_history_path, config)
            num_batches = math.ceil(len(file_tuples) / PAMClient.MAX_FILES_PER_REQUEST)
            print(f"  [2/6] Uploading {len(file_tuples)} file(s) ({num_batches} batches) ...")
            upload_results = pam.upload_generic_files(file_tuples)
            print(f"        Uploaded {len(upload_results)} files")

            # Step 3: Create memory (timed separately)
            print(f"  [3/6] Creating memory (this may take a while) ...")
            mem_start = time.time()
            mem_result = pam.create_memory()
            memory_creation_sec = round(time.time() - mem_start, 2)
            print(f"        Memory created: {mem_result.get('message', 'ok')} "
                  f"({memory_creation_sec}s)")

        # Build ordered question list with original 0-based indices
        q_items: List[Tuple[int, str]] = list(enumerate(questions))

        # Apply question range filter (1-based inclusive)
        if question_range_start is not None or question_range_end is not None:
            n = len(q_items)
            start_1 = question_range_start if question_range_start is not None else 1
            end_1 = question_range_end if question_range_end is not None else n
            if start_1 < 1 or end_1 < 1:
                print("Warning: QUESTION_RANGE indices must be >= 1 (1-based)")
            else:
                if end_1 > n:
                    print(f"Warning: QUESTION_RANGE_END ({end_1}) clipped to {n}")
                    end_1 = n
                q_items = q_items[start_1 - 1:end_1]
                print(f"  Question range (1-based): {start_1}-{end_1} → {len(q_items)} question(s)")

        # Limit to max_questions
        if max_questions > 0:
            q_items = q_items[:max_questions]
            print(f"  Limited to {len(q_items)} question(s)")

        # Step 4: Answer each question
        total_q = len(q_items)
        for q_pos, (q_idx, question) in enumerate(q_items):
            print(f"\n  [4/6] Question {q_pos + 1}/{total_q} (idx={q_idx}): "
                  f"{question[:80]}{'…' if len(question) > 80 else ''}")
            prompt = f"Question: {question}\nAnswer:"
            gen_start = time.time()
            try:
                answer, injected_tokens = pam.send_message(prompt)
            except Exception as e:
                print(f"        ERROR sending message: {repr(e)}")
                answer, injected_tokens = "", 0
            generation_sec = round(time.time() - gen_start, 2)
            print(f"        Answer ({generation_sec}s): "
                  f"{answer[:200]}{'…' if len(answer) > 200 else ''}")
            predictions.append({
                "question_idx": q_idx,
                "question": question,
                "hypothesis": answer.strip(),
                "generation_duration_sec": generation_sec,
                "injected_tokens": injected_tokens,
            })

        if not debug:
            # Step 5: Backup workspace
            print(f"\n  [5/6] Backing up workspace ...")
            backup = pam.backup_workspace()
            print(f"        Backup: {backup.get('backup_path', 'done')}")
        else:
            print(f"\n  [5/6] Skipping backup (debug)")

    except Exception as e:
        print(f"  ERROR in PAM pipeline: {repr(e)}")

    finally:
        if not debug and pam.user_id:
            try:
                print(f"  [6/6] Deleting account (user_id={pam.user_id}) ...")
                pam.delete_account()
                print(f"        Account deleted")
            except Exception as ex:
                print(f"        Warning: cleanup failed: {repr(ex)}")
        elif debug:
            print(f"  [6/6] Skipping account deletion (debug)")

    return {
        "predictions": predictions,
        "memory_creation_duration_sec": memory_creation_sec,
    }


###############################################################################
# LLM-as-Judge Evaluation
###############################################################################

class EvaluationResult(BaseModel):
    """Pydantic model for LLM judge evaluation result."""
    score: float = Field(ge=0.0, le=1.0, description="Score between 0.0 and 1.0")
    is_correct: bool = Field(description="Whether the answer is correct")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the evaluation")
    reasoning: str = Field(description="Brief explanation of the evaluation")


JUDGE_SYSTEM_PROMPT = """You are evaluating whether an AI agent correctly answered a memory-related question
about a workplace event timeline (Linear tickets and Slack messages).

QUESTION: {question}
EXPECTED ANSWER: {expected_answer}
AGENT'S ANSWER: {agent_answer}

Determine if the agent's answer is correct. Consider:
1. Exact matches are obviously correct
2. Semantic equivalence (same meaning, different wording)
3. Partial correctness (got part of a multi-part answer right)
4. Reasonable interpretations of ambiguous questions

Examples:
- If expected "done" and agent said "completed": score 1.0, correct true
- If expected "alice, bob" and agent said "alice": score 0.5, correct false
- If expected "in_progress, charlie" and agent said "in_progress, urgent, charlie": score 1.0, correct true (extra info OK)
- If completely wrong: score 0.0, correct false"""


@backoff.on_exception(backoff.constant, (openai.RateLimitError, openai.APIError), interval=5, max_tries=3)
def _call_llm_judge_api(client: OpenAI, model: str, system_prompt: str) -> EvaluationResult:
    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Please evaluate this answer."},
        ],
        text_format=EvaluationResult,
    )
    return response.output_parsed


def call_llm_judge(
    client: OpenAI,
    question: str,
    expected_answer: str,
    agent_answer: str,
    model: str,
) -> dict:
    """Evaluate one Q&A pair with the LLM judge. Returns score/is_correct/confidence/reasoning."""
    system_prompt = JUDGE_SYSTEM_PROMPT.format(
        question=question,
        expected_answer=expected_answer,
        agent_answer=agent_answer,
    )
    try:
        result = _call_llm_judge_api(client, model, system_prompt)
        return result.model_dump()
    except Exception as e:
        return {
            "score": 0.0,
            "is_correct": False,
            "confidence": 0.0,
            "reasoning": f"Evaluation error: {repr(e)}",
        }


def evaluate_predictions(
    client: OpenAI,
    predictions: List[dict],
    expected_answers: List[str],
    eval_model: str,
) -> List[dict]:
    """Evaluate all Q&A predictions with LLM-as-judge."""
    evaluated = []
    for pred in predictions:
        q_idx = pred["question_idx"]
        question = pred["question"]
        hypothesis = pred.get("hypothesis", "")
        expected = str(expected_answers[q_idx]) if q_idx < len(expected_answers) else ""

        print(f"  Evaluating Q{q_idx + 1}: {question[:60]}{'…' if len(question) > 60 else ''}")
        eval_start = time.time()
        judge = call_llm_judge(client, question, expected, hypothesis, eval_model)
        eval_duration = round(time.time() - eval_start, 2)

        status = "✓" if judge["is_correct"] else "✗"
        print(f"    {status} score={judge['score']:.2f} confidence={judge['confidence']:.2f}")

        evaluated.append({
            **pred,
            "expected_answer": expected,
            "is_correct": judge["is_correct"],
            "score": judge["score"],
            "confidence": judge["confidence"],
            "reasoning": judge["reasoning"],
            "eval_duration_sec": eval_duration,
        })
    return evaluated


###############################################################################
# MongoDB Output
###############################################################################

def build_config_record(
    config_name: str,
    evaluated: List[dict],
    memory_creation_sec: float,
    execution_time: float,
) -> dict:
    """Build the MongoDB document for one evaluated config.

    Fields mirror those produced by the LongMemEval pam agent so the same
    report generator can display PAM-specific metrics.
    """
    total = len(evaluated)
    correct = sum(1 for r in evaluated if r.get("is_correct", False))
    avg_score = sum(r.get("score", 0.0) for r in evaluated) / total if total else 0.0
    avg_confidence = sum(r.get("confidence", 0.0) for r in evaluated) / total if total else 0.0
    accuracy = round(correct / total, 4) if total else 0.0

    total_gen_sec = sum(r.get("generation_duration_sec", 0.0) for r in evaluated)
    total_eval_sec = sum(r.get("eval_duration_sec", 0.0) for r in evaluated)
    total_injected = sum(r.get("injected_tokens", 0) for r in evaluated)

    incorrect_responses = [
        {
            "question_num": r["question_idx"] + 1,
            "question": r["question"],
            "expected_answer": r.get("expected_answer", ""),
            "agent_answer": r.get("hypothesis", ""),
            "score": r.get("score", 0.0),
            "reasoning": r.get("reasoning", ""),
        }
        for r in evaluated
        if not r.get("is_correct", False)
    ]

    return {
        "experiment_name": os.environ.get("EXPERIMENT_NAME", ""),
        "config_name": config_name,
        "dataset_name": os.environ.get("DATASET_NAME", "memtrack@1.0"),
        "agent_name": os.environ.get("PAM_AGENT_NAME", "pam_v2"),
        "task_name": os.environ.get("TASK_NAME", "memtrack"),
        "total_questions": total,
        "correct_count": correct,
        "incorrect_count": total - correct,
        "accuracy": accuracy,
        "avg_score": avg_score,
        "avg_confidence": avg_confidence,
        "execution_time_seconds": round(execution_time, 2),
        # PAM-specific timing / token metrics (same fields as LongMemEval)
        "total_memory_creation_duration_sec": round(memory_creation_sec, 2),
        "avg_memory_creation_duration_sec": round(memory_creation_sec, 2),  # one memory per config
        "total_generation_duration_sec": round(total_gen_sec, 2),
        "avg_generation_duration_sec": round(total_gen_sec / total, 2) if total else 0.0,
        "total_eval_duration_sec": round(total_eval_sec, 2),
        "total_injected_tokens": total_injected,
        "avg_injected_tokens": round(total_injected / total, 1) if total else 0.0,
        "incorrect_responses": incorrect_responses,
        "timestamp": datetime.utcnow(),
        "created_at": datetime.utcnow().isoformat(),
    }


def save_to_mongodb(record: dict, db_name: str, connection_string: str) -> bool:
    """Save one config record to the evaluation_results MongoDB collection."""
    try:
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[db_name]
        collection = db["evaluation_results"]
        result = collection.insert_one(record)
        print(f"✓ MongoDB: saved config '{record['config_name']}' "
              f"(accuracy={record['accuracy']}, id={result.inserted_id})")
        client.close()
        return True
    except Exception as e:
        print(f"⚠ Warning: Failed to save to MongoDB: {str(e)}")
        return False


###############################################################################
# CLI / Main
###############################################################################

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run MemTrack benchmark with PAM API (pam_v2 agent)"
    )
    parser.add_argument(
        "--configs-dir", type=str, default="/task_data/test_configs",
        help="Directory containing config YAML files",
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Process a single config by name (without .yaml extension)",
    )
    parser.add_argument(
        "--task-data-dir", type=str, default="/task_data",
        help="Base directory for task data (event histories, etc.)",
    )
    parser.add_argument(
        "--out-dir", type=str, default="/outputs",
        help="Directory for prediction and evaluation output files",
    )
    parser.add_argument(
        "--eval-model", type=str, default="gpt-4o",
        help="Model for LLM-as-judge evaluation",
    )
    parser.add_argument(
        "--max-questions", type=int, default=0,
        help="Max questions to process per config (0 = all)",
    )
    parser.add_argument(
        "--question-range-start", type=int, default=None,
        help="1-based inclusive start question index per config",
    )
    parser.add_argument(
        "--question-range-end", type=int, default=None,
        help="1-based inclusive end question index per config",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Regenerate predictions even if a predictions file already exists",
    )
    parser.add_argument(
        "--skip-eval", action="store_true",
        help="Skip LLM-as-judge evaluation step",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Debug mode: skip workspace backup and account deletion",
    )
    parser.add_argument(
        "--debug-user-id", type=int, default=None,
        help="Debug: reuse an existing PAM user (skips account creation, file upload, memory creation)",
    )

    args = parser.parse_args()

    # Override from environment variables (same pattern as run_longmemeval.py)
    if os.environ.get("DEBUG", "").lower() in ("true", "1"):
        args.debug = True
    env_debug_uid = os.environ.get("DEBUG_USER_ID", "").strip()
    if env_debug_uid and args.debug_user_id is None:
        args.debug_user_id = int(env_debug_uid)

    env_qrs = os.environ.get("QUESTION_RANGE_START", "").strip()
    env_qre = os.environ.get("QUESTION_RANGE_END", "").strip()
    if env_qrs and args.question_range_start is None:
        args.question_range_start = int(env_qrs)
    if env_qre and args.question_range_end is None:
        args.question_range_end = int(env_qre)

    return args


def print_metrics(all_config_results: Dict[str, Optional[dict]]) -> None:
    """Print evaluation metrics across all processed configs."""
    print("\n" + "=" * 60)
    print("Evaluation Results by Config")
    print("=" * 60)

    total_correct = 0
    total_questions = 0

    for config_name, result in all_config_results.items():
        if result is None:
            print(f"  {config_name}: ERROR (no result)")
            continue

        evaluated = result.get("evaluated", [])
        mem_sec = result.get("memory_creation_duration_sec", 0.0)

        if not evaluated:
            print(f"  {config_name}: N/A (0 questions evaluated)")
            continue

        total = len(evaluated)
        correct = sum(1 for r in evaluated if r.get("is_correct", False))
        acc = round(correct / total, 4)
        avg_gen = round(sum(r.get("generation_duration_sec", 0) for r in evaluated) / total, 2)
        avg_injected = round(sum(r.get("injected_tokens", 0) for r in evaluated) / total, 1)

        print(f"  {config_name}: {acc:.4f} ({correct}/{total}) "
              f"— memory {mem_sec}s, avg_gen {avg_gen}s, avg_injected {avg_injected} tok")

        total_correct += correct
        total_questions += total

    if total_questions > 0:
        overall_acc = round(total_correct / total_questions, 4)
        print(f"\n  Overall Accuracy: {overall_acc:.4f} ({total_correct}/{total_questions})")
    print("=" * 60)


def main() -> None:
    start_time = time.time()
    load_secrets()
    args = parse_args()

    print("=" * 60)
    print("MemTrack PAM v2 Benchmark Runner")
    print("=" * 60)
    print(f"  Configs dir: {args.configs_dir}")
    print(f"  Task data dir: {args.task_data_dir}")
    print(f"  Output dir: {args.out_dir}")
    print(f"  Eval model: {args.eval_model}")
    if args.config:
        print(f"  Config filter: {args.config}")
    if args.max_questions > 0:
        print(f"  Max questions: {args.max_questions}")
    if args.question_range_start is not None or args.question_range_end is not None:
        _s = args.question_range_start or 1
        _e = args.question_range_end or "…"
        print(f"  Question range (1-based): {_s}-{_e}")
    if args.debug:
        print(f"  Debug mode: ON")
        if args.debug_user_id is not None:
            print(f"  Debug user_id: {args.debug_user_id}")
    print("=" * 60)

    # Validate PAM credentials
    pam_host = os.environ.get("PAM_API_HOST")
    pam_api_user = os.environ.get("PAM_API_USER")
    pam_api_password = os.environ.get("PAM_API_PASSWORD")
    missing = [k for k, v in [
        ("PAM_API_HOST", pam_host),
        ("PAM_API_USER", pam_api_user),
        ("PAM_API_PASSWORD", pam_api_password),
    ] if not v]
    if missing:
        print(f"Error: {', '.join(missing)} not set (required for pam_v2 agent)")
        sys.exit(1)
    print(f"  PAM API host: {pam_host}")
    print(f"  PAM admin user: {pam_api_user}")

    # Validate OpenAI key (needed for evaluation)
    eval_client = None
    if not args.skip_eval:
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            print("Error: OPENAI_API_KEY not set (required for LLM-as-judge evaluation)")
            sys.exit(1)
        eval_client = OpenAI(api_key=openai_api_key)

    # Discover config files
    configs_dir = Path(args.configs_dir)
    if not configs_dir.exists():
        print(f"Error: configs directory not found: {configs_dir}")
        sys.exit(1)

    # Priority: --config arg > TASK_CONFIGS env var > all *.yaml in configs_dir
    if args.config:
        config_files = [configs_dir / f"{args.config}.yaml"]
    else:
        task_configs_env = os.environ.get("TASK_CONFIGS", "").strip()
        if task_configs_env:
            config_names = [c.strip() for c in task_configs_env.split(",") if c.strip()]
            config_files = [configs_dir / f"{name}.yaml" for name in config_names]
        else:
            config_files = sorted(configs_dir.glob("*.yaml"))

    if not config_files:
        print("Error: No config files to process")
        sys.exit(1)

    print(f"\nConfigs to process ({len(config_files)}): {[f.stem for f in config_files]}")

    os.makedirs(args.out_dir, exist_ok=True)

    all_config_results: Dict[str, Optional[dict]] = {}

    for config_file in config_files:
        if not config_file.exists():
            print(f"\nError: Config file not found: {config_file}")
            all_config_results[config_file.stem] = None
            continue

        config_name = config_file.stem
        print(f"\n{'=' * 60}")
        print(f"Config: {config_name}")
        print(f"{'=' * 60}")

        # Load YAML config
        config = load_config(str(config_file))
        benchmark = config.get("benchmark", {})
        questions = benchmark.get("questions", [])
        expected_answers = benchmark.get("expected_answers", [])
        event_history_rel = benchmark.get("event_history", "")
        event_history_path = os.path.join(args.task_data_dir, event_history_rel)

        if not questions:
            print(f"No questions found in config, skipping")
            all_config_results[config_name] = None
            continue

        if not event_history_rel:
            print(f"No event_history path in config, skipping")
            all_config_results[config_name] = None
            continue

        if not os.path.exists(event_history_path):
            print(f"Event history not found: {event_history_path}")
            all_config_results[config_name] = None
            continue

        print(f"  Questions: {len(questions)}")
        print(f"  Event history: {event_history_path}")
        if expected_answers:
            print(f"  Expected answers: {len(expected_answers)}")

        # Load existing predictions if not overwriting
        predictions_file = Path(args.out_dir) / f"{config_name}_pam_v2_predictions.jsonl"
        memory_creation_sec = 0.0
        predictions: List[dict] = []

        if predictions_file.exists() and not args.overwrite:
            with open(predictions_file) as f:
                for line in f:
                    predictions.append(json.loads(line))
            print(f"Loaded {len(predictions)} existing predictions from {predictions_file}")

        config_start = time.time()

        if not predictions:
            # Run PAM pipeline
            result = process_config_pam(
                pam_host=pam_host,
                admin_email=pam_api_user,
                admin_password=pam_api_password,
                config_name=config_name,
                config=config,
                event_history_path=event_history_path,
                questions=questions,
                debug=args.debug,
                debug_user_id=args.debug_user_id,
                max_questions=args.max_questions,
                question_range_start=args.question_range_start,
                question_range_end=args.question_range_end,
            )
            predictions = result["predictions"]
            memory_creation_sec = result["memory_creation_duration_sec"]

            # Save predictions to file
            with open(predictions_file, 'w') as f:
                for pred in predictions:
                    f.write(json.dumps(pred) + '\n')
            print(f"\nPredictions saved to {predictions_file}")

        config_execution_time = round(time.time() - config_start, 2)

        if args.skip_eval or not predictions:
            print("\nSkipping evaluation")
            all_config_results[config_name] = {
                "evaluated": [],
                "memory_creation_duration_sec": memory_creation_sec,
            }
            continue

        # Evaluate with LLM-as-judge
        print(f"\nEvaluating {len(predictions)} prediction(s) with {args.eval_model}...")
        evaluated = evaluate_predictions(eval_client, predictions, expected_answers, args.eval_model)

        # Save evaluation results to file
        eval_file = Path(args.out_dir) / f"{config_name}_pam_v2_eval.jsonl"
        with open(eval_file, 'w') as f:
            for entry in evaluated:
                f.write(json.dumps(entry, default=str) + '\n')
        print(f"Evaluation results saved to {eval_file}")

        all_config_results[config_name] = {
            "evaluated": evaluated,
            "memory_creation_duration_sec": memory_creation_sec,
        }

        # Build and save MongoDB record
        record = build_config_record(
            config_name, evaluated, memory_creation_sec, config_execution_time
        )

        db_name = os.environ.get("DB_NAME")
        connection_string = os.environ.get("CONNECTION_STRING")
        experiment_name = os.environ.get("EXPERIMENT_NAME")

        if experiment_name and db_name and connection_string:
            save_to_mongodb(record, db_name, connection_string)
        elif not experiment_name:
            print("\nEXPERIMENT_NAME not set, skipping MongoDB save")
        else:
            print("\nMongoDB not fully configured (missing DB_NAME or CONNECTION_STRING), skipping save")

    # Print overall summary
    print_metrics(all_config_results)

    total_execution_time = time.time() - start_time
    print(f"\nTotal execution time: {total_execution_time:.1f}s")
    print("Done.")


if __name__ == "__main__":
    main()
