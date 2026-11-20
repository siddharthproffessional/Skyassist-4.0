"""Generates the five importable n8n workflow exports (A–E) in n8n/workflows/.

No credentials or secrets are embedded: the SkyAssist API base URL, service token and HMAC secret are read at
run time with n8n `$env` expressions. Each workflow:
  Webhook (raw JSON) → Code: verify inbound HMAC + build signed request → HTTP Request to SkyAssist API
  → Respond to Webhook with SkyAssist's (deterministic) result.
n8n orchestrates only; every decision is made by SkyAssist's Python services.
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "workflows"

VERIFY_AND_SIGN = r"""
// SkyAssist: verify the inbound HMAC, then sign the outbound call. Requires NODE_FUNCTION_ALLOW_BUILTIN=crypto
const crypto = require('crypto');
const secret = $env.SKYASSIST_WEBHOOK_SECRET;
if (!secret) { throw new Error('SKYASSIST_WEBHOOK_SECRET is not set - refusing (fail closed)'); }
const item = $input.first().json;
const inbound = JSON.stringify(item.body);
const given = (item.headers || {})['x-skyassist-signature'] || '';
const expected = crypto.createHmac('sha256', secret).update(inbound).digest('hex');
if (given.length !== expected.length ||
    !crypto.timingSafeEqual(Buffer.from(given), Buffer.from(expected))) {
  throw new Error('Inbound signature invalid - event rejected');
}
const payload = __PAYLOAD__;
const bodyString = JSON.stringify(payload);
return [{ json: {
  bodyString,
  signature: crypto.createHmac('sha256', secret).update(bodyString).digest('hex'),
  idempotencyKey: (item.headers || {})['x-idempotency-key'] || ('n8n-' + $execution.id),
  executionId: String($execution.id),
} }];
"""

WORKFLOWS = {
    "A": ("SkyAssist A - Disruption rebooking intake", "skyassist/disruption", "/v1/rebooking/jobs",
          "{ disrupted_flight: item.body.disrupted_flight, target_flight: item.body.target_flight, run: true }",
          "U-4.1 - creates a priority-first, batched rebooking job; vulnerable passengers are processed first."),
    "B": ("SkyAssist B - Crew message intake", "skyassist/crew-message", "/v1/crew/messages",
          "{ flight_no: item.body.flight_no, sender: String(item.body.sender || 'crew channel'), "
          "body: String(item.body.body || '') }",
          "U-4.2 - forwards crew-channel text as untrusted data; SkyAssist validates duty legality deterministically."),
    "C": ("SkyAssist C - Maintenance sign-off intake", "skyassist/maintenance-signoff", "/v1/maintenance/signoffs",
          "{ engineer_id: item.body.engineer_id, defect_id: item.body.defect_id, reg: item.body.reg, "
          "task_scope: item.body.task_scope, result: item.body.result, signed_at_utc: item.body.signed_at_utc, "
          "evidence_ref: item.body.evidence_ref }",
          "U-4.3 - submits a sign-off for validation; an invalid one keeps the aircraft blocked."),
    "D": ("SkyAssist D - Baggage feasibility check", "skyassist/baggage-check", "/v1/baggage/feasibility",
          "{ booking_ref: item.body.booking_ref, candidate_flight: item.body.candidate_flight }",
          "U-4.4 - read-only feasibility (passenger vs bag connection); commits happen only in SkyAssist."),
    "E": ("SkyAssist E - State change revalidation", "skyassist/state-change", "/v1/state-changes",
          "{ resources: (item.body.payload && item.body.payload.resources) || item.body.resources, "
          "reason: 'n8n workflow E' }",
          "U-4.5 - receives SkyAssist outbox state-change events and asks SkyAssist to mark affected approvals stale."),
}


def build(code, name, path, api_path, payload_js, note):
    wid = f"skyassist-{code.lower()}"
    nodes = [
        {"id": f"{wid}-hook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
         "position": [0, 0], "webhookId": f"{wid}-hook",
         "parameters": {"httpMethod": "POST", "path": path, "responseMode": "responseNode", "options": {}}},
        {"id": f"{wid}-sign", "name": "Verify and sign", "type": "n8n-nodes-base.code", "typeVersion": 2,
         "position": [240, 0],
         "parameters": {"jsCode": VERIFY_AND_SIGN.replace("__PAYLOAD__", payload_js).strip()}},
        {"id": f"{wid}-call", "name": "Call SkyAssist API", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
         "position": [480, 0],
         "parameters": {
             "method": "POST", "url": f"={{{{ $env.SKYASSIST_API_BASE }}}}{api_path}",
             "sendHeaders": True,
             "headerParameters": {"parameters": [
                 {"name": "Authorization", "value": "=Bearer {{ $env.SKYASSIST_SERVICE_TOKEN }}"},
                 {"name": "X-SkyAssist-Signature", "value": "={{ $json.signature }}"},
                 {"name": "Idempotency-Key", "value": "={{ $json.idempotencyKey }}"},
                 {"name": "X-Workflow", "value": name},
                 {"name": "X-N8N-Execution-Id", "value": "={{ $json.executionId }}"}]},
             "sendBody": True, "contentType": "raw", "rawContentType": "application/json",
             "body": "={{ $json.bodyString }}",
             "options": {"timeout": 10000, "response": {"response": {"neverError": True, "fullResponse": True}}}}},
        {"id": f"{wid}-reply", "name": "Respond", "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1.1,
         "position": [720, 0],
         "parameters": {"respondWith": "json", "responseBody": "={{ JSON.stringify($json.body) }}",
                        "options": {"responseCode": "={{ $json.statusCode }}"}}},
        {"id": f"{wid}-note", "name": "About", "type": "n8n-nodes-base.stickyNote", "typeVersion": 1,
         "position": [0, -220], "parameters": {"width": 720, "height": 160, "content":
                                              f"## {name}\n{note}\n\nNeeds env: SKYASSIST_API_BASE, "
                                              "SKYASSIST_SERVICE_TOKEN, SKYASSIST_WEBHOOK_SECRET, "
                                              "NODE_FUNCTION_ALLOW_BUILTIN=crypto. No credentials are stored here."}},
    ]
    connections = {
        "Webhook": {"main": [[{"node": "Verify and sign", "type": "main", "index": 0}]]},
        "Verify and sign": {"main": [[{"node": "Call SkyAssist API", "type": "main", "index": 0}]]},
        "Call SkyAssist API": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
    }
    return {"id": wid, "name": name, "active": False, "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1", "saveDataErrorExecution": "all"},
            "pinData": {}, "meta": {"templateCredsSetupCompleted": True},
            "tags": [], "versionId": f"{wid}-v3", "staticData": None}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for code, spec in WORKFLOWS.items():
        wf = build(code, *spec)
        (OUT / f"{code}_{spec[1].split('/')[-1]}.json").write_text(json.dumps(wf, indent=2) + "\n")
    print(f"wrote {len(WORKFLOWS)} workflows to {OUT}")


if __name__ == "__main__":
    main()
