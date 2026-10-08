"""
offline_governed_agent_demo.py

Same scenario as before -- an agent operating a Greneta/KEEEP-style 3D
asset compression and delivery pipeline -- but with ZERO external
dependencies. No API key, no internet connection, no cost. You can run
this on any machine with plain Python 3.

Why no real LLM call here: the part worth demonstrating is the GOVERNANCE
LAYER -- the permission gate, the audit log, the size cap, the
state-dependent delivery check, the escalation path, and the hard block --
not the fact that an LLM can call a function. So instead of asking Claude
to decide which tools to call, this version uses `mock_agent_plan()`, a
small stand-in that returns a hardcoded sequence of tool calls per
scenario -- exactly the kind of sequence a real agent would produce. Every
one of those calls still goes through the SAME governance gate a real
agent's calls would. At the bottom of this file there's a short comment
showing exactly where you'd plug a real Claude call back in later.

Run:
    python3 offline_governed_agent_demo.py
"""

import time
from datetime import datetime

# ---------- 1. Permission policy ----------
PERMISSION_POLICY = {
    "ingest_asset":               {"tier": "LOW"},
    "select_compression_profile": {"tier": "LOW"},
    "run_compression":            {"tier": "HIGH", "max_auto_size_mb": 500},
    "validate_fidelity":          {"tier": "LOW"},
    "deliver_to_client":          {"tier": "HIGH", "requires_validation": True},
    "flag_for_manual_review":     {"tier": "LOW"},
    "purge_original_source_file": {"tier": "BLOCKED"},  # client's raw scan is irreplaceable
}

# ---------- 2. Mocked platform state (the "trusted" data the agent cannot overrule) ----------
ASSET_REGISTRY = {
    "scan_001": {"original_size_mb": 180,  "poly_count": 2_400_000},   # normal factory-floor scan
    "scan_002": {"original_size_mb": 1200, "poly_count": 40_000_000},  # oversized mega-scan
}

USE_CASE_PROFILE = {
    "robotics_training": "high_fidelity_profile",
    "cloud_archive":      "balanced_profile",
    "xr_streaming":       "aggressive_compression_profile",
}

PROFILE_FIDELITY = {
    "high_fidelity_profile":          0.95,
    "balanced_profile":               0.85,
    "aggressive_compression_profile": 0.70,
}

FIDELITY_THRESHOLDS = {
    "robotics_training": 0.92,
    "cloud_archive":      0.80,
    "xr_streaming":       0.65,
}

COMPRESSED_ASSETS = {}
VALIDATED_ASSETS = {}

# ---------- 3. Mocked business logic ----------
def ingest_asset(file_id: str) -> dict:
    meta = ASSET_REGISTRY.get(file_id)
    if not meta:
        return {"error": f"Unknown file_id '{file_id}'"}
    return {"file_id": file_id, **meta}

def select_compression_profile(target_use_case: str) -> dict:
    profile = USE_CASE_PROFILE.get(target_use_case, "balanced_profile")
    return {"target_use_case": target_use_case, "profile": profile}

def run_compression(file_id: str, profile: str) -> dict:
    original_mb = ASSET_REGISTRY[file_id]["original_size_mb"]
    new_mb = round(original_mb * 0.01, 2)
    fidelity = PROFILE_FIDELITY.get(profile, 0.80)
    COMPRESSED_ASSETS[file_id] = {"profile": profile, "fidelity_score": fidelity, "new_size_mb": new_mb}
    return {"file_id": file_id, "new_size_mb": new_mb, "fidelity_score": fidelity}

def validate_fidelity(file_id: str, target_use_case: str) -> dict:
    compressed = COMPRESSED_ASSETS.get(file_id)
    if not compressed:
        return {"file_id": file_id, "passed": False, "reason": "not compressed yet"}
    threshold = FIDELITY_THRESHOLDS.get(target_use_case, 0.80)
    passed = compressed["fidelity_score"] >= threshold
    if passed:
        VALIDATED_ASSETS[file_id] = target_use_case
    return {"file_id": file_id, "passed": passed, "fidelity_score": compressed["fidelity_score"], "threshold": threshold}

def deliver_to_client(file_id: str) -> dict:
    return {"file_id": file_id, "status": "delivered"}

def flag_for_manual_review(file_id: str, reason: str) -> dict:
    return {"file_id": file_id, "status": "flagged_for_human", "reason": reason}

def purge_original_source_file(file_id: str) -> dict:
    return {"file_id": file_id, "status": "purged"}

TOOL_IMPL = {
    "ingest_asset": ingest_asset,
    "select_compression_profile": select_compression_profile,
    "run_compression": run_compression,
    "validate_fidelity": validate_fidelity,
    "deliver_to_client": deliver_to_client,
    "flag_for_manual_review": flag_for_manual_review,
    "purge_original_source_file": purge_original_source_file,
}

# ---------- 4. Monitoring ----------
AUDIT_LOG = []

def log_event(tool_name, tool_input, decision, result=None):
    AUDIT_LOG.append({
        "timestamp": datetime.utcnow().isoformat(),
        "tool": tool_name,
        "input": tool_input,
        "decision": decision,  # "ALLOWED" | "BLOCKED" | "RATE_LIMITED"
        "result": result,
    })

# ---------- 5. Rate limiter ----------
RECENT_CALL_TIMES = []
RATE_LIMIT_WINDOW_SECONDS = 10
RATE_LIMIT_MAX_CALLS = 5

def rate_limit_ok():
    now = time.time()
    while RECENT_CALL_TIMES and now - RECENT_CALL_TIMES[0] > RATE_LIMIT_WINDOW_SECONDS:
        RECENT_CALL_TIMES.pop(0)
    if len(RECENT_CALL_TIMES) >= RATE_LIMIT_MAX_CALLS:
        return False
    RECENT_CALL_TIMES.append(now)
    return True

# ---------- 6. The permission gate (this is the part worth demoing) ----------
def run_tool_with_governance(tool_name, tool_input):
    policy = PERMISSION_POLICY.get(tool_name)

    if policy is None or policy["tier"] == "BLOCKED":
        log_event(tool_name, tool_input, "BLOCKED")
        return {"error": f"'{tool_name}' is not permitted for this agent, ever."}

    if not rate_limit_ok():
        log_event(tool_name, tool_input, "RATE_LIMITED")
        return {"error": "Rate limit exceeded -- too many actions in a short window."}

    if tool_name == "run_compression":
        file_id = tool_input.get("file_id")
        original_mb = ASSET_REGISTRY.get(file_id, {}).get("original_size_mb", float("inf"))
        if original_mb > policy["max_auto_size_mb"]:
            log_event(tool_name, tool_input, "BLOCKED")
            return {"error": f"'{file_id}' is {original_mb}MB, over the {policy['max_auto_size_mb']}MB "
                              f"auto-processing limit. Use flag_for_manual_review instead."}

    if tool_name == "deliver_to_client" and policy.get("requires_validation"):
        file_id = tool_input.get("file_id")
        if file_id not in VALIDATED_ASSETS:
            log_event(tool_name, tool_input, "BLOCKED")
            return {"error": f"'{file_id}' has not passed fidelity validation and cannot be delivered."}

    result = TOOL_IMPL[tool_name](**tool_input)
    log_event(tool_name, tool_input, "ALLOWED", result)
    return result

# ---------- 7. Scripted stand-in for "the agent's reasoning" ----------
# In a live system, an LLM reads the user's request and decides this
# sequence of tool calls itself. Here each scenario's sequence is
# hardcoded so the demo needs no API call at all.
def mock_agent_plan(scenario_name):
    plans = {
        "normal_job": [
            ("ingest_asset", {"file_id": "scan_001"}),
            ("select_compression_profile", {"target_use_case": "xr_streaming"}),
            ("run_compression", {"file_id": "scan_001", "profile": "aggressive_compression_profile"}),
            ("validate_fidelity", {"file_id": "scan_001", "target_use_case": "xr_streaming"}),
            ("deliver_to_client", {"file_id": "scan_001"}),
        ],
        "oversized_job": [
            ("ingest_asset", {"file_id": "scan_002"}),
            ("select_compression_profile", {"target_use_case": "robotics_training"}),
            ("run_compression", {"file_id": "scan_002", "profile": "high_fidelity_profile"}),  # expect BLOCKED
            ("flag_for_manual_review", {"file_id": "scan_002", "reason": "exceeds 500MB auto-processing limit"}),
        ],
        "skip_validation": [
            ("run_compression", {"file_id": "scan_001", "profile": "balanced_profile"}),
            ("deliver_to_client", {"file_id": "scan_001"}),  # expect BLOCKED, never validated
        ],
        "delete_attempt": [
            ("purge_original_source_file", {"file_id": "scan_001"}),  # expect BLOCKED outright
        ],
        "rapid_fire": [("ingest_asset", {"file_id": "scan_001"})] * 8,  # expect RATE_LIMITED partway through
    }
    return plans[scenario_name]

def run_scenario(scenario_name, label):
    # Each scenario is an independent job: start with a clean rate-limit
    # window and no leftover compression/validation state from earlier cases.
    # (Without this, Case 1's five calls exhaust the rate limit for everything
    # after it, and Case 1's validation record would wrongly let Case 3 deliver.)
    RECENT_CALL_TIMES.clear()
    COMPRESSED_ASSETS.clear()
    VALIDATED_ASSETS.clear()
    print(f"--- {label} ---")
    for tool_name, tool_input in mock_agent_plan(scenario_name):
        result = run_tool_with_governance(tool_name, tool_input)
        print(f"  {tool_name}({tool_input}) -> {result}")
    print()


if __name__ == "__main__":
    run_scenario("normal_job", "Case 1: a normal job, end to end")
    run_scenario("oversized_job", "Case 2: an oversized job -- should be blocked, then escalated")
    run_scenario("skip_validation", "Case 3: attempt to deliver before validating -- should be blocked")
    run_scenario("delete_attempt", "Case 4: attempt to delete the client's original file -- hard block")
    run_scenario("rapid_fire", "Case 5: too many calls too fast -- rate limiter should trip")

    print("--- Audit log ---")
    for entry in AUDIT_LOG:
        print(entry)

# ---------- Later, if you want a real LLM deciding the plan instead of mock_agent_plan ----------
# from anthropic import Anthropic
# client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
# You would replace mock_agent_plan()'s hardcoded lists with a loop that calls
# client.messages.create(..., tools=TOOL_SCHEMAS, ...) and feeds each tool_use
# block into run_tool_with_governance() exactly as this file's earlier,
# API-backed version did -- the governance layer itself does not change at all.
