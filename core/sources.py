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

import requests

from core.cache import cache_key


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

        resp = requests.post(url, json=body, auth=_auth(cfg),
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
    resp = requests.post(_api(cfg, "search/approximate-count"),
                         json={"jql": jql}, auth=_auth(cfg),
                         headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    count = int(resp.json().get("count", 0))
    if cache is not None and key is not None:
        cache.put(key, count)
    return count


def fetch_myself(cfg):
    """Who the configured credentials belong to — used as a connection check."""
    resp = requests.get(_api(cfg, "myself"), auth=_auth(cfg),
                        headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_fields(cfg):
    """Every field the site knows about — used by `pm doctor --discover-fields`."""
    resp = requests.get(_api(cfg, "field"), auth=_auth(cfg),
                        headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    return resp.json() or []


def fetch_project(cfg, project):
    """One project's metadata, or raise if the key does not exist."""
    resp = requests.get(_api(cfg, f"project/{project}"), auth=_auth(cfg),
                        headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_project_components(cfg, project):
    """Component names defined on a project, so config typos can be caught."""
    resp = requests.get(_api(cfg, f"project/{project}/components"),
                        auth=_auth(cfg),
                        headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    return [c.get("name") for c in resp.json() if c.get("name")]


def fetch_active_sprints(cfg, project):
    """Active sprints (and their Sprint Goals) for a project, if Agile is on.

    Uses `/rest/agile/1.0`. Returns [] when the endpoint is missing, the
    project has no board, or anything else goes wrong — callers treat an
    empty list as "no Sprint Goal to show", not an error.
    """
    if not project:
        return []
    base = cfg["base_url"].rstrip("/")
    auth = _auth(cfg)
    headers = {"Accept": "application/json"}
    try:
        resp = requests.get(f"{base}/rest/agile/1.0/board",
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
            resp = requests.get(
                f"{base}/rest/agile/1.0/board/{board_id}/sprint",
                params={"state": "active"},
                auth=auth, headers=headers, timeout=30)
            resp.raise_for_status()
            for sprint in resp.json().get("values") or []:
                sprints.append({
                    "id": sprint.get("id"),
                    "name": sprint.get("name") or "",
                    "goal": (sprint.get("goal") or "").strip(),
                    "board": board.get("name") or "",
                    "project": project,
                })
        except requests.RequestException:
            continue
    return sprints


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
        items.append(make_item(
            ref=ref,
            source="Jira",
            title=f"{iss['key']}: {short(f.get('summary'), 140)}",
            detail=meta,
            url=f"{cfg['base_url'].rstrip('/')}/browse/{iss['key']}",
            meta=meta,
            uid=iss["key"],       # e.g. SDX-101 — stable across weeks
            watch=status,          # we flag a change when status moves
        ))
        idx += 1
    return items, idx


# ---------------------------------------------------------------------------
#  Jira — detailed fetch for lint
# ---------------------------------------------------------------------------

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
              "assignee", "labels", "duedate", "updated", "description",
              "parent"]
    for extra in (sp, sd, ac, epic):
        if extra and extra not in fields:
            fields.append(extra)

    out = []
    for iss in search_issues(cfg, jql, fields=fields, max_items=max_results):
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
            "description": adf_to_text(f.get("description")),
            "acceptance_criteria": adf_to_text(f.get(ac)) if ac else "",
        })
    return out


# ---------------------------------------------------------------------------
#  Jira — standup helpers
# ---------------------------------------------------------------------------

def fetch_jira_cards(cfg, jql, max_results=None):
    """Light fetch returning key/summary/status/assignee for grouping.

    Used by `pm standup` for the "in progress now" list, where we want the
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
    resp = requests.get(_api(cfg, f"issue/{key}/changelog"), auth=_auth(cfg),
                        params={"maxResults": 100},
                        headers={"Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    return resp.json().get("values") or []


def fetch_jira_changelog(cfg, jql, since_days, max_results=None):
    """Fetch issues and pull their recent STATUS transitions from the changelog.

    Returns a list of dicts, each with a `transitions` list of
    {from, to, when, who} that happened within the last `since_days` days.
    Issues with no recent status transition are omitted, so the caller gets
    exactly "what moved" for a standup.
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
                if it.get("field") == "status":
                    transitions.append({
                        "from": it.get("fromString") or "?",
                        "to": it.get("toString") or "?",
                        "when": when,
                        "who": (hist.get("author") or {}).get("displayName",
                                                              ""),
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


# ---------------------------------------------------------------------------
#  Confluence
# ---------------------------------------------------------------------------

def fetch_confluence(cfg, cql, tag_prefix, start_index):
    """Return (items, next_index) for a Confluence CQL query."""
    if not cql:
        return [], start_index

    # Add a date filter so we only get material since the last report.
    since = (dt.date.today()
             - dt.timedelta(days=cfg["lookback_days"])).isoformat()
    full_cql = f"({cql}) AND lastmodified >= '{since}'"

    url = f"{cfg['base_url'].rstrip('/')}/rest/api/content/search"
    resp = requests.get(
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
    resp = requests.post(url, data={
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
    site_resp = requests.get(
        f"https://{host}/v1.0/sites/root:/{cfg['site_path']}",
        headers=headers, timeout=60)
    site_resp.raise_for_status()
    site_id = site_resp.json()["id"]

    search_resp = requests.get(
        f"https://{host}/v1.0/sites/{site_id}/drive/root/search(q='{query}')",
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
