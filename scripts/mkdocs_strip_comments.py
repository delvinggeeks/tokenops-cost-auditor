"""R-DOCS-PUBLIC (founder 2026-07-22): the `<!-- src: ... -->` citation
comments are an internal discipline — they name internal docs, gates and
rulings, and belong in the repo, not in served HTML source or the search
index. Strip every HTML comment from the public build."""

from __future__ import annotations

import re

_COMMENT = re.compile(r"<!--.*?-->", re.S)


def on_page_markdown(markdown: str, **kwargs: object) -> str:
    return _COMMENT.sub("", markdown)
