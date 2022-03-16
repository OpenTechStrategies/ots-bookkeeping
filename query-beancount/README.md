                           query-beancount
                           ===============

# Overview

TBD: write real README

# Setup

There's a comment near the top of 'query-beancount' listing all the
Python3 packages one might have to install to get this working.  Note
that all python3-levenshtein does is suppress a run-time warning from
python3-fuzzywuzzy about using a slow pure-python SequenceMatcher and
how installing Levenshtein would speed it up.

For convenience, there is a symlink in ${OTS_DIR}/finances/qb to
./query-beancount.  You might typically invoke query-beancount with
this link:

     ./qb validate
