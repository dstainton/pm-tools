"""A tiny stand-in for Jira Cloud (and a local model), for end-to-end tests.

It speaks just enough of the real thing to run `pm` for real:

  POST /rest/api/3/search/jql               paged search, nextPageToken and all
  POST /rest/api/3/search/approximate-count
  GET  /rest/api/3/myself
  GET  /rest/api/3/field
  GET  /rest/api/3/project/<KEY>
  GET  /rest/api/3/project/<KEY>/components
  GET  /rest/api/3/issue/<KEY>/changelog
  GET  /rest/agile/1.0/board
  GET  /rest/agile/1.0/board/<ID>/sprint
  GET  /wiki/rest/api/content/search        Confluence pages, filtered by space
  POST /v1/chat/completions                 an OpenAI-compatible model reply

The searches are answered by evaluating the JQL `pm` generates against an
in-memory backlog, so a test can assert that the right issues — and only the
right issues — end up in a workstream.
"""

import datetime as dt
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse


# ---------------------------------------------------------------------------
#  A very small JQL reader: enough for every query pm builds
# ---------------------------------------------------------------------------

TOKEN = re.compile(r"""\s*(?:
      (?P<str>"(?:[^"\\]|\\.)*")
    | (?P<num>-?\d+[dhwm]?)
    | (?P<ident>[A-Za-z_][\w.\-]*)
    | (?P<punct>!=|>=|<=|[(),=<>])
)""", re.VERBOSE)

LIST_FIELDS = {"component", "components", "labels"}


def tokenize(jql):
    tokens, pos = [], 0
    while pos < len(jql):
        match = TOKEN.match(jql, pos)
        if not match:
            if jql[pos:].strip() == "":
                break
            raise ValueError(f"cannot tokenize JQL at: {jql[pos:pos + 30]!r}")
        pos = match.end()
        if match.group("str") is not None:
            tokens.append(("str", json.loads(match.group("str"))))
        elif match.group("num") is not None:
            tokens.append(("num", match.group("num")))
        elif match.group("ident") is not None:
            tokens.append(("ident", match.group("ident")))
        else:
            tokens.append(("punct", match.group("punct")))
    return tokens


class Parser:
    """expr := term (OR term)* ; term := pred (AND pred)* ; pred | '(' expr ')'"""

    def __init__(self, tokens):
        self.tokens = tokens
        self.at = 0

    def peek(self):
        return self.tokens[self.at] if self.at < len(self.tokens) else (None, None)

    def next(self):
        token = self.peek()
        self.at += 1
        return token

    def accept_word(self, word):
        kind, value = self.peek()
        if kind == "ident" and value.lower() == word:
            self.at += 1
            return True
        return False

    def expect(self, value):
        kind, got = self.next()
        if got != value:
            raise ValueError(f"expected {value!r} in JQL, got {got!r}")

    def parse(self):
        node = self.parse_expr()
        if self.at != len(self.tokens):
            raise ValueError(f"trailing JQL at token {self.at}: {self.tokens[self.at:]}")
        return node

    def parse_expr(self):
        parts = [self.parse_term()]
        while self.accept_word("or"):
            parts.append(self.parse_term())
        return parts[0] if len(parts) == 1 else ("or", parts)

    def parse_term(self):
        parts = [self.parse_factor()]
        while self.accept_word("and"):
            parts.append(self.parse_factor())
        return parts[0] if len(parts) == 1 else ("and", parts)

    def parse_factor(self):
        kind, value = self.peek()
        if kind == "punct" and value == "(":
            self.next()
            node = self.parse_expr()
            self.expect(")")
            return node
        return self.parse_predicate()

    def parse_values(self):
        self.expect("(")
        values = []
        while True:
            kind, value = self.next()
            if kind == "punct" and value == ")":
                break
            if kind == "punct" and value == ",":
                continue
            values.append(value)
        return values

    def parse_predicate(self):
        kind, field = self.next()
        if kind != "ident":
            raise ValueError(f"expected a field name in JQL, got {field!r}")
        field = field.lower()

        negate = False
        if self.accept_word("not"):
            negate = True

        kind, value = self.next()
        if kind == "ident" and value.lower() == "in":
            nxt_kind, nxt_value = self.peek()
            if nxt_kind == "ident":                # a function, e.g. openSprints()
                self.next()
                self.expect("(")
                self.expect(")")
                return ("func", field, nxt_value.lower(), negate)
            return ("in", field, self.parse_values(), negate)
        if kind == "ident" and value.lower() == "is":
            negate = negate or self.accept_word("not")
            if not self.accept_word("empty"):
                raise ValueError("expected EMPTY after IS in JQL")
            return ("empty", field, None, negate)
        if kind == "punct" and value in ("=", "!=", ">=", "<=", ">", "<"):
            _kind, operand = self.next()
            return ("cmp", field, (value, operand), negate)
        raise ValueError(f"unsupported JQL operator {value!r} on {field!r}")


def _issue_value(issue, field):
    if field in ("component", "components"):
        return issue.get("components") or []
    if field == "parentepic":
        return issue.get("parent_epic")
    if field == "statuscategory":
        return issue.get("status_category")
    if field == "issuetype":
        return issue.get("issuetype")
    return issue.get(field)


def _days_ago(text):
    match = re.fullmatch(r"-(\d+)([dhwm]?)", str(text))
    if not match:
        raise ValueError(f"unsupported relative date {text!r}")
    return int(match.group(1))


def evaluate(node, issue, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    kind = node[0]
    if kind == "and":
        return all(evaluate(part, issue, now) for part in node[1])
    if kind == "or":
        return any(evaluate(part, issue, now) for part in node[1])

    _kind, field, operand, negate = node
    value = _issue_value(issue, field)

    if kind == "in":
        if field in LIST_FIELDS:
            hit = any(v in (value or []) for v in operand)
        else:
            hit = value in operand
    elif kind == "empty":
        hit = not value
    elif kind == "func":
        if field == "sprint" and operand == "opensprints":
            hit = issue.get("sprint") == "open"
        elif field == "sprint" and operand == "futuresprints":
            hit = issue.get("sprint") == "future"
        else:
            raise ValueError(f"unsupported JQL function {operand}() on {field}")
    else:                                            # cmp
        operator, target = operand
        if field in ("updated", "created", "duedate") and \
                str(target).startswith("-"):
            cutoff = now - dt.timedelta(days=_days_ago(target))
            stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")) \
                if value else None
            hit = bool(stamp and stamp >= cutoff)
        elif operator == "=":
            hit = str(value) == str(target)
        elif operator == "!=":
            hit = str(value) != str(target)
        else:
            hit = _compare(operator, value, target)
    return not hit if negate else hit


def _compare(operator, value, target):
    if value is None:
        return False
    left, right = str(value), str(target)
    if operator == ">=":
        return left >= right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    return left < right


def matches(jql, issue, now=None):
    return evaluate(Parser(tokenize(jql)).parse(), issue, now)


# ---------------------------------------------------------------------------
#  Turning a backlog record into a Jira-shaped response
# ---------------------------------------------------------------------------

CATEGORY_KEYS = {"To Do": "new", "In Progress": "indeterminate", "Done": "done"}


def link_parents(issues):
    """Fill in `parent_epic` by walking each issue up to its Epic."""
    by_key = {i["key"]: i for i in issues}
    for issue in issues:
        current, epic = issue, None
        seen = set()
        while current and current["key"] not in seen:
            seen.add(current["key"])
            parent = by_key.get(current.get("parent"))
            if parent is None:
                break
            if parent.get("issuetype") == "Epic":
                epic = parent["key"]
                break
            current = parent
        issue["parent_epic"] = epic
    return issues


def _adf(text):
    return {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def render(issue, fields, expand=None):
    """Build the Jira JSON for one issue, honouring the requested field list."""
    everything = {
        "summary": issue.get("summary", ""),
        "status": {"name": issue.get("status_name", "To Do"),
                   "statusCategory": {
                       "key": CATEGORY_KEYS.get(issue.get("status_category"),
                                                "new"),
                       "name": issue.get("status_category", "To Do")}},
        "assignee": ({"displayName": issue["assignee"]}
                     if issue.get("assignee") else None),
        "issuetype": {"name": issue.get("issuetype", "Task")},
        "components": [{"name": c} for c in issue.get("components") or []],
        "duedate": issue.get("duedate"),
        "updated": issue.get("updated"),
        "created": issue.get("created") or issue.get("updated"),
        "issuelinks": issue.get("issuelinks") or [],
        "priority": {"name": issue.get("priority", "Medium")},
        "labels": issue.get("labels") or [],
        "description": (_adf(issue["description"])
                        if issue.get("description") else None),
        "parent": ({"key": issue["parent"]} if issue.get("parent") else None),
        "customfield_10016": issue.get("story_points"),
        "customfield_10015": issue.get("start_date"),
    }
    out = {"key": issue["key"], "id": issue["key"],
           "fields": {name: everything.get(name) for name in fields
                      if name != "key"}}
    if expand and "changelog" in expand:
        out["changelog"] = {"histories": issue.get("changelog") or []}
    return out


# ---------------------------------------------------------------------------
#  The server
# ---------------------------------------------------------------------------

DEFAULT_FIELDS = [
    {"id": "summary", "name": "Summary", "schema": {"type": "string"}},
    {"id": "customfield_10016", "name": "Story Points",
     "schema": {"type": "number"}},
    {"id": "customfield_10015", "name": "Start date",
     "schema": {"type": "date"}},
    {"id": "customfield_10014", "name": "Epic Link",
     "schema": {"type": "any"}},
]

DEFAULT_USERS = [
    {"accountId": "test-pm", "displayName": "Test PM",
     "emailAddress": "pm@example.com"},
    {"accountId": "dana", "displayName": "Dana",
     "emailAddress": "dana@example.com"},
]


class _Handler(BaseHTTPRequestHandler):
    backlog = []
    components = {}
    pages = []
    fields = DEFAULT_FIELDS
    sprints = {}
    users = DEFAULT_USERS
    calls = []

    def log_message(self, *args):                    # keep test output readable
        return

    def _send(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    # -- GETs --------------------------------------------------------------
    def do_GET(self):                                # noqa: N802 — http.server API
        self.calls.append(("GET", self.path))
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/rest/api/3/myself"):
            return self._send({"displayName": "Test PM",
                               "emailAddress": "pm@example.com",
                               "accountId": "test-pm"})

        if path.startswith("/rest/api/3/field"):
            return self._send(self.fields)

        match = re.match(r"/rest/agile/1.0/board/([^/]+)/sprint", path)
        if match:
            board_id = match.group(1)
            values = self.sprints.get(str(board_id), self.sprints.get("default", []))
            return self._send({"values": values})

        if path.startswith("/rest/agile/1.0/board"):
            query = parse_qs(parsed.query)
            project = (query.get("projectKeyOrId") or [None])[0]
            boards = []
            if project and project in self.components:
                boards.append({"id": 1, "name": f"{project} board"})
            return self._send({"values": boards})

        match = re.match(r"/rest/api/3/project/([^/]+)/components", path)
        if match:
            names = self.components.get(match.group(1), [])
            return self._send([{"name": n} for n in names])

        match = re.match(r"/rest/api/3/project/([^/]+)/?$", path)
        if match:
            key = match.group(1)
            if key not in self.components:
                return self._send({"errorMessages": [f"No project {key}"]}, 404)
            return self._send({"key": key, "name": key, "id": "10000"})

        match = re.match(r"/rest/api/3/issue/([^/]+)/changelog", path)
        if match:
            issue = next((i for i in self.backlog
                          if i["key"] == match.group(1)), None)
            return self._send({"values": (issue or {}).get("changelog") or []})

        match = re.match(r"/rest/api/3/issue/([^/]+)/comment", path)
        if match:
            issue = next((i for i in self.backlog
                          if i["key"] == match.group(1)), None)
            return self._send({"comments": (issue or {}).get("comments") or []})

        match = re.match(r"/rest/api/3/issue/([^/]+)/?$", path)
        if match:
            issue = next((i for i in self.backlog
                          if i["key"] == match.group(1)), None)
            if issue is None:
                return self._send({"errorMessages": [f"No issue {match.group(1)}"]}, 404)
            fields = parse_qs(parsed.query).get("fields", ["summary,issuelinks"])[0]
            return self._send(render(issue, [f.strip() for f in fields.split(",")]))

        if path.startswith("/rest/api/3/user/search"):
            query = (parse_qs(parsed.query).get("query") or [""])[0].lower()
            hits = [u for u in self.users
                    if query in (u.get("displayName") or "").lower()
                    or query in (u.get("emailAddress") or "").lower()]
            return self._send(hits)

        if path.startswith("/wiki/rest/api/content/search"):
            return self._confluence()

        if path.rstrip("/") == "/wiki/rest/api/content":
            query = parse_qs(parsed.query)
            space = (query.get("spaceKey") or [None])[0]
            title = (query.get("title") or [None])[0]
            hits = []
            for page in self.pages:
                if space and page.get("space") != space:
                    continue
                if title and page.get("title") != title:
                    continue
                if title or space:
                    hits.append({
                        "id": page["id"],
                        "title": page["title"],
                        "space": {"key": page.get("space")},
                        "version": {"number": page.get("version", 1)},
                    })
            return self._send({"results": hits})

        return self._send({"errorMessages": [f"no route for {self.path}"]}, 404)

    def _confluence(self):
        query = unquote(parse_qs(urlparse(self.path).query).get("cql", [""])[0])
        space = re.search(r'space\s*=\s*"?([\w-]+)"?', query)
        labels = re.findall(r'"([\w-]+)"', query.split("label", 1)[-1]) \
            if "label" in query else []

        hits = []
        for page in self.pages:
            if space and page.get("space") != space.group(1):
                continue
            if labels and not set(labels) & set(page.get("labels") or []):
                continue
            hits.append({
                "id": page["id"],
                "title": page["title"],
                "body": {"view": {"value": f"<p>{page.get('body', '')}</p>"}},
                "version": {"when": page.get("when", "2026-09-01T00:00:00.000Z")},
                "_links": {"webui": page.get("webui", f"/pages/{page['id']}")},
            })
        return self._send({"results": hits})

    # -- POSTs -------------------------------------------------------------
    def do_POST(self):                               # noqa: N802 — http.server API
        body = self._body()
        self.calls.append(("POST", self.path, body))

        if self.path.startswith("/rest/api/3/search/approximate-count"):
            return self._send({"count": len(self._hits(body["jql"]))})

        if self.path.startswith("/rest/api/3/search/jql"):
            return self._search(body)

        if self.path.startswith("/v1/chat/completions"):
            return self._model(body)

        if self.path.rstrip("/") == "/teams/webhook":
            return self._send({"ok": True}, status=200)

        if self.path.rstrip("/") == "/wiki/rest/api/content":
            fields = body if isinstance(body, dict) else {}
            page = {
                "id": str(3000 + len(self.pages)),
                "title": fields.get("title") or "Untitled",
                "space": (fields.get("space") or {}).get("key") or "APS",
                "body": ((fields.get("body") or {}).get("storage") or {}).get("value") or "",
                "version": 1,
                "labels": [],
            }
            self.pages.append(page)
            return self._send({"id": page["id"], "title": page["title"]}, status=200)

        match = re.match(r"/rest/api/3/issue/([^/]+)/comment", self.path)
        if match:
            issue = next((i for i in self.backlog
                          if i["key"] == match.group(1)), None)
            if issue is None:
                return self._send({"errorMessages": ["no issue"]}, 404)
            issue.setdefault("comments", []).append({
                "body": body.get("body"),
                "created": dt.datetime.now(dt.timezone.utc).isoformat(),
                "author": {"displayName": "Test PM"},
            })
            return self._send({"id": "100"}, status=201)

        if self.path.rstrip("/") == "/rest/api/3/issue":
            fields = body.get("fields") or {}
            project = ((fields.get("project") or {}).get("key")
                       or "APS")
            n = 100 + sum(1 for i in self.backlog if i["key"].startswith(project))
            key = f"{project}-{n}"
            summary = fields.get("summary") or ""
            itype = (fields.get("issuetype") or {}).get("name") or "Story"
            comps = [c.get("name") for c in (fields.get("components") or [])
                     if c.get("name")]
            desc = fields.get("description")
            if isinstance(desc, dict):
                texts = []
                def walk(node):
                    if isinstance(node, dict):
                        if node.get("type") == "text":
                            texts.append(node.get("text") or "")
                        for child in node.get("content") or []:
                            walk(child)
                walk(desc)
                desc = " ".join(texts)
            self.backlog.append({
                "key": key, "project": project, "issuetype": itype,
                "summary": summary, "components": comps,
                "status_name": "To Do", "status_category": "To Do",
                "description": desc or "", "updated": stamp_now(),
                "created": stamp_now(),
            })
            link_parents(self.backlog)
            return self._send({"key": key, "id": key}, status=201)

        return self._send({"errorMessages": [f"no route for {self.path}"]}, 404)

    def do_PUT(self):                                 # noqa: N802
        body = self._body()
        self.calls.append(("PUT", self.path, body))
        match = re.match(r"/wiki/rest/api/content/([^/]+)", self.path)
        if match:
            page = next((p for p in self.pages if str(p.get("id")) == match.group(1)), None)
            if page is None:
                return self._send({"errorMessages": ["no page"]}, 404)
            page["title"] = body.get("title") or page["title"]
            page["version"] = int(page.get("version") or 1) + 1
            storage = ((body.get("body") or {}).get("storage") or {}).get("value")
            if storage:
                page["body"] = storage
            return self._send({"id": page["id"], "title": page["title"],
                               "version": {"number": page["version"]}})
        match = re.match(r"/rest/api/3/issue/([^/]+)", self.path)
        if not match:
            return self._send({"errorMessages": [f"no route for {self.path}"]}, 404)
        issue = next((i for i in self.backlog if i["key"] == match.group(1)), None)
        if issue is None:
            return self._send({"errorMessages": ["no issue"]}, 404)
        fields = body.get("fields") or {}
        if "summary" in fields:
            issue["summary"] = fields["summary"]
        if "duedate" in fields:
            issue["duedate"] = fields["duedate"]
        if "assignee" in fields:
            person = fields["assignee"] or {}
            issue["assignee"] = person.get("displayName") or person.get("accountId")
        if "customfield_10016" in fields:
            issue["story_points"] = fields["customfield_10016"]
        if "description" in fields:
            desc = fields["description"]
            if isinstance(desc, dict):
                texts = []
                def walk(node):
                    if isinstance(node, dict):
                        if node.get("type") == "text":
                            texts.append(node.get("text") or "")
                        for child in node.get("content") or []:
                            walk(child)
                walk(desc)
                issue["description"] = " ".join(texts)
            else:
                issue["description"] = desc
        return self._send({})

    def _hits(self, jql):
        try:
            node = Parser(tokenize(jql)).parse()
        except ValueError as err:
            raise AssertionError(f"fake Jira could not read JQL: {err}\n{jql}")
        return [i for i in self.backlog if evaluate(node, i)]

    def _search(self, body):
        hits = self._hits(body["jql"])
        page_size = int(body.get("maxResults") or 50)
        start = int(body.get("nextPageToken") or 0)
        page = hits[start:start + page_size]
        payload = {"issues": [render(i, body.get("fields") or ["key"],
                                    body.get("expand")) for i in page],
                   "isLast": start + page_size >= len(hits)}
        if start + page_size < len(hits):
            payload["nextPageToken"] = str(start + page_size)
        return self._send(payload)

    def _model(self, body):
        system = next((m["content"] for m in body.get("messages", [])
                       if m.get("role") == "system"), "")
        user = next((m["content"] for m in body.get("messages", [])
                     if m.get("role") == "user"), "")
        if "Extract decisions and actions" in system:
            reply = json.dumps({
                "decisions": [{"text": "Rotate certificates by 17 Sep",
                               "owner": "A. Lee"}],
                "actions": [{"title": "Book the rotation window",
                             "owner": "B. Ray", "issuetype": "Task",
                             "workstream": "SDX"}],
            })
        elif "file this note" in system.lower() or "JSON object" in system:
            reply = json.dumps({
                "product": "IP", "workstream": "SDX", "issuetype": "Story",
                "title": "Export the SSO audit log for tenant admins",
                "criteria": "Given a tenant admin, when they request an audit export, then a CSV is emailed to them.",
            })
        elif "Draft a clearer title" in system:
            reply = '[{"key":"APS-11","title":"Fix retry handling in the exchange client"}]'
        elif "Draft acceptance criteria" in system:
            reply = '[{"key":"APS-20","criteria":"Given a tenant over the limit, requests are rejected with 429."}]'
        elif "JSON array" in system:
            reply = "[]"
        else:
            reply = ("### What changed since last week\n"
                     "- Fake model reply for the end-to-end test.\n")
        _ = user
        return self._send({"choices": [{"message": {"role": "assistant",
                                                    "content": reply}}]})


def stamp_now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


class FakeJira:
    """Run the stand-in on a spare port for the length of a test."""

    def __init__(self, backlog, components=None, pages=None,
                 fields=None, sprints=None, users=None):
        _Handler.backlog = link_parents(backlog)
        _Handler.components = components or {}
        _Handler.pages = pages or []
        _Handler.fields = fields if fields is not None else DEFAULT_FIELDS
        _Handler.users = users if users is not None else list(DEFAULT_USERS)
        _Handler.sprints = sprints or {
            "1": [{"id": 10, "name": "Sprint 42", "state": "active",
                   "goal": "Ship certificate rotation",
                   "startDate": "2026-08-27T00:00:00.000+0000",
                   "endDate": "2026-09-10T00:00:00.000+0000"}],
            "default": [{"id": 10, "name": "Sprint 42", "state": "active",
                         "goal": "Ship certificate rotation",
                         "startDate": "2026-08-27T00:00:00.000+0000",
                         "endDate": "2026-09-10T00:00:00.000+0000"}],
        }
        _Handler.calls = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    @property
    def calls(self):
        return _Handler.calls

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
