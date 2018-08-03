# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import Counter
from collections import OrderedDict
from curses import tigetstr, tparm
from functools import partial
import re
from six.moves import StringIO
import sys
import time
import traceback

import blessings
from mock import patch
import pytest

from pyout import Tabular as TheRealTabular
from pyout.field import StyleFunctionError
from pyout.common import ContentError

from pyout.tests.utils import assert_contains, assert_eq_repr

# TestTerminal, unicode_cap, and unicode_parm are copied from
# blessings' tests.

TestTerminal = partial(blessings.Terminal, kind='xterm-256color')


class Tabular(TheRealTabular):
    """Test-specific subclass of pyout.Tabular.
    """

    def __init__(self, *args, **kwargs):
        fd = StringIO()
        with patch("pyout.tabular.Terminal", TestTerminal):
            super(Tabular, self).__init__(
                *args, force_styling=True, stream=fd, **kwargs)

    @property
    def stdout(self):
        return self.term.stream.getvalue()


def unicode_cap(cap):
    """Return the result of ``tigetstr`` except as Unicode."""
    return tigetstr(cap).decode('latin1')


def unicode_parm(cap, *parms):
    """Return the result of ``tparm(tigetstr())`` except as Unicode."""
    return tparm(tigetstr(cap), *parms).decode('latin1')


COLORNUMS = {"black": 0, "red": 1, "green": 2, "yellow": 3, "blue": 4,
             "magenta": 5, "cyan": 6, "white": 7}


def capres(name, value):
    """Format value with CAP key, followed by a reset.
    """
    if name in COLORNUMS:
        prefix = unicode_parm("setaf", COLORNUMS[name])
    else:
        prefix = unicode_cap(name)
    return prefix + value + unicode_cap("sgr0")


def eq_repr_noclear(actual, expected):
    """Like `eq_repr`, but strip clear-related codes from `actual`.
    """
    clear_codes = [re.escape(unicode_cap(x)) for x in ["el", "ed", "cuu1"]]
    match = re.match("(?:{}|{}|{})*(.*)".format(*clear_codes), actual)
    assert match, "This should always match"
    return repr(match.group(1)) == repr(expected)


assert_contains_nc = partial(assert_contains, cmp=eq_repr_noclear)


class AttrData(object):
    """Store `kwargs` as attributes.

    For testing tabular calls to construct row's data from an objects
    attributes.

    This doesn't use __getattr__ to map dict keys to attributes because then
    we'd have to handle a KeyError for the "missing" column tests.
    """
    def __init__(self, **kwargs):
        for attr, value in kwargs.items():
            setattr(self, attr, value)


def test_tabular_write_color():
    out = Tabular(["name"],
                  style={"name": {"color": "green", "width": 3}})

    out({"name": "foo"})

    expected = capres("green", "foo") + "\n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_empty_string():
    out = Tabular()
    out({"name": ""})
    assert_eq_repr(out.stdout, "\n")


def test_tabular_write_missing_column():
    out = Tabular(columns=["name", "status"])
    out({"name": "solo"})
    assert_eq_repr(out.stdout, "solo \n")


def test_tabular_write_missing_column_missing_text():
    out = Tabular(columns=["name", "status"],
                  style={"status":
                         {"missing": "-"}})
    out({"name": "solo"})
    assert_eq_repr(out.stdout, "solo -\n")


def test_tabular_write_list_value():
    out = Tabular(columns=["name", "status"])
    out({"name": "foo", "status": [0, 1]})
    assert_eq_repr(out.stdout, "foo [0, 1]\n")


def test_tabular_write_missing_column_missing_object_data():
    data = AttrData(name="solo")

    out = Tabular(columns=["name", "status"],
                  style={"status":
                         {"missing": "-"}})
    out(data)
    assert_eq_repr(out.stdout, "solo -\n")


def test_tabular_write_columns_from_orderdict_row():
    out = Tabular(style={"name": {"width": 3},
                         "id": {"width": 3},
                         "status": {"width": 9},
                         "path": {"width": 8}})

    row = OrderedDict([("name", "foo"),
                       ("id", "001"),
                       ("status", "installed"),
                       ("path", "/tmp/foo")])
    out(row)

    assert_eq_repr(out.stdout, "foo 001 installed /tmp/foo\n")


@pytest.mark.parametrize("row", [["foo", "ok"],
                                 {"name": "foo", "status": "ok"}],
                         ids=["sequence", "dict"])
def test_tabular_write_columns_orderdict_mapping(row):
    out = Tabular(OrderedDict([("name", "Long name"),
                               ("status", "Status")]),
                  style={"header_": {},
                         "name": {"width": 10},
                         "status": {"width": 6}})

    out(row)

    expected = ("Long name  Status\n"
                "foo        ok    \n")
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_data_as_list():
    out = Tabular(["name", "status"],
                  style={"name": {"width": 3},
                         "status": {"width": 9}})

    out(["foo", "installed"])
    out(["bar", "unknown"])

    expected = "foo installed\nbar unknown  \n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_header():
    out = Tabular(["name", "status"],
                  style={"header_": {},
                         "name": {"width": 10},
                         "status": {"width": 10}})

    out({"name": "foo",
         "status": "installed"})
    out({"name": "bar",
         "status": "installed"})

    expected = ("name       status    \n"
                "foo        installed \n"
                "bar        installed \n")
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_data_as_object():
    out = Tabular(["name", "status"],
                  style={"name": {"width": 3},
                         "status": {"width": 9}})

    out(AttrData(name="foo", status="installed"))
    out(AttrData(name="bar", status="unknown"))

    expected = "foo installed\nbar unknown  \n"
    assert out.stdout == expected


def test_tabular_write_different_data_types_same_output():
    style = {"header_": {},
             "name": {"width": 10},
             "status": {"width": 10}}

    out_list = Tabular(["name", "status"], style=style)
    out_dict = Tabular(["name", "status"], style=style)
    out_od = Tabular(style=style)

    out_list(["foo", "installed"])
    out_list(["bar", "installed"])

    out_dict({"name": "foo", "status": "installed"})
    out_dict({"name": "bar", "status": "installed"})

    out_od(OrderedDict([("name", "foo"),
                        ("status", "installed")]))
    out_od(OrderedDict([("name", "bar"),
                        ("status", "installed")]))

    assert out_dict.stdout == out_list.stdout
    assert out_dict.stdout == out_od.stdout


def test_tabular_write_header_with_style():
    out = Tabular(["name", "status"],
                  style={"header_": {"underline": True},
                         "name": {"width": 4},
                         "status": {"width": 9,
                                    "color": "green"}})
    out({"name": "foo",
         "status": "installed"})

    expected = capres("smul", "name") + " " + \
               capres("smul", "status") + "   " + "\nfoo  " + \
               capres("green", "installed") + "\n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_nondefault_separator():
    out = Tabular(["name", "status"],
                  style={"header_": {},
                         "separator_": " | ",
                         "name": {"width": 4},
                         "status": {"width": 9}})
    out({"name": "foo",
         "status": "installed"})
    out({"name": "bar",
         "status": "installed"})

    expected = ("name | status   \n"
                "foo  | installed\n"
                "bar  | installed\n")
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_data_as_list_no_columns():
    out = Tabular(style={"name": {"width": 3},
                         "status": {"width": 9}})
    with pytest.raises(ValueError):
        out(["foo", "installed"])


def test_tabular_write_style_override():
    out = Tabular(["name"],
                  style={"name": {"color": "green", "width": 3}})
    out({"name": "foo"},
        style={"name": {"color": "black", "width": 3}})

    expected = capres("black", "foo") + "\n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_default_style():
    out = Tabular(["name", "status"],
                  style={"default_": {"width": 3}})
    out({"name": "foo", "status": "OK"})
    out({"name": "bar", "status": "OK"})

    expected = ("foo OK \n"
                "bar OK \n")
    assert out.stdout == expected


def test_tabular_write_multicolor():
    out = Tabular(["name", "status"],
                  style={"name": {"color": "green", "width": 3},
                         "status": {"color": "white", "width": 7}})
    out({"name": "foo", "status": "unknown"})

    expected = capres("green", "foo") + " " + \
               capres("white", "unknown") + "\n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_empty_string_nostyle():
    out = Tabular(style={"name": {"color": "green"}})
    out({"name": ""})
    assert_eq_repr(out.stdout, "\n")


def test_tabular_write_style_flanking():
    out = Tabular(columns=["name", "status"],
                  style={"status": {"underline": True,
                                    "align": "center",
                                    "width": 7},
                         # Use "," to more easily see spaces in fields.
                         "separator_": ","})
    out({"name": "foo", "status": "bad"})
    # The text is style but not the flanking whitespace.
    expected = "foo," + "  " + capres("smul", "bad") + "  \n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_align():
    out = Tabular(["name"],
                  style={"name": {"align": "right", "width": 10}})
    out({"name": "foo"})

    assert_eq_repr(out.stdout, "       foo\n")


def test_tabular_rewrite():
    out = Tabular(["name", "status"],
                  style={"name": {"width": 3}, "status": {"width": 9}})
    data = [{"name": "foo", "status": "unknown"},
            {"name": "bar", "status": "installed"}]
    for row in data:
        out(row)

    out({"name": "foo", "status": "installed"})

    expected = unicode_cap("cuu1") * 2 + unicode_cap("el") + "foo installed"
    assert_eq_repr(out.stdout.strip().splitlines()[-1],
                   expected)


def test_tabular_rewrite_with_header():
    out = Tabular(["name", "status"],
                  style={"header_": {},
                         "status": {"width": 9}})
    data = [{"name": "foo", "status": "unknown"},
            {"name": "bar", "status": "unknown"}]
    for row in data:
        out(row)
    out({"name": "bar", "status": "installed"})

    expected = unicode_cap("cuu1") * 1 + unicode_cap("el") + "bar  installed"
    assert_eq_repr(out.stdout.strip().splitlines()[-1],
                   expected)


def test_tabular_rewrite_multi_id():
    out = Tabular(["name", "type", "status"],
                  style={"name": {"width": 3},
                         "type": {"width": 1},
                         "status": {"width": 9}})
    out.ids = ["name", "type"]

    data = [{"name": "foo", "type": "0", "status": "unknown"},
            {"name": "foo", "type": "1", "status": "unknown"},
            {"name": "bar", "type": "2", "status": "installed"}]
    for row in data:
        out(row)

    out({"name": "foo", "type": "0", "status": "installed"})

    expected = unicode_cap("cuu1") * 3 + unicode_cap("el") + "foo 0 installed"
    assert_eq_repr(out.stdout.strip().splitlines()[-1],
                   expected)


def test_tabular_rewrite_multi_value():
    out = Tabular(["name", "type", "status"],
                  style={"name": {"width": 3},
                         "type": {"width": 1},
                         "status": {"width": 9}})
    data = [{"name": "foo", "type": "0", "status": "unknown"},
            {"name": "bar", "type": "1", "status": "unknown"}]
    for row in data:
        out(row)

    out({"name": "foo", "status": "installed", "type": "3"})

    expected = unicode_cap("cuu1") * 2 + unicode_cap("el") + "foo 3 installed"
    assert_eq_repr(out.stdout.strip().splitlines()[-1],
                   expected)


def test_tabular_rewrite_auto_width():
    out = Tabular(["name", "status"],
                  style={"name": {"width": 3}, "status": {"width": "auto"}})
    data = [{"name": "foo", "status": "unknown"},
            {"name": "bar", "status": "unknown"},
            {"name": "baz", "status": "unknown"}]
    for row in data:
        out(row)

    out({"name": "bar", "status": "installed"})

    lines = out.stdout.splitlines()
    assert_contains_nc(lines, "foo unknown  ", "baz unknown  ")


def test_tabular_non_hashable_id_error():
    out = Tabular()
    out.ids = ["status"]
    with pytest.raises(ContentError):
        out({"name": "foo", "status": [0, 1]})


def test_tabular_write_lookup_color():
    out = Tabular(style={"name": {"width": 3},
                         "status": {"color": {"lookup": {"BAD": "red"}},
                                    "width": 6}})
    out(OrderedDict([("name", "foo"),
                     ("status", "OK")]))
    out(OrderedDict([("name", "bar"),
                     ("status", "BAD")]))

    expected = "foo " + "OK    \n" + \
               "bar " + capres("red", "BAD") + "   \n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_lookup_bold():
    out = Tabular(style={"name": {"width": 3},
                         "status": {"bold": {"lookup": {"BAD": True}},
                                    "width": 6}})
    out(OrderedDict([("name", "foo"),
                     ("status", "OK")]))
    out(OrderedDict([("name", "bar"),
                     ("status", "BAD")]))

    expected = "foo " + "OK    \n" + \
               "bar " + capres("bold", "BAD") + "   \n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_lookup_bold_false():
    out = Tabular(style={"name": {"width": 3},
                         "status": {"bold": {"lookup": {"BAD": False}},
                                    "width": 6}})
    out(OrderedDict([("name", "foo"),
                     ("status", "OK")]))
    out(OrderedDict([("name", "bar"),
                     ("status", "BAD")]))

    expected = ("foo OK    \n"
                "bar BAD   \n")
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_lookup_non_hashable():
    out = Tabular(style={"status": {"color": {"lookup": {"BAD": "red"}}}})
    out(OrderedDict([("name", "foo"),
                     ("status", [0, 1])]))
    expected = "foo [0, 1]\n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_intervals_color():
    out = Tabular(style={"name": {"width": 3},
                         "percent": {"color": {"interval":
                                               [[0, 50, "red"],
                                                [50, 80, "yellow"],
                                                [80, 100, "green"]]},
                                     "width": 7}})
    out(OrderedDict([("name", "foo"),
                     ("percent", 88)]))
    out(OrderedDict([("name", "bar"),
                     ("percent", 33)]))

    expected = "foo " + capres("green", "88") + "     \n" + \
               "bar " + capres("red", "33") + "     \n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_intervals_color_open_ended():
    out = Tabular(style={"name": {"width": 3},
                         "percent": {"color": {"interval":
                                               [[None, 50, "red"],
                                                [80, None, "green"]]},
                                     "width": 7}})
    out(OrderedDict([("name", "foo"),
                     ("percent", 88)]))
    out(OrderedDict([("name", "bar"),
                     ("percent", 33)]))

    expected = "foo " + capres("green", "88") + "     \n" + \
               "bar " + capres("red", "33") + "     \n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_intervals_color_outside_intervals():
    out = Tabular(style={"name": {"width": 3},
                         "percent": {"color": {"interval":
                                               [[0, 50, "red"]]},
                                     "width": 7}})
    out(OrderedDict([("name", "foo"),
                     ("percent", 88)]))
    out(OrderedDict([("name", "bar"),
                     ("percent", 33)]))

    expected = "foo 88     \n" + \
               "bar " + capres("red", "33") + "     \n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_intervals_bold():
    out = Tabular(style={"name": {"width": 3},
                         "percent": {"bold": {"interval":
                                              [[30, 50, False],
                                               [50, 80, True]]},
                                     "width": 2}})
    out(OrderedDict([("name", "foo"),
                     ("percent", 78)]))
    out(OrderedDict([("name", "bar"),
                     ("percent", 33)]))

    expected = "foo " + capres("bold", "78") + "\n" + \
               "bar 33\n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_intervals_missing():
    out = Tabular(style={"name": {"width": 3},
                         "percent": {"bold": {"interval":
                                              [[30, 50, False],
                                               [50, 80, True]]},
                                     "width": 2}})
    out(OrderedDict([("name", "foo"),
                     ("percent", 78)]))
    # Interval lookup function can handle a missing value.
    out(OrderedDict([("name", "bar")]))

    expected = "foo " + capres("bold", "78") + "\n" + "bar   \n"
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_transform():
    out = Tabular(style={"val": {"transform": lambda x: x[::-1]}})
    out(OrderedDict([("name", "foo"),
                     ("val", "330")]))
    out(OrderedDict([("name", "bar"),
                     ("val", "780")]))

    expected = ("foo 033\n"
                "bar 087\n")
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_transform_with_header():
    out = Tabular(style={"header_": {},
                         "name": {"width": 4},
                         "val": {"transform": lambda x: x[::-1]}})
    out(OrderedDict([("name", "foo"),
                     ("val", "330")]))
    out(OrderedDict([("name", "bar"),
                     ("val", "780")]))

    expected = ("name val\n"
                "foo  033\n"
                "bar  087\n")
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_transform_autowidth():
    out = Tabular(style={"val": {"transform": lambda x: x * 2}})
    out(OrderedDict([("name", "foo"),
                     ("val", "330")]))
    out(OrderedDict([("name", "bar"),
                     ("val", "7800")]))

    lines = out.stdout.splitlines()
    assert_contains_nc(lines, "foo 330330  ", "bar 78007800")


def test_tabular_write_transform_on_header():
    out = Tabular(style={"header_": {"transform": lambda x: x.upper()},
                         "name": {"width": 4},
                         "val": {"width": 3}})
    out(OrderedDict([("name", "foo"),
                     ("val", "330")]))
    out(OrderedDict([("name", "bar"),
                     ("val", "780")]))

    expected = ("NAME VAL\n"
                "foo  330\n"
                "bar  780\n")
    assert_eq_repr(out.stdout, expected)


def test_tabular_write_transform_func_error():
    def dontlikeints(x):
        return x[::-1]

    out = Tabular(style={"name": {"width": 4},
                         "val": {"transform": dontlikeints}})
    # The transform function receives the data as given, so it fails trying to
    # index an integer.
    try:
        out(OrderedDict([("name", "foo"), ("val", 330)]))
    except:
        exc_type, value, tb = sys.exc_info()
        try:
            assert isinstance(value, StyleFunctionError)
            tblines = "\n".join(
                traceback.format_exception(exc_type, value, tb))
            assert "in dontlikeints" in tblines
        finally:
            del tb


def test_tabular_write_width_truncate_long():
    out = Tabular(style={"name": {"width": 8},
                         "status": {"width": 3}})
    out(OrderedDict([("name", "abcdefghijklmnop"),
                     ("status", "OK")]))
    out(OrderedDict([("name", "bar"),
                     ("status", "BAD")]))

    expected = ("abcde... OK \n"
                "bar      BAD\n")
    assert out.stdout == expected


def test_tabular_write_autowidth():
    out = Tabular(style={"name": {"width": "auto"},
                         "status": {"width": "auto"},
                         "path": {"width": 6}})
    out(OrderedDict([("name", "fooab"),
                     ("status", "OK"),
                     ("path", "/tmp/a")]))
    out(OrderedDict([("name", "bar"),
                     ("status", "BAD"),
                     ("path", "/tmp/b")]))

    lines = out.stdout.splitlines()
    assert_contains_nc(lines, "bar   BAD /tmp/b", "fooab OK  /tmp/a")


def test_tabular_write_autowidth_with_header():
    out = Tabular(style={"header_": {},
                         "name": {"width": "auto"},
                         "status": {"width": "auto"}})
    out(OrderedDict([("name", "foobar"),
                     ("status", "OK")]))
    out(OrderedDict([("name", "baz"),
                     ("status", "OK")]))

    lines = out.stdout.splitlines()
    assert_contains_nc(lines, "name   status")


def test_tabular_write_autowidth_min():
    out = Tabular(style={"name": {"width": "auto"},
                         "status": {"width": {"auto": True, "min": 5}},
                         "path": {"width": 6}})
    out(OrderedDict([("name", "fooab"),
                     ("status", "OK"),
                     ("path", "/tmp/a")]))
    out(OrderedDict([("name", "bar"),
                     ("status", "BAD"),
                     ("path", "/tmp/b")]))

    lines = out.stdout.splitlines()
    assert_contains_nc(lines, "bar   BAD   /tmp/b", "fooab OK    /tmp/a")


@pytest.mark.parametrize("marker", [True, False, "…"],
                         ids=["marker=True", "marker=False", "marker=…"])
def test_tabular_write_autowidth_min_max(marker):
    out = Tabular(style={"name": {"width": 3},
                         "status": {"width":
                                    {"auto": True, "min": 2, "max": 7}},
                         "path": {"width": {"auto": True, "max": 5,
                                            "marker": marker}}})
    out(OrderedDict([("name", "foo"),
                     ("status", "U"),
                     ("path", "/tmp/a")]))

    if marker is True:
        assert out.stdout == "foo U  /t...\n"
    elif marker:
        assert out.stdout == "foo U  /tmp…\n"
    else:
        assert out.stdout == "foo U  /tmp/\n"

    out(OrderedDict([("name", "bar"),
                     ("status", "BAD!!!!!!!!!!!"),
                     ("path", "/tmp/b")]))

    lines = out.stdout.splitlines()
    if marker is True:
        assert_contains_nc(lines,
                           "foo U       /t...",
                           "bar BAD!... /t...")
    elif marker:
        assert_contains_nc(lines,
                           "foo U       /tmp…",
                           "bar BAD!... /tmp…")
    else:
        assert_contains_nc(lines,
                           "foo U       /tmp/",
                           "bar BAD!... /tmp/")


def test_tabular_write_autowidth_min_max_with_header():
    out = Tabular(style={"header_": {},
                         "name": {"width": 4},
                         "status": {"width":
                                    {"auto": True, "min": 2, "max": 8}}})
    out(OrderedDict([("name", "foo"),
                     ("status", "U")]))

    lines0 = out.stdout.splitlines()
    assert_contains_nc(lines0, "name status", "foo  U     ")

    out(OrderedDict([("name", "bar"),
                     ("status", "BAD!!!!!!!!!!!")]))

    lines1 = out.stdout.splitlines()
    assert_contains_nc(lines1, "bar  BAD!!...")


def test_tabular_write_autowidth_different_data_types_same_output():
    out_dict = Tabular(["name", "status"],
                       style={"header_": {},
                              "name": {"width": 4},
                              "status": {"width":
                                         {"auto": True, "min": 2, "max": 8}}})
    out_dict({"name": "foo", "status": "U"})
    out_dict({"name": "bar", "status": "BAD!!!!!!!!!!!"})

    out_list = Tabular(["name", "status"],
                       style={"header_": {},
                              "name": {"width": 4},
                              "status": {"width":
                                         {"auto": True, "min": 2, "max": 8}}})
    out_list(["foo", "U"])
    out_list(["bar", "BAD!!!!!!!!!!!"])

    assert out_dict.stdout == out_list.stdout


def test_tabular_write_autowidth_auto_false_exception():
    out = Tabular(style={"header_": {},
                         "name": {"width": 4},
                         "status": {"width": {"auto": False}}})
    with pytest.raises(ValueError):
        out(OrderedDict([("name", "foo"),
                         ("status", "U")]))


class Delayed(object):
    """Helper for producing a delayed callable.
    """

    def __init__(self, value):
        self.value = value
        self.now = False

    def run(self):
        """Return `value` once `now` is true.
        """
        while True:
            if self.now:
                return self.value


@pytest.mark.timeout(10)
def test_tabular_write_callable_values():
    delay0 = Delayed("done")
    delay1 = Delayed("over")

    with Tabular(["name", "status"]) as out:
        out({"name": "foo", "status": ("thinking", delay0.run)})
        out({"name": "bar", "status": "ok"})
        # A single callable can be passed rather than (initial_value, fn).
        out({"name": "baz", "status": delay1.run})

        expected = ("foo thinking\n"
                    "bar ok      \n"
                    "baz         \n")
        assert_eq_repr(out.stdout, expected)

        delay0.now = True
        delay1.now = True
    lines = out.stdout.splitlines()
    assert_contains_nc(lines, "foo done    ", "baz over    ")


@pytest.mark.timeout(10)
def test_tabular_write_callable_transform_nothing():
    delay0 = Delayed(3)

    out = Tabular(["name", "status"],
                  style={"status": {"transform": lambda n: n + 2}})
    with out:
        # The unspecified initial value is set to Nothing().  The transform
        # function above, which is designed to take a number, won't be called
        # with it.
        out({"name": "foo", "status": delay0.run})
        assert_eq_repr(out.stdout, "foo \n")
        delay0.now = True
    lines = out.stdout.splitlines()
    assert_contains_nc(lines, "foo 5")


@pytest.mark.timeout(10)
def test_tabular_write_callable_values_multi_return():
    delay = Delayed({"status": "done", "path": "/tmp/a"})

    out = Tabular(["name", "status", "path"])
    with out:
        out({"name": "foo", ("status", "path"): ("...", delay.run)})
        out({"name": "bar", "status": "ok", "path": "na"})

        expected = ("foo ... ...\n"
                    "bar ok  na \n")
        assert_eq_repr(out.stdout, expected)

        delay.now = True
    lines = out.stdout.splitlines()
    assert_contains_nc(lines, "foo done /tmp/a")


@pytest.mark.timeout(10)
@pytest.mark.parametrize("result",
                         [{"status": "done", "path": "/tmp/a"},
                          ("done", "/tmp/a")],
                         ids=["result=tuple", "result=dict"])
def test_tabular_write_callable_values_multicol_key_infer_column(result):
    delay = Delayed(result)
    out = Tabular()
    with out:
        out(OrderedDict([("name", "foo"),
                         (("status", "path"), ("...", delay.run))]))
        out(OrderedDict([("name", "bar"),
                         ("status", "ok"),
                         ("path", "na")]))

        expected = ("foo ... ...\n"
                    "bar ok  na \n")
        assert_eq_repr(out.stdout, expected)

        delay.now = True
    lines = out.stdout.splitlines()
    assert_contains_nc(lines, "foo done /tmp/a")


def delayed_gen_func(*values):
    if not values:
        values = ["update", "finished"]

    def fn():
        for val in values:
            time.sleep(0.05)
            yield val
    return fn


@pytest.mark.timeout(10)
@pytest.mark.parametrize("gen_source",
                         [delayed_gen_func(),
                          delayed_gen_func()()],
                         ids=["gen_func", "generator"])
def test_tabular_write_generator_function_values(gen_source):
    with Tabular(["name", "status"]) as out:
        out({"name": "foo", "status": ("waiting", gen_source)})
        out({"name": "bar", "status": "ok"})

        expected = ("foo waiting\n"
                    "bar ok     \n")
        assert_eq_repr(out.stdout, expected)
    lines = out.stdout.splitlines()
    assert_contains_nc(lines,
                       "foo update ",
                       "foo finished",
                       "bar ok      ")


@pytest.mark.timeout(10)
def test_tabular_write_generator_values_multireturn():
    gen = delayed_gen_func({"status": "working"},  # for one of two columns
                           {"path": "/tmp/a"},  # for the other of two columns
                           {"path": "/tmp/b",  # for both columns
                            "status": "done"})
    out = Tabular()
    with out:
        out(OrderedDict([("name", "foo"),
                         (("status", "path"), ("...", gen))]))
        out(OrderedDict([("name", "bar"),
                         ("status", "ok"),
                         ("path", "na")]))

        expected = ("foo ... ...\n"
                    "bar ok  na \n")
        assert_eq_repr(out.stdout, expected)
    lines = out.stdout.splitlines()
    assert_contains_nc(lines,
                       "foo working ...",
                       "foo working /tmp/a",
                       "foo done    /tmp/b")


def test_tabular_write_wait_noop_if_nothreads():
    with Tabular(["name", "status"]) as out:
        out({"name": "foo", "status": "done"})
        out({"name": "bar", "status": "ok"})

        expected = ("foo done\n"
                    "bar ok  \n")
        assert_eq_repr(out.stdout, expected)


@pytest.mark.timeout(10)
@pytest.mark.parametrize("form", ["dict", "list", "attrs"])
def test_tabular_write_delayed(form):
    data = OrderedDict([("name", "foo"),
                        ("paired0", 1),
                        ("paired1", 2),
                        ("solo", 3)])

    if form == "dict":
        row = data
    elif form == "list":
        row = list(data.values())
    elif form == "attrs":
        row = AttrData(**data)

    out = Tabular(list(data.keys()),
                  style={"paired0": {"delayed": "pair"},
                         "paired1": {"delayed": "pair"},
                         "solo": {"delayed": True}})
    with out:
        out(row)
    lines = out.stdout.splitlines()
    assert lines[0] == "foo   "

    # Either paired0/paired1 came in first or solo came in first, but
    # paired0/paired1 should arrive together.
    firstin = [ln for ln in lines
               if eq_repr_noclear(ln, "foo 1 2 ")
               or eq_repr_noclear(ln, "foo   3")]
    assert len(firstin) == 1

    assert eq_repr_noclear(lines[-1], "foo 1 2 3")


def test_tabular_summary():

    def nbad(xs):
        return "{:d} failed".format(sum("BAD" == x for x in xs))

    out = Tabular(style={"header_": {},
                         "status": {"aggregate": nbad},
                         "num": {"aggregate": sum}})

    out(OrderedDict([("name", "foo"),
                     ("status", "BAD"),
                     ("num", 2)]))
    out(OrderedDict([("name", "bar"),
                     ("status", "BAD"),
                     ("num", 3)]))
    out(OrderedDict([("name", "baz"),
                     ("status", "BAD"),
                     ("num", 4)]))

    # Update "foo".
    out(OrderedDict([("name", "foo"),
                     ("status", "OK"),
                     ("num", 10)]))

    lines = out.stdout.splitlines()
    assert_contains_nc(lines,
                       "     1 failed 2  ",
                       "     2 failed 5  ",
                       "     3 failed 9  ",
                       "     2 failed 17 ")


def test_tabular_shrinking_summary():

    def counts(values):
        cnt = Counter(values)
        return ["{}: {:d}".format(k, cnt[k]) for k in sorted(cnt.keys())]

    out = Tabular(["name", "status"],
                  style={"status": {"aggregate": counts}})

    out({"name": "foo", "status": "unknown"})
    out({"name": "bar", "status": "ok"})
    # Remove the only occurrence of "unknown".
    out({"name": "foo", "status": "ok"})

    lines = out.stdout.splitlines()
    # Two summary lines shrank to one, so we expect a two move-ups and a clear.
    expected = unicode_cap("cuu1") * 2 + unicode_cap("ed")
    assert len([ln for ln in lines if ln.startswith(expected)]) == 1
