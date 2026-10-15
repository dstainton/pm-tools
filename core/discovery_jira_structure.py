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
