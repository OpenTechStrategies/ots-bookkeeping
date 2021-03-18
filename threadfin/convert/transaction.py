import math
import re
import sys

import util as u


class UnimplementedError(Exception):
    pass


rx = {}
# If a string is only these chars, it's a string, not a regex
rx["not_regex"] = re.compile(r"^[A-Za-z0-9-/_, ]+$")


class Transaction(dict):
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

        # Init hash values we'll later use to fill out the entry
        self.vals = {"flag": "txn", "tags": set()}
        for field in "cardholder category code comment payee narration".split(" "):
            self.vals[field] = ""

    def custom_match_comment(self, patterns, vals):
        """Step through the patterns and match them against
        vals['comment'].  Do some replace/processing based on the
        contents of patterns[match]

        """
        p = dict(patterns)
        for match, custom in p.items():
            if isinstance(match, type("")):
                if rx["not_regex"].match(match):
                    if match in self.vals["comment"]:
                        vals = self.custom_replace(custom, vals)
                else:
                    m = re.compile(match)
                    patterns[m] = patterns[match]
                    del patterns[match]
                    match = m

            if isinstance(match, re.Pattern):
                if match.search(self.vals["comment"]):
                    vals = self.custom_replace(custom, vals)
        return vals

    def custom_replace(self, custom, vals):
        """Twiddle self.vals as per some custom rules."""

        # If the custom rule specifies a date field, then let's only
        # do this on that date. TODO: allow date ranges.
        if "date" in custom:
            if isinstance(custom["date"], type([])):
                if not vals["date"] in [str(d) for d in custom["date"]]:
                    return vals
            else:
                if not vals["date"] == str(custom["date"]):
                    return vals

        # Overwrite/update vals with those from the custom data
        # structure
        for k, v in custom.items():
            if k == "tags":
                if [i for i in v if len(i) == 1]:
                    u.err("Tag is a string but should be a list: %s\n" % custom.items())
                vals[k].update(set(v))
            elif k == "comment":
                vals[k] = "%s\n             %s" % (v, vals[k])
            elif k == "date":
                continue
            else:
                vals[k] = v
        return vals

    def interpolate(self, vals):
        if vals["tags"]:
            vals["tags"] = " #" + " #".join(vals["tags"])
        else:
            vals["tags"] = ""

        if "unfiled" not in vals:
            vals["unfiled"] = ""

        used = "currency date flag payee narration tags account account2 amount unfiled".split(
            " "
        )
        vals["add_meta"] = "\n".join(
            ['   %s: "%s"' % (k, vals[k]) for k in vals if vals[k] and k not in used]
        )
        if vals["add_meta"] and not vals["add_meta"].endswith("\n"):
            vals["add_meta"] += "\n"
        return (
            '{date} {flag} "{payee}" "{narration}"{tags}\n{add_meta}'
            + "   {account}{unfiled}            {amount} USD\n"
            + "   {account2}{unfiled}\n\n"
        ).format(**vals)


class Transactions(list):
    """A list of Transaction instances.

    This is just a list we're wrapping in a class so we can add
    methods to it.

    """

    pass
