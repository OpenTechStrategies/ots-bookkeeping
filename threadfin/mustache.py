import os
import sys
from typing import Any, Dict, cast

import pystache
from lxml import etree  # type: ignore


def load_templates(fname: str) -> Dict[str, str]:
    templates = {}

    full_path = os.path.join(os.path.split(os.path.realpath(__file__))[0], fname)
    if os.path.isdir(full_path):
        tree = etree.parse(os.path.join(full_path, "mustache.html"))
    else:
        tree = etree.parse(os.path.join(full_path))

    root = tree.getroot()
    if root.tag != "mustache":
        # To avoid a circular import, we don't call u.err
        sys.exit("This isn't an xml file full of mustache templates")

    for template in root:
        xml = "\n".join(
            etree.tostring(template, pretty_print=True)
            .decode("UTF-8")
            .strip()
            .split("\n")[1:-1]
        )
        if xml.strip().startswith("<html"):
            xml = "<!DOCTYPE html>\n%s" % xml
        templates[template.get("name")] = xml

    return templates


def render(templates: Dict[str, str], template: str, dic: Dict[str, Any]) -> str:
    return pystache.render(templates[template], dic)
