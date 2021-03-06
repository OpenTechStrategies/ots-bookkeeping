import datetime
import io
import os
import pprint
import subprocess
import sys
import time
from typing import (Any, Dict, Iterator, Optional, Sequence, TypeVar, Union,
                    cast)

import yaml
from dateutil import parser as dateparse
from moneyed import Money  # type: ignore

import mustache

VERBOSE = False

pp = pprint.PrettyPrinter(indent=4, width=120).pprint
pf = pprint.PrettyPrinter(indent=4, width=120).pformat


def bean_query(bean_file: str, query: str, csv: bool = False) -> str:
    csv_param = "-f csv" if csv else ""
    cmd = f'bean-query {csv_param} {bean_file} "{query}";'
    return run_command(cmd).strip()


def bean_query_csv(bean_file: str, query: str) -> str:
    return bean_query(bean_file, query, True)


def current_dir_name() -> str:
    """Returns current directory name as a string"""
    return os.path.split(os.path.realpath(os.getcwd()))[1]


def err(msg: str) -> None:
    if not msg.endswith("\n"):
        msg += "\n"
    sys.stderr.write(msg)
    sys.exit(-1)


def get_config(fname: str) -> Dict[str, Any]:
    """Grab config.yaml, parse and return"""

    with open(fname) as fh:
        settings = cast(Dict[str, Any], yaml.safe_load(fh.read()))

    # If relative dir specified for templates, it's relative to the
    # codebase (e.g. this file).
    if settings.get("template_dir", "").startswith("/"):
        settings["template_dir"] = os.path.join(
            os.path.join(os.path.realpath(os.path.split(__file__)[0])),
            settings.get("template_dir", ""),
        )

    settings["templates"] = mustache.load_templates(settings["template_dir"])

    return settings


def get_threadfin_yaml(fname: str) -> Dict[str, Any]:
    with open(fname) as fh:
        settings = yaml.safe_load(fh.read())
    return cast(Dict[str, Any], settings)


# In the Indexable class below, we reference Indexable as a type inside the
# Indexable class.  At that point, it isn't defined yet.  This causes a mypy
# error, so we reference this TypeVar instead.
Indexable_T = TypeVar("Indexable_T", bound="Indexable")


class Indexable:
    """An indexable iterator made from a list.

    We can treat this just like an iterator with a known length that we can
    index.  We can look at the next item without looping.  We could, if we
    implemented 'prev' also look at the previous item if we want."""

    def __init__(self, indexable: Sequence[Any]) -> None:
        self.length = len(indexable)
        self.current = 0
        self.indexable = indexable

    def __iter__(self) -> Iterator[Any]:
        return iter(self.indexable)

    def next(self) -> Optional[Any]:
        """Return the next item in the iteration, and advance the current pointer."""
        ret = self.curr()
        self.current += 1
        return ret

    def done(self) -> bool:
        """Return True unless there are more items left to return."""
        return self.current >= self.length

    def curr(self) -> Any:
        """Return the current item in the sequence."""
        if self.done():
            return None
        return self.indexable[self.current]


def int2word(n: int) -> str:
    """
    convert an integer number n into a string of english words
    from https://www.daniweb.com/programming/software-development/code/216839/number-to-word-converter-python
    """

    ones = [
        "",
        "One ",
        "Two ",
        "Three ",
        "Four ",
        "Five ",
        "Six ",
        "Seven ",
        "Eight ",
        "Nine ",
    ]
    tens = [
        "Ten ",
        "Eleven ",
        "Twelve ",
        "Thirteen ",
        "Fourteen ",
        "Fifteen ",
        "Sixteen ",
        "Seventeen ",
        "Eighteen ",
        "Nineteen ",
    ]
    twenties = [
        "",
        "",
        "Twenty ",
        "Thirty ",
        "Forty ",
        "Fifty ",
        "Sixty ",
        "Seventy ",
        "Eighty ",
        "Ninety ",
    ]
    thousands = [
        "",
        "Thousand ",
        "Million ",
        "billion ",
        "trillion ",
        "quadrillion ",
        "quintillion ",
        "sextillion ",
        "septillion ",
        "octillion ",
        "nonillion ",
        "decillion ",
        "undecillion ",
        "duodecillion ",
        "tredecillion ",
        "quattuordecillion ",
        "quindecillion",
        "sexdecillion ",
        "septendecillion ",
        "octodecillion ",
        "novemdecillion ",
        "vigintillion ",
    ]

    # break the number into groups of 3 digits using slicing
    # each group representing hundred, thousand, million, billion, ...
    n3 = []
    r1 = ""
    # create numeric string
    ns = str(n)
    for k in range(3, 33, 3):
        r = ns[-k:]
        q = len(ns) - k
        # break if end of ns has been reached
        if q < -2:
            break
        else:
            if q >= 0:
                n3.append(int(r[:3]))
            elif q >= -1:
                n3.append(int(r[:2]))
            elif q >= -2:
                n3.append(int(r[:1]))
        r1 = r

    # print n3  # test

    # break each group of 3 digits into
    # ones, tens/twenties, hundreds
    # and form a string
    nw = ""
    for i, x in enumerate(n3):
        b1 = x % 10
        b2 = (x % 100) // 10
        b3 = (x % 1000) // 100
        # print b1, b2, b3  # test
        if x == 0:
            continue  # skip
        else:
            t = thousands[i]
        if b2 == 0:
            nw = ones[b1] + t + nw
        elif b2 == 1:
            nw = tens[b1] + t + nw
        elif b2 > 1:
            nw = twenties[b2] + ones[b1] + t + nw
        if b3 > 0:
            nw = ones[b3] + "hundred " + nw
    return nw


class OpenableIOString:
    def __init__(self, in_string: str, byte: bool = True) -> None:
        """PETL expects an openable file-like object, but all we have is an
        iostring.  Rather than write it to disk and then call PETL to
        read it, we'll wrap the iostring in this class that implements
        open.

        If BYTES is true, we'll encode as a byte stream, otherwise,
        we'll use stream io.  PETL wants bytes, as it tries to open
        with 'wb'.  Hmm... maybe we should just encode as needed in
        the open method.

        """
        self.io: io.IOBase
        if byte:
            self.io = io.BytesIO(in_string.encode("UTF-8"))
        else:
            self.io = io.StringIO(in_string)

    def open(self, *args: str, **kwargs: Any) -> io.IOBase:
        return self.io


def parse_date(string: str, ignore_error: bool = False) -> Optional[datetime.date]:
    "Return a date object representation of STRING."
    try:
        return dateparse.parse(string).date()
    except ValueError:
        if ignore_error:
            return None
        else:
            raise


def parse_money(money_string: str, ignore_error: bool = False) -> Money:
    """Assumes string is USD, returns money object

    If you pass it an int, it will cast to string.  If you're already
    a Money type, we'll just return what we get.

    """

    if isinstance(money_string, type(Money(0, "USD"))):
        return money_string

    money_string = str(money_string).strip()
    if money_string.startswith("$"):
        money_string = money_string[1:]
    if "," in money_string:
        money_string = money_string.replace(",", "")
    if not ignore_error:
        return Money(amount=money_string, currency="USD")

    try:
        return Money(amount=money_string, currency="USD")
    except ValueError:
        if ignore_error:
            return None
        else:
            raise


def pdf2txt(pdfname: str) -> str:
    """Convert pdfname to text, cache the result, return the text"""
    txtname = os.path.splitext(pdfname)[0] + ".txt"
    if not os.path.exists(txtname):
        run_command("pdftotext -layout %s %s" % (pdfname, txtname))
        txt = slurp(txtname)
    return txt


def rm_file(fname: str, verbose: bool = False) -> None:
    """Remove the file unless we're in verbose mode for debugging purposes"""

    # If caller specifies verbose=False, override the package VERBOSE
    if verbose or (VERBOSE and not verbose == False):
        return
        verbose = True

    os.unlink(fname)


class RunCommandError(subprocess.CalledProcessError):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        subprocess.CalledProcessError.__init__(self, *args, **kwargs)
        self.dump()

    def dump(self) -> None:
        sys.stderr.write(self.output)
        sys.stderr.write(self.stderr)
        sys.stderr.write(str(self.returncode))
        sys.stderr.write("\n")


def run_command(cmd: str, verbose: bool = False, ignore_error: bool = False) -> str:
    """Run CMD, return output.  If command returns an error, raise an
    exception that contains the exception string.  If that error isn't
    trapped upstream, print the error and bail.

    CMD is a string containing a command that can be run in a shell.
    """

    # If caller specifies verbose=False, override the package VERBOSE
    if verbose or (VERBOSE and not verbose == False):
        verbose = True

    # Be verbose if we're supposed. Be verbose about sudo even when
    # the verbose flag isn't set.
    if cmd.startswith("sudo") and cmd != "sudo -vn":
        if subprocess.check_output("sudo -vn", shell=True):
            print("Please grant sudo access to execute: `%s`" % cmd)
        elif verbose:
            print("Using existing sudo access to execute: `%s`" % cmd)
    elif verbose:
        print(cmd)

    p = subprocess.Popen(
        cmd, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=os.environ
    )
    output_b, errors_b = p.communicate()
    output = output_b.decode("UTF-8")
    errors = errors_b.decode("UTF-8")

    # Wait until process terminates (without using p.wait())
    while p.poll() is None:
        # Process hasn't exited yet, let's wait some
        time.sleep(0.5)
    return_code = p.returncode

    if return_code != 0 and not ignore_error:
        raise RunCommandError(
            cmd=cmd, returncode=return_code, output=output, stderr=errors
        )
    return output


def slurp_bytes(fname: str) -> bytes:
    with open(fname, "rb") as fh:
        bytestr = fh.read()
        return bytestr


def slurp(fname: str, decode: str = "utf-8") -> str:
    """Read file named FNAME from disk and return contents as a string.

    DECODE is the expected encoding of the file.  This func will
    decode it from bytes to a string using this setting.  It defaults
    to UTF-8.

    """
    with open(fname, "rb") as fh:
        bytestr = fh.read()
        try:
            return bytestr.decode(decode)
        except UnicodeDecodeError:
            return str(bytestr)


def tomorrow(date: Union[str, datetime.date]) -> datetime.date:
    if not isinstance(date, type(datetime.datetime.now())):
        date = dateparse.parse(cast(str, date))
    return date + datetime.timedelta(days=1)
