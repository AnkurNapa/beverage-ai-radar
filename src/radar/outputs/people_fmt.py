from __future__ import annotations


def people_md(company) -> str:
    """People as markdown: '[Name](linkedin) (Role), ...'. Falls back to the
    plain key_people string when no structured people list is present."""
    people = getattr(company, "people", None) or []
    if people:
        parts = []
        for p in people:
            name = p.get("name", "")
            link = p.get("linkedin")
            role = p.get("role")
            named = f"[{name}]({link})" if link else name
            parts.append(f"{named} ({role})" if role else named)
        return ", ".join(parts)
    return company.key_people or ""
