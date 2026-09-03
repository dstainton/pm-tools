"""Publish a Markdown file to Confluence and/or a Teams webhook.

Config (`publish:`) can enable one, the other, or both. Every send uses the
shared write path: preview, one confirm, a line in the write log.
Nothing on this path runs on a schedule.
"""

import html
import os
import re
import sys

import requests

from core import writes


def settings(cfg):
    block = cfg.get("publish") if isinstance(cfg.get("publish"), dict) else {}
    conf = block.get("confluence") if isinstance(block.get("confluence"), dict) else {}
    teams = block.get("teams") if isinstance(block.get("teams"), dict) else {}
    # A webhook string at the top level is the older sketch.
    webhook = teams.get("webhook") or block.get("teams_webhook") or ""
    return {
        "confluence_enabled": bool(conf.get("enabled", bool(conf.get("space")))),
        "space": conf.get("space") or "",
        "parent_page": conf.get("parent_page") or "",
        "teams_enabled": bool(teams.get("enabled", bool(webhook))),
        "webhook": webhook,
    }


def markdown_to_storage(text):
    """Small Markdown → Confluence storage conversion (headings, lists, code)."""
    chunks = []
    in_list = False
    in_code = False
    code_lines = []
    for raw in (text or "").splitlines():
        if raw.strip().startswith("```"):
            if in_code:
                body = html.escape("\n".join(code_lines))
                chunks.append(f"<ac:structured-macro ac:name=\"code\">"
                              f"<ac:plain-text-body><![CDATA[{body}]]>"
                              f"</ac:plain-text-body></ac:structured-macro>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(raw)
            continue
        if raw.startswith("# "):
            if in_list:
                chunks.append("</ul>")
                in_list = False
            chunks.append(f"<h1>{html.escape(raw[2:].strip())}</h1>")
        elif raw.startswith("## "):
            if in_list:
                chunks.append("</ul>")
                in_list = False
            chunks.append(f"<h2>{html.escape(raw[3:].strip())}</h2>")
        elif raw.startswith("### "):
            if in_list:
                chunks.append("</ul>")
                in_list = False
            chunks.append(f"<h3>{html.escape(raw[4:].strip())}</h3>")
        elif raw.startswith("- ") or raw.startswith("* "):
            if not in_list:
                chunks.append("<ul>")
                in_list = True
            chunks.append(f"<li>{html.escape(raw[2:].strip())}</li>")
        elif not raw.strip():
            if in_list:
                chunks.append("</ul>")
                in_list = False
        else:
            if in_list:
                chunks.append("</ul>")
                in_list = False
            chunks.append(f"<p>{html.escape(raw)}</p>")
    if in_list:
        chunks.append("</ul>")
    return "\n".join(chunks) or "<p></p>"


def _confluence_base(cfg):
    return (cfg.get("confluence") or {}).get("base_url") or ""


def find_page(cfg, space, title):
    base = _confluence_base(cfg).rstrip("/")
    if not base or not space or not title:
        return None
    url = f"{base}/rest/api/content"
    try:
        resp = requests.get(
            url,
            params={"spaceKey": space, "title": title, "expand": "version"},
            auth=(cfg["confluence"]["email"], cfg["confluence"]["api_token"]),
            headers={"Accept": "application/json"},
            timeout=60)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    results = (resp.json() or {}).get("results") or []
    return results[0] if results else None


def find_parent(cfg, space, parent_title):
    if not parent_title:
        return None
    return find_page(cfg, space, parent_title)


def confluence_action(cfg, opts, title, markdown):
    base = _confluence_base(cfg).rstrip("/")
    if not base:
        sys.exit("publish.confluence needs confluence.base_url.")
    if not opts["space"]:
        sys.exit("publish.confluence.space is empty.")
    storage = markdown_to_storage(markdown)
    existing = find_page(cfg, opts["space"], title)
    body = {
        "type": "page",
        "title": title,
        "space": {"key": opts["space"]},
        "body": {"storage": {"value": storage, "representation": "storage"}},
    }
    if existing:
        version = ((existing.get("version") or {}).get("number") or 1) + 1
        body["version"] = {"number": version}
        page_id = existing.get("id")
        return {
            "method": "PUT",
            "url": f"{base}/rest/api/content/{page_id}",
            "path": f"/wiki/rest/api/content/{page_id}",
            "body": body,
            "kind": "publish-confluence",
            "summary": title,
            "description": f"update Confluence page in {opts['space']}",
        }
    parent = find_parent(cfg, opts["space"], opts["parent_page"])
    if parent and parent.get("id"):
        body["ancestors"] = [{"id": parent["id"]}]
    return {
        "method": "POST",
        "url": f"{base}/rest/api/content",
        "path": "/wiki/rest/api/content",
        "body": body,
        "kind": "publish-confluence",
        "summary": title,
        "description": f"create Confluence page in {opts['space']}",
    }


def teams_action(opts, title, markdown):
    if not opts["webhook"]:
        sys.exit("publish.teams.webhook is empty.")
    # Incoming webhooks accept a simple text card.
    text = f"**{title}**\n\n{markdown}"
    return {
        "method": "POST",
        "url": opts["webhook"],
        "path": opts["webhook"],
        "body": {"text": text},
        "auth": "none",
        "kind": "publish-teams",
        "summary": title,
        "description": "post to the Teams webhook",
    }


def publish_file(cfg, args, path, title=None):
    if not path or not os.path.exists(path):
        sys.exit(f"No file at {path!r} to publish.")
    with open(path, encoding="utf-8") as fh:
        markdown = fh.read()
    title = title or os.path.basename(path)
    # First heading wins as the page title when the caller did not set one.
    if title == os.path.basename(path):
        match = re.search(r"^#\s+(.+)$", markdown, re.M)
        if match:
            title = match.group(1).strip()
    opts = settings(cfg)
    actions = []
    if opts["confluence_enabled"]:
        actions.append(confluence_action(cfg, opts, title, markdown))
    if opts["teams_enabled"]:
        actions.append(teams_action(opts, title, markdown))
    if not actions:
        sys.exit("Nothing to publish. Enable publish.confluence and/or "
                 "publish.teams in config.")
    print(f"Publishing {path} ({len(actions)} destination(s))\n")
    for action in actions:
        writes.preview(action)
        print("")
    if not writes.should_write(args):
        return []
    results = []
    for action in actions:
        try:
            result = writes.execute(cfg, action)
            writes.log_write(cfg, action, result=result)
            print(f"Sent ({action['kind']}).")
            results.append(result)
        except requests.RequestException as err:
            writes.log_write(cfg, action, error=err)
            sys.exit(f"Write failed: {err}")
    return results


def run(cfg, args):
    path = getattr(args, "file", None)
    if not path:
        sys.exit("Which file? e.g.  pm publish weekly_report_2026-09-03.md")
    publish_file(cfg, args, path)
