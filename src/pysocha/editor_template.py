"""Create a Markdown draft from an editor buffer without changing the source."""
import json
import re
import sys
from datetime import datetime
from uuid import uuid4

import yaml
from slugify import slugify

FIELD = re.compile(r"\{\$([A-Za-z_][A-Za-z0-9_]*)\}")
HEADER = re.compile(r"\A(\ufeff?---[ \t]*\r?\n)(.*?)(^---[ \t]*(?:\r?\n|\Z))", re.MULTILINE | re.DOTALL)


def fields(source):
    return list(dict.fromkeys(name for name in FIELD.findall(source)
                              if name not in ("title", "current_time")))


def render_header(header, values):
    # A bare {$field} looks like a flow mapping to a YAML parser. Mask markers
    # before parsing so bare, quoted, and embedded fields behave alike.
    prefix = "pysochafield" + uuid4().hex
    markers = {}

    def mask(match):
        key = prefix + str(len(markers)) + "z"
        markers[key] = values[match.group(1)]
        return key

    masked = FIELD.sub(mask, header)
    root = yaml.compose(masked, Loader=yaml.SafeLoader)
    fixed = {}
    if isinstance(root, yaml.MappingNode):
        meta = {k.value: v for k, v in root.value if isinstance(k, yaml.ScalarNode)
                and isinstance(v, yaml.ScalarNode)}
        title = meta.get("Title")
        if title is not None and prefix not in title.value:
            fixed[title.start_mark.index] = values["title"]
            # TNL's original starter predates named placeholders.
            if title.value == "TITLE" and "PostedDate" in meta:
                fixed[meta["PostedDate"].start_mark.index] = values["current_time"]

    parts = []
    offset = 0
    marker = re.compile(prefix + r"[0-9]+z")
    for token in yaml.scan(masked, Loader=yaml.SafeLoader):
        if not isinstance(token, yaml.ScalarToken):
            continue
        start, end = token.start_mark.index, token.end_mark.index
        if start in fixed:
            value = fixed[start]
        elif prefix in token.value:
            value = marker.sub(lambda m: markers[m.group()], token.value)
        else:
            continue
        parts.extend((masked[offset:start], json.dumps(value, ensure_ascii=False)))
        # A block scalar can own the newline before the next YAML key.
        if token.style in ("|", ">") and masked[start:end].endswith("\n"):
            parts.append("\r\n" if masked[start:end].endswith("\r\n") else "\n")
        offset = end
    parts.append(masked[offset:])
    # Comments can contain fields, too. Their values cannot affect YAML types.
    return marker.sub(lambda m: markers[m.group()], "".join(parts))


def render(source, title, answers, now=None):
    title = title.strip()
    slug = slugify(title)
    if not slug:
        raise ValueError("Enter a title with a letter or number for the file name.")
    if re.fullmatch(r"con|prn|aux|nul|com[1-9]|lpt[1-9]|0-basetemplate", slug):
        raise ValueError("This title gives a reserved file name. Choose another title.")
    values = {field: answers.get(field, "") for field in fields(source)}
    values.update(title=title, current_time=(now or datetime.now().astimezone()).isoformat(timespec="seconds"))
    match = HEADER.match(source)
    front = ""
    if match:
        front = match[1] + render_header(match[2], values) + match[3]
        source = source[match.end():]
    return {"filename": slug + ".md", "text": front + FIELD.sub(lambda m: values[m[1]], source)}


def main():
    request = json.load(sys.stdin)
    try:
        if "title" in request:
            result = render(request["source"], request["title"], request["fields"])
        else:
            result = {"fields": fields(request["source"])}
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        line = " on line {}".format(mark.line + 2) if mark else ""
        result = {"error": "Check the template's YAML{}: {}.".format(line, error.problem or "invalid syntax")}
    except ValueError as error:
        result = {"error": str(error)}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
