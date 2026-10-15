"""Read-only Jira site and project structure observations.

Jira administration metadata describes available fields and issue types, not
business ownership. Missing permissions are explicitly reflected in coverage.
"""
from core import sources


def inspect(cfg, projects):
    jira = cfg["jira"]
    root = jira["base_url"].rstrip("/")
    observations = {"projects": [], "coverage": "complete"}
    projects = list(dict.fromkeys(str(x).strip() for x in projects if x))
    if not projects:
        observations["coverage"] = "unconfigured"
        return observations
    for project in projects:
        item = {"project": project, "status": "complete",
                "issue_types": [], "components": [], "versions": []}
        observations["projects"].append(item)
        from urllib.parse import quote
        url = root + "/rest/api/3/project/" + quote(project, safe="")
        try:
            response = sources.send("GET", url, auth=(jira["email"], jira["api_token"]),
                                    headers={"Accept": "application/json"}, timeout=60)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("issueTypes"), list):
                raise ValueError("Project metadata did not include issue types")
            item["issue_types"] = [{"id": str(x.get("id", "")),
                                    "name": x.get("name"),
                                    "subtask": bool(x.get("subtask")),
                                    "hierarchy_level": x.get("hierarchyLevel")}
                                   for x in data["issueTypes"]]
            # Site-wide fields are candidates, not proof of applicability to
            # this project's issue screens or configured workstreams.
            item["fields"] = []
            try:
                field_response = sources.send(
                    "GET", root + "/rest/api/3/field",
                    auth=(jira["email"], jira["api_token"]),
                    headers={"Accept": "application/json"}, timeout=60)
                field_response.raise_for_status()
                field_data = field_response.json()
                if not isinstance(field_data, list):
                    raise ValueError("Unexpected Jira field catalog")
                item["fields"] = [
                    {"id": str(f.get("id", "")), "name": f.get("name"),
                     "custom": bool(f.get("custom")), "schema": f.get("schema") or {}}
                    for f in field_data if isinstance(f, dict)]
                item["fields_coverage"] = "site catalogue; project applicability unverified"
            except Exception as exc:
                item["fields_coverage"] = "unavailable: {}: {}".format(
                    type(exc).__name__, str(exc)[:120])
                item["status"] = "partial"
                observations["coverage"] = "partial"
            # Components/versions may be unavailable in project metadata.
            for name, field in (("components", "components"), ("versions", "versions")):
                value = data.get(field)
                if isinstance(value, list):
                    item[name] = [{"id": str(v.get("id", "")), "name": v.get("name")}
                                  for v in value if isinstance(v, dict)]
                else:
                    item[name + "_coverage"] = "unavailable in project response"
        except Exception as exc:
            item["status"] = "unavailable"
            item["detail"] = "{}: {}".format(type(exc).__name__, str(exc)[:160])
            observations["coverage"] = "partial"
    return observations
