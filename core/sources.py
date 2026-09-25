"""Data sources: Jira, Confluence, SharePoint.

Two flavours of Jira fetch live here:
  * fetch_jira          - light items (title, status, link) used by the report.
  * fetch_jira_detailed - richer records (components, epic, dates, estimate,
                          acceptance criteria) used by the lint command.

All of them go through `search_issues`, which talks to Jira Cloud's current
search endpoint (`/rest/api/3/search/jql`) and follows `nextPageToken` until the
query is exhausted or the configured cap is reached. The endpoint this tool used
to call, `/rest/api/3/search`, has been removed from Jira Cloud.

Nothing here reaches the public internet except your own tenants.
"""

import datetime as dt
import re
import time
from urllib.parse import quote

import requests

from core import queries
from core.cache import cache_key
from core.http import retry_after_seconds


def send(method, url, **kwargs):
    """One HTTP call. On 429, wait for Retry-After and try once more.

    Uses requests.get/post/put so tests can patch those on this module.
    A stand-in response with no status_code is returned as-is.
    """
    kwargs.setdefault("timeout", 60)
    func = {"GET": requests.get, "POST": requests.post,
            "PUT": requests.put}[method.upper()]
    response = func(url, **kwargs)
    if getattr(response, "status_code", None) != 429:
        return response
    wait = retry_after_seconds(response)
    time.sleep(wait)
    response = func(url, **kwargs)
    if getattr(response, "status_code", None) == 429:
        raise requests.HTTPError(
            f"Rate limit (429) after waiting {wait}s. Try again shortly.",
            response=response)
    return response


# ---------------------------------------------------------------------------
#  Text helpers
# ---------------------------------------------------------------------------

def short(text, limit=280):
    """Shorten free text so we feed the model signal, not noise."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def strip_html(html):
    """Confluence returns HTML; reduce it to readable plain text."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    return short(text, 400)


def adf_to_text(node):
    """Flatten Jira Cloud's rich description (ADF JSON) to plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    texts = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "text" and "text" in n:
                texts.append(n["text"])
            for child in n.get("content", []) or []:
                walk(child)
        elif isinstance(n, list):
            for child in n:
                walk(child)

    walk(node)
    return " ".join(texts)


# A gathered item is a plain dict. We build a reference tag for each so the
# model can cite it and we can list it in the reference table at the end.
def make_item(ref, source, title, detail, url, meta="", uid=None, watch=""):
    return {
        "ref": ref,          # e.g. "SDX-J1" — a per-run tag for citing
        "source": source,    # "Jira" | "Confluence" | "SharePoint"
        "title": title,
        "detail": detail,
        "url": url,
        "meta": meta,        # e.g. "Status: In Progress | Assignee: A. Lee"
        "uid": uid or url,   # STABLE identity across weeks (Jira key, page url)
        "watch": watch,      # the value we compare week-to-week (e.g. status)
    }




# ---------------------------------------------------------------------------
#  Jira — the search call every fetch is built on
# ---------------------------------------------------------------------------

def _auth(cfg):
    return (cfg["email"], cfg["api_token"])


def _api(cfg, path):
    return f"{cfg['base_url'].rstrip('/')}/rest/api/3/{path.lstrip('/')}"


def _field_list(fields):
    """Accept a list or a comma-separated string; the API wants a list."""
    if not fields:
        return ["key"]
    if isinstance(fields, str):
        return [f.strip() for f in fields.split(",") if f.strip()]
    return list(fields)


def search_issues(cfg, jql, fields=None, expand=None, max_items=None,
                  page_size=None):
    """Run a JQL search, following nextPageToken, and return the raw issues.

    `max_items` caps how much we pull for one query (defaults to the config's
    `max_results`); pass 0 or None-with-`unlimited` semantics via
    `max_items=0` to fetch everything the query matches.
    """
    if not jql:
        return []

    if max_items is None:
        max_items = int(cfg.get("max_results", 100) or 100)
    page_size = int(page_size or cfg.get("page_size", 100) or 100)
    if max_items:
        page_size = min(page_size, max_items)

    cache = cfg.get("_fetch_cache")
    key = None
    if cache is not None:
        key = cache_key("search", jql, _field_list(fields), expand, max_items)
        hit = cache.get(key)
        if hit is not None:
            return hit

    url = _api(cfg, "search/jql")
    issues, token = [], None
    while True:
        # POST so a long JQL string (a list of epic keys, say) can't blow the
        # URL length limit.
        body = {"jql": jql, "fields": _field_list(fields),
                "maxResults": page_size}
        if expand:
            body["expand"] = expand
        if token:
            body["nextPageToken"] = token

        resp = send("POST",url, json=body, auth=_auth(cfg),
                             headers={"Accept": "application/json"}, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        page = data.get("issues") or []
        issues.extend(page)
        token = data.get("nextPageToken")
        if not token or not page:
            break
        if max_items and len(issues) >= max_items:
            break

    result = issues[:max_items] if max_items else issues
    if cache is not None and key is not None:
        cache.put(key, result)
    return result


def approximate_count(cfg, jql):
    """How many issues a query matches, without pulling them all back."""
    if not jql:
        return 0
    cache = cfg.get("_fetch_cache")
    key = None
    if cache is not None:
        key = cache_key("count", jql)
        hit = cache.get(key)
        if hit is not None:
            return int(hit)
    resp = send("POST",_api(cfg, "search/approximate-count"),
                         json={"jql": jql}, auth=_auth(cfg),
                         headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    count = int(resp.json().get("count", 0))
    if cache is not None and key is not None:
        cache.put(key, count)
    return count


def fetch_myself(cfg):
    """Who the configured credentials belong to — used as a connection check."""
    resp = send("GET",_api(cfg, "myself"), auth=_auth(cfg),
                        headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_fields(cfg):
    """Every field the site knows about — used by `pm doctor --discover-fields`."""
    resp = send("GET",_api(cfg, "field"), auth=_auth(cfg),
                        headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    return resp.json() or []


def fetch_project(cfg, project):
    """One project's metadata, or raise if the key does not exist."""
    resp = send("GET",_api(cfg, f"project/{project}"), auth=_auth(cfg),
                        headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_project_components(cfg, project):
    """Component names defined on a project, so config typos can be caught."""
    resp = send("GET",_api(cfg, f"project/{project}/components"),
                        auth=_auth(cfg),
                        headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    return [c.get("name") for c in resp.json() if c.get("name")]


def fetch_project_statuses(cfg, project):
    """Every status on a project, with its statusCategory key.

    Jira returns one entry per issue type, each with its own status list.
    The same status id can appear under several types; callers de-duplicate.
    """
    resp = send("GET", _api(cfg, f"project/{project}/statuses"),
                auth=_auth(cfg),
                headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    rows = []
    for issue_type in resp.json() or []:
        for status in issue_type.get("statuses") or []:
            category = ((status.get("statusCategory") or {}).get("key") or "")
            rows.append({
                "id": str(status.get("id") or ""),
                "name": status.get("name") or "",
                "category": category,
            })
    return rows


def parse_timestamp(value):
    """Jira's ISO timestamp, or a YYYY-MM-DD date at UTC midnight."""
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day,
                           tzinfo=dt.timezone.utc)
    if not value:
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text = text + "T00:00:00+00:00"
    text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text.replace("Z", "+00:00"))
    for candidate in (text, text.split(".")[0]):
        try:
            parsed = dt.datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    return None


def fetch_comments(cfg, key, cutoff=None, limit=None):
    """Comments on one issue.

    With no cutoff and no limit, every comment is returned in the order
    Jira sends. With either, comments are read newest-first and the result
    is the kept ones, oldest first. Reading stops at `cutoff` or once
    `limit` comments are kept, so a long thread is not downloaded whole.
    """
    cache = cfg.get("_fetch_cache")
    cache_id = None
    if cache is not None:
        stamp = cutoff.isoformat() if cutoff is not None else None
        cache_id = cache_key("comments", key, stamp, limit)
        hit = cache.get(cache_id)
        if hit is not None:
            return hit

    kept = []
    start = 0
    page_size = 50
    windowed = cutoff is not None or limit is not None
    for _page in range(40):
        params = {"startAt": start, "maxResults": page_size}
        if windowed:
            params["orderBy"] = "-created"
        resp = send("GET", _api(cfg, f"issue/{key}/comment"),
                    params=params, auth=_auth(cfg),
                    headers={"Accept": "application/json"}, timeout=60)
        resp.raise_for_status()
        data = resp.json() or {}
        comments = data.get("comments") or []
        stop = False
        for comment in comments:
            created = parse_timestamp(comment.get("created"))
            if cutoff is not None and created is not None and created < cutoff:
                stop = True
                break
            kept.append(comment)
            if limit is not None and len(kept) >= limit:
                stop = True
                break
        if stop or not comments:
            break
        total = data.get("total")
        start += len(comments)
        if total is not None and start >= int(total):
            break
        if len(comments) < page_size:
            break
    if windowed:
        kept.reverse()
    if cache is not None and cache_id is not None:
        cache.put(cache_id, kept)
    return kept


def fetch_issue_links(cfg, key):
    """issuelinks for one issue: [{type, inward, outward, key, summary}]."""
    resp = send("GET",_api(cfg, f"issue/{key}"),
                        params={"fields": "issuelinks,summary"},
                        auth=_auth(cfg),
                        headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    links = []
    for link in (resp.json().get("fields") or {}).get("issuelinks") or []:
        rel = link.get("type") or {}
        other = link.get("outwardIssue") or link.get("inwardIssue") or {}
        direction = "outward" if link.get("outwardIssue") else "inward"
        name = rel.get("outward") if direction == "outward" else rel.get("inward")
        links.append({
            "type": rel.get("name") or "",
            "relation": (name or "").lower(),
            "direction": direction,
            "key": other.get("key"),
            "summary": ((other.get("fields") or {}).get("summary") or ""),
        })
    return links


def search_users(cfg, query):
    """People whose name or email matches `query`."""
    if not query:
        return []
    resp = send("GET",_api(cfg, "user/search"),
                        params={"query": query},
                        auth=_auth(cfg),
                        headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    return resp.json() or []


def resolve_assignee(cfg, name):
    """Pick the first user search hit. Returns {accountId, displayName} or None."""
    hits = search_users(cfg, name)
    if not hits:
        return None
    person = hits[0]
    return {
        "accountId": person.get("accountId"),
        "displayName": person.get("displayName") or name,
    }


def _sprint_identity(sprint):
    """The sprint id when Jira sent one, otherwise the text we would print.

    The board search returns every board whose filter mentions the project,
    and the same sprint is active on each of them.
    """
    sprint_id = sprint.get("id")
    if sprint_id is not None:
        return ("id", sprint_id)
    return ("text", sprint.get("project"), sprint.get("name"),
            sprint.get("goal"), sprint.get("end"))


def dedupe_sprints(sprints):
    """Keep the first copy of each sprint."""
    seen = set()
    unique = []
    for sprint in sprints:
        key = _sprint_identity(sprint)
        if key in seen:
            continue
        seen.add(key)
        unique.append(sprint)
    return unique


def fetch_sprints(cfg, project, states=("active",)):
    """Sprints for a project, if Agile is on.

    `states` is passed to the Agile API (`active`, `closed`, `future`).
    A sprint on more than one board is returned once. Returns [] when the
    endpoint is missing or the project has no board.
    """
    if not project:
        return []
    state = ",".join(states) if not isinstance(states, str) else states
    base = cfg["base_url"].rstrip("/")
    auth = _auth(cfg)
    headers = {"Accept": "application/json"}
    try:
        resp = send("GET",f"{base}/rest/agile/1.0/board",
                            params={"projectKeyOrId": project},
                            auth=auth, headers=headers, timeout=30)
        resp.raise_for_status()
        boards = resp.json().get("values") or []
    except requests.RequestException:
        return []

    sprints = []
    for board in boards[:5]:
        board_id = board.get("id")
        if board_id is None:
            continue
        try:
            resp = send("GET",
                f"{base}/rest/agile/1.0/board/{board_id}/sprint",
                params={"state": state},
                auth=auth, headers=headers, timeout=30)
            resp.raise_for_status()
            for sprint in resp.json().get("values") or []:
                sprints.append({
                    "id": sprint.get("id"),
                    "name": sprint.get("name") or "",
                    "goal": (sprint.get("goal") or "").strip(),
                    "board": board.get("name") or "",
                    "project": project,
                    "start": (sprint.get("startDate") or "")[:10] or None,
                    "end": (sprint.get("endDate") or sprint.get("end") or "")[:10] or None,
                    "state": sprint.get("state") or "active",
                })
        except requests.RequestException:
            continue
    return dedupe_sprints(sprints)


def fetch_active_sprints(cfg, project):
    """Active sprints only. `pm today` wants the Sprint that is open now."""
    return fetch_sprints(cfg, project, states=("active",))


def fetch_projects(cfg):
    """Projects the token can see. `pm setup` offers these instead of a blank."""
    base = cfg["base_url"].rstrip("/")
    resp = send(
        "GET", f"{base}/rest/api/3/project/search",
        params={"maxResults": 50},
        auth=_auth(cfg), headers={"Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    out = []
    for project in resp.json().get("values") or []:
        out.append({
            "key": project.get("key") or "",
            "name": project.get("name") or "",
        })
    return out


def fetch_confluence_spaces(cfg):
    """Spaces on the Confluence site. Empty when Confluence is not configured."""
    base = (cfg.get("base_url") or "").rstrip("/")
    if not base:
        return []
    resp = send(
        "GET", f"{base}/rest/api/space",
        params={"limit": 50},
        auth=(cfg.get("email"), cfg.get("api_token")),
        headers={"Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    out = []
    for space in resp.json().get("results") or []:
        out.append({
            "key": space.get("key") or "",
            "name": space.get("name") or "",
        })
    return out


def fetch_model_ids(endpoint):
    """Model ids from an OpenAI-compatible `/v1/models` (llama.cpp, Lemonade)."""
    url = endpoint.rstrip("/")
    if not url.endswith("/models"):
        url = url + "/models" if url.endswith("/v1") else url + "/v1/models"
    resp = send("GET", url, headers={"Accept": "application/json"}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    rows = data.get("data") if isinstance(data, dict) else data
    ids = []
    for row in rows or []:
        if isinstance(row, dict) and row.get("id"):
            ids.append(row["id"])
        elif isinstance(row, str):
            ids.append(row)
    return ids


# ---------------------------------------------------------------------------
#  Jira — workstream discovery
# ---------------------------------------------------------------------------

def fetch_jira_keys(cfg, jql):
    """Return every Jira issue key matching JQL, paging until exhausted.

    Used to discover the Epics (and directly tagged issues) that define a
    workstream, so it deliberately ignores the item cap and fetches only keys.
    """
    return [iss["key"] for iss in
            search_issues(cfg, jql, fields=["key"], max_items=0)
            if iss.get("key")]


# ---------------------------------------------------------------------------
#  Jira — light fetch for the report
# ---------------------------------------------------------------------------

DEFAULT_REPORT_FIELDS = ("summary,status,assignee,updated,duedate,priority,"
                         "issuetype,labels")


def fetch_jira(cfg, jql, tag_prefix, start_index):
    """Return (items, next_index) for a Jira JQL query."""
    if not jql:
        return [], start_index

    issues = search_issues(cfg, jql,
                           fields=cfg.get("fields") or DEFAULT_REPORT_FIELDS)

    items, idx = [], start_index
    for iss in issues:
        f = iss.get("fields", {})
        status = (f.get("status") or {}).get("name", "Unknown")
        assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
        due = f.get("duedate") or "no due date"
        priority = (f.get("priority") or {}).get("name", "")
        meta = f"Status: {status} | Assignee: {assignee} | Due: {due}"
        if priority:
            meta += f" | Priority: {priority}"
        ref = f"{tag_prefix}-J{idx}"
        item = make_item(
            ref=ref,
            source="Jira",
            title=f"{iss['key']}: {short(f.get('summary'), 140)}",
            detail=meta,
            url=f"{cfg['base_url'].rstrip('/')}/browse/{iss['key']}",
            meta=meta,
            uid=iss["key"],       # e.g. SDX-101 — stable across weeks
            watch=status,          # we flag a change when status moves
        )
        item["updated"] = f.get("updated")
        items.append(item)
        idx += 1
    return items, idx


# ---------------------------------------------------------------------------
#  Jira — detailed fetch for lint
# ---------------------------------------------------------------------------

def latest_status_change(issue):
    """ISO timestamp of the newest status transition, or None."""
    histories = ((issue.get("changelog") or {}).get("histories") or [])
    latest = None
    for history in histories:
        created = history.get("created")
        if not created:
            continue
        for item in history.get("items") or []:
            if (item.get("field") or "").lower() != "status":
                continue
            if latest is None or str(created) > str(latest):
                latest = created
    return latest


def sharepoint_search_url(site_id, query):
    """Graph drive search URL with quotes in the query escaped."""
    escaped = str(query).replace("'", "''")
    encoded = quote(escaped, safe="")
    return (f"https://graph.microsoft.com/v1.0/sites/{site_id}"
            f"/drive/root/search(q='{encoded}')")


def fetch_jira_detailed(cfg, jql, max_results=None):
    """Fetch issues with the extra fields lint needs. Returns list of dicts.

    Custom-field IDs (story points, start date, acceptance criteria, epic link)
    vary by Jira instance, so they are read from config and skipped if blank.
    """
    if not jql:
        return []

    sp = cfg.get("story_points_field") or ""
    sd = cfg.get("start_date_field") or ""
    ac = cfg.get("acceptance_criteria_field") or ""
    epic = cfg.get("epic_link_field") or "parent"

    fields = ["summary", "status", "issuetype", "components",
              "assignee", "labels", "duedate", "updated", "created",
              "description", "parent"]
    for extra in (sp, sd, ac, epic):
        if extra and extra not in fields:
            fields.append(extra)

    out = []
    for iss in search_issues(cfg, jql, fields=fields, expand="changelog",
                             max_items=max_results):
        f = iss.get("fields", {})

        # Epic / parent link — team-managed uses "parent", classic a customfield.
        if epic == "parent":
            epic_key = (f.get("parent") or {}).get("key")
        else:
            val = f.get(epic)
            if isinstance(val, dict):
                epic_key = val.get("key")
            else:
                epic_key = val

        out.append({
            "key": iss["key"],
            "url": f"{cfg['base_url'].rstrip('/')}/browse/{iss['key']}",
            "summary": f.get("summary") or "",
            "status": (f.get("status") or {}).get("name", "Unknown"),
            "status_category": ((f.get("status") or {}).get(
                "statusCategory") or {}).get("key", ""),
            "issuetype": (f.get("issuetype") or {}).get("name", ""),
            "components": [c.get("name") for c in (f.get("components") or [])],
            "assignee": (f.get("assignee") or {}).get("displayName",
                                                      "Unassigned"),
            "labels": f.get("labels") or [],
            "epic": epic_key,
            "story_points": f.get(sp) if sp else None,
            "start_date": f.get(sd) if sd else None,
            "due_date": f.get("duedate"),
            "updated": f.get("updated"),
            "status_changed": latest_status_change(iss),
            "created": f.get("created"),
            "description": adf_to_text(f.get("description")),
            "acceptance_criteria": adf_to_text(f.get(ac)) if ac else "",
        })
    return out


# ---------------------------------------------------------------------------
#  Jira — daily movement helpers
# ---------------------------------------------------------------------------

def fetch_jira_cards(cfg, jql, max_results=None):
    """Light fetch returning key/summary/status/assignee for grouping.

    Used by `pm daily` for the "in progress now" list, where we want the
    owner but none of the heavier lint fields. Returns a list of dicts.
    """
    if not jql:
        return []

    fields = ["summary", "status", "assignee", "issuetype", "updated"]

    out = []
    for iss in search_issues(cfg, jql, fields=fields, max_items=max_results):
        f = iss.get("fields", {})
        out.append({
            "key": iss["key"],
            "url": f"{cfg['base_url'].rstrip('/')}/browse/{iss['key']}",
            "summary": f.get("summary") or "",
            "status": (f.get("status") or {}).get("name", "Unknown"),
            "assignee": (f.get("assignee") or {}).get("displayName",
                                                      "Unassigned"),
            "issuetype": (f.get("issuetype") or {}).get("name", ""),
            "updated": f.get("updated"),
        })
    return out


def fetch_issue_changelog(cfg, key):
    """One issue's change history, for sites that don't expand it on search."""
    resp = send("GET",_api(cfg, f"issue/{key}/changelog"), auth=_auth(cfg),
                        params={"maxResults": 100},
                        headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    return resp.json().get("values") or []


def fetch_jira_changelog(cfg, jql, since_days, max_results=None):
    """Fetch issues and pull their recent STATUS transitions from the changelog.

    Returns a list of dicts, each with a `transitions` list of
    {from, to, when, who} that happened within the last `since_days` days.
    Issues with no recent status transition are omitted, so the caller gets
    exactly "what moved" for the Daily Scrum.
    """
    if not jql:
        return []

    import datetime as _dt
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=since_days)

    fields = ["summary", "status", "assignee", "issuetype"]
    issues = search_issues(cfg, jql, fields=fields, expand="changelog",
                           max_items=max_results)

    def _parse(ts):
        if not ts:
            return None
        text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2",
                      str(ts).replace("Z", "+00:00"))
        for cand in (text, text.split(".")[0]):
            try:
                p = _dt.datetime.fromisoformat(cand)
                return p if p.tzinfo else p.replace(tzinfo=_dt.timezone.utc)
            except ValueError:
                continue
        return None

    out = []
    for iss in issues:
        f = iss.get("fields", {})
        histories = (iss.get("changelog") or {}).get("histories")
        if histories is None:
            # Some sites do not expand the changelog on search; ask per issue.
            histories = fetch_issue_changelog(cfg, iss["key"])
        transitions = []
        for hist in histories or []:
            when = _parse(hist.get("created"))
            if when is None or when < cutoff:
                continue
            for it in hist.get("items", []):
                if (it.get("field") or "").lower() != "status":
                    continue
                transitions.append({
                    "field": "status",
                    "from": it.get("fromString") or "?",
                    "to": it.get("toString") or "?",
                    "from_id": it.get("from") or "",
                    "to_id": it.get("to") or "",
                    "when": when,
                    "who": (hist.get("author") or {}).get("displayName", ""),
                })
        if not transitions:
            continue
        transitions.sort(key=lambda t: t["when"])
        out.append({
            "key": iss["key"],
            "url": f"{cfg['base_url'].rstrip('/')}/browse/{iss['key']}",
            "summary": f.get("summary") or "",
            "status": (f.get("status") or {}).get("name", "Unknown"),
            "assignee": (f.get("assignee") or {}).get("displayName",
                                                      "Unassigned"),
            "issuetype": (f.get("issuetype") or {}).get("name", ""),
            "transitions": transitions,
        })
    return out


def parse_jira_datetime(value):
    """Parse a Jira ISO timestamp into an aware UTC datetime, or None."""
    if not value:
        return None
    text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2",
                  str(value).replace("Z", "+00:00"))
    for cand in (text, text.split(".")[0]):
        try:
            parsed = dt.datetime.fromisoformat(cand)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    return None


def fetch_jira_history(cfg, jql, max_results=None):
    """Issues plus their full status and sprint changelog (no recency cutoff).

    Used by `pm metrics`. Each record has the lint-style fields plus
    `transitions`: [{field, from, to, when, who}, ...].
    """
    if not jql:
        return []

    sp = cfg.get("story_points_field") or ""
    fields = ["summary", "status", "assignee", "issuetype", "updated",
              "created", "duedate"]
    if sp:
        fields.append(sp)

    issues = search_issues(cfg, jql, fields=fields, expand="changelog",
                           max_items=max_results)
    out = []
    for iss in issues:
        f = iss.get("fields", {})
        histories = (iss.get("changelog") or {}).get("histories")
        if histories is None:
            histories = fetch_issue_changelog(cfg, iss["key"])
        transitions = []
        for hist in histories or []:
            when = parse_jira_datetime(hist.get("created"))
            if when is None:
                continue
            for it in hist.get("items", []):
                field = (it.get("field") or "").lower()
                if field not in ("status", "sprint"):
                    continue
                transitions.append({
                    "field": field,
                    "from": it.get("fromString") or "",
                    "to": it.get("toString") or "",
                    "from_id": it.get("from") or "",
                    "to_id": it.get("to") or "",
                    "when": when,
                    "who": (hist.get("author") or {}).get("displayName", ""),
                })
        transitions.sort(key=lambda t: t["when"])
        category = ((f.get("status") or {}).get("statusCategory") or {}).get("key", "")
        out.append({
            "key": iss["key"],
            "url": f"{cfg['base_url'].rstrip('/')}/browse/{iss['key']}",
            "summary": f.get("summary") or "",
            "status": (f.get("status") or {}).get("name", "Unknown"),
            "status_category": category,
            "assignee": (f.get("assignee") or {}).get("displayName", "Unassigned"),
            "issuetype": (f.get("issuetype") or {}).get("name", ""),
            "story_points": f.get(sp) if sp else None,
            "updated": f.get("updated"),
            "created": f.get("created"),
            "due_date": f.get("duedate"),
            "transitions": transitions,
        })
    return out


# ---------------------------------------------------------------------------
#  Confluence
# ---------------------------------------------------------------------------

def fetch_confluence(cfg, cql, tag_prefix, start_index, since=None):
    """Return (items, next_index) for a Confluence CQL query."""
    if not cql:
        return [], start_index

    # Add a date filter so we only get material since the last report.
    if since is None:
        since = (dt.date.today()
                 - dt.timedelta(days=cfg["lookback_days"])).isoformat()
    elif hasattr(since, "isoformat"):
        since = since.isoformat()
    full_cql = queries.render(None, "confluence.window", cql=cql, since=since)

    url = f"{cfg['base_url'].rstrip('/')}/rest/api/content/search"
    resp = send("GET",
        url,
        params={"cql": full_cql,
                "limit": cfg["max_results"],
                "expand": "body.view,version,space"},
        auth=(cfg["email"], cfg["api_token"]),
        headers={"Accept": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])

    items, idx = [], start_index
    for page in results:
        body = (page.get("body", {}).get("view", {}) or {}).get("value", "")
        when = (page.get("version", {}) or {}).get("when", "")[:10]
        link = cfg["base_url"].rstrip("/") + page.get("_links", {}).get("webui", "")
        ref = f"{tag_prefix}-C{idx}"
        items.append(make_item(
            ref=ref,
            source="Confluence",
            title=short(page.get("title"), 140),
            detail=strip_html(body),
            url=link,
            meta=f"Updated: {when}",
            uid=f"confluence:{page.get('id', link)}",  # stable page id
            watch=when,            # a new "updated" date means it changed
        ))
        idx += 1
    return items, idx


# ---------------------------------------------------------------------------
#  SharePoint (via Microsoft Graph)
# ---------------------------------------------------------------------------

def get_graph_token(cfg):
    """Get a Microsoft Graph app-only token for SharePoint."""
    url = f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token"
    resp = send("POST",url, data={
        "grant_type": "client_credentials",
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "scope": "https://graph.microsoft.com/.default",
    }, timeout=60)
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_sharepoint(cfg, query, tag_prefix, start_index):
    """Return (items, next_index) for tracked SharePoint documents."""
    if not cfg.get("enabled") or not query:
        return [], start_index

    token = get_graph_token(cfg)
    headers = {"Authorization": f"Bearer {token}"}

    # Resolve the site id from its path, then search its drive for the query.
    host = "graph.microsoft.com"
    site_resp = send("GET",
        f"https://{host}/v1.0/sites/root:/{cfg['site_path']}",
        headers=headers, timeout=60)
    site_resp.raise_for_status()
    site_id = site_resp.json()["id"]

    search_resp = send("GET",
        sharepoint_search_url(site_id, query),
        headers=headers, timeout=60)
    search_resp.raise_for_status()
    files = search_resp.json().get("value", [])[: cfg["max_results"]]

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=cfg["lookback_days"])
    items, idx = [], start_index
    for f in files:
        modified = f.get("lastModifiedDateTime", "")
        try:
            mod_dt = dt.datetime.fromisoformat(modified.replace("Z", "+00:00"))
            if mod_dt < cutoff:
                continue
        except ValueError:
            pass
        ref = f"{tag_prefix}-S{idx}"
        items.append(make_item(
            ref=ref,
            source="SharePoint",
            title=short(f.get("name"), 140),
            detail=f"Modified {modified[:10]}",
            url=f.get("webUrl", ""),
            meta=f"Modified: {modified[:10]}",
            uid=f"sharepoint:{f.get('id', f.get('webUrl', ''))}",  # stable id
            watch=modified[:10],   # a newer modified date means it changed
        ))
        idx += 1
    return items, idx
