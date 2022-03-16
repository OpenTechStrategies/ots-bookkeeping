                           query-beancount
                           ===============

# Overview

The `query-beancount` program has subcommands that generate various
reports about the finances of Open Tech Strategies, LLC.

This tree is very much a work-in-progress.  The code runs for us, but
probably requires OTS-specific environmental tweaks that we haven't
yet documented.  It also depends on access to OTS's financial data,
which is not public.  Eventually, we'll provide some sample data here;
until then, this code is probably only useful for OTS partners.

The documentation of subcommands given in the `__doc__` string at the
top of `query-beancount' is out-of-date: some of those subcommands
don't behave correctly, or don't run at all, or in some cases don't
even exist anymore.  We're gradually getting it all fixed up.  The
commands we run on a regular basis are the ones that work.

# Setup

There's a comment near the top of 'query-beancount' listing all the
Python3 packages one might have to install to get this working.  Note
that all python3-levenshtein does is suppress a run-time warning from
python3-fuzzywuzzy about using a slow pure-python SequenceMatcher and
how installing Levenshtein would speed it up.
