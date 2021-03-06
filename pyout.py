"""Terminal styling for tabular data.

TODO: Come up with a better one-line description.  Should emphasize
style declaration.
"""

__version__ = "0.1.0"
__all__ = ["Tabular"]

from contextlib import contextmanager
from blessings import Terminal


def _adopt(style, new_style):
    if new_style is None:
        return style
    return {key: dict(style[key], **new_style.get(key, {})) for key in style}


class Tabular(object):
    """Interface for writing and updating styled terminal output.

    Parameters
    ----------
    data : iterable
        Each element should be a dictionary where keys are the column
        names and values are the data to write.
    columns : list of str
        Column names
    id_column : int, optional
        Column that contains unique labels that can be used to
        reference rows.
    style : dict, optional
        Each top-level key should be a column name and the value
        should be a style dict that overrides the `default_style`
        class attribute.
    stream : file object, optional
        Defaults to standard output.

    Attributes
    ----------
    term : blessings.Terminal instance
    """

    # TODO: Support things like auto-width, value-based coloring, etc.
    default_style = {"align": "<",
                     "width": 10,
                     "attrs": []}

    def __init__(self, data, columns, id_column=0, style=None, stream=None):
        self.term = Terminal(stream=stream)

        ## FIXME: Don't coerce data into a list -- store on the fly.
        self._rows = list(data)
        ## TODO: Allow columns to be infered from data or style.
        self._columns = columns
        self.id = columns[id_column]

        self._style = _adopt({c: self.default_style for c in columns},
                             style)
        self._format = self._build_format(self._style)

    def _build_format(self, style):
        fields = []
        for column in self._columns:
            cstyle = style[column]
            field = "{{{}:{align}{width}}}".format(column, **cstyle)
            for attr in cstyle["attrs"]:
                 field = getattr(self.term, attr) + field + self.term.normal
            fields.append(field)
        return " ".join(fields) + "\n"

    def _writerow(self, row, style=None):
        if style is None:
            fmt = self._format
        else:
            fmt = self._build_format(_adopt(self._style, style))
        self.term.stream.write(fmt.format(**{i: row[i] for i in self._columns}))

    def write(self):
        """Write styled data to the terminal.
        """
        for row in self._rows:
            self._writerow(row)
        self.term.stream.flush()

    def _repaint(self):
        ## TODO: I don't think this is a good approach.  Destroys any
        ## scroll back.
        self.term.stream.write(self.term.clear)
        self.term.stream.write("  ".join(self._columns) + "\n")
        for row in self._rows:
            self._writerow(row)
        self.term.stream.flush()

    @contextmanager
    def _moveback(self, n):
        self.term.stream.write(self.term.move_up * n + self.term.clear_eol)
        try:
            yield
        finally:
            self.term.stream.write(self.term.move_down * (n - 1))
            self.term.stream.flush()

    ## FIXME: This will break with stderr and when the output scrolls.
    ## Maybe we could check term height and repaint?
    def rewrite(self, label, column, new_value, style=None):
        """Rewrite a row.

        Parameters
        ----------
        label : str
            A label that identifies the row.  It should be a unique
            value in the ID column.
        column : str
            The name of the column whose value should be updated to
            `new_value`.
        new_value : str
        style : dict
            A new style dictionary to use for the new row.  All
            unspecified style elements are taken from the instance's
            `style`.
        """
        nback = None
        for rev_idx, row in enumerate(reversed(self._rows), 1):
            if row[self.id] == label:
                nback = rev_idx
                break
        if nback is None:
            raise ValueError("Could not find row with '{}' id")

        idx = len(self._rows) - nback
        self._rows[idx][column] = new_value

        with self._moveback(nback):
            self._writerow(self._rows[idx], style)
