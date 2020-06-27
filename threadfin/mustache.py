from lxml import etree
import os
import pystache


def load_templates(fname):
    templates = {}

    full_path = os.path.join(
        os.path.split(
            os.path.realpath(__file__))[0],
        fname)
    if os.path.isdir(full_path):
        tree = etree.parse(os.path.join(full_path, "mustache.html"))
    else:
        tree = etree.parse(os.path.join(full_path))

    root = tree.getroot()
    if root.tag != "mustache":
        sys.stderr.write(
            "Um... this isn't an xml file full of mustache templates")
        sys.exit(2)

    for template in root:
        xml = "\n".join(etree.tostring(template, pretty_print=True).decode(
            "UTF-8").strip().split("\n")[1:-1])
        if xml.strip().startswith('<html'):
            xml = "<!DOCTYPE html>\n%s" % xml
        templates[template.get('name')] = xml

    return templates


def render(templates, template, dic):
    return pystache.render(templates[template], dic)
