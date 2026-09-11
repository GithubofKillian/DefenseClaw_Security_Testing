"""Helpers de terminal et de rapport partages par les campagnes ASI0x."""

import os
import re
import sys

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")
_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _wrap(code, text):
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def green(text):
    return _wrap("32", text)


def red(text):
    return _wrap("31", text)


def yellow(text):
    return _wrap("33", text)


def dim(text):
    return _wrap("2", text)


def bold(text):
    return _wrap("1", text)


def visible_len(text):
    return len(_ANSI_RE.sub("", text))


def pad(text, width):
    return text + " " * max(0, width - visible_len(text))


def status(ok, ok_label="PASS", ko_label="FAIL"):
    return green(ok_label) if ok else red(ko_label)


def scenario_start(scenario_id, width=26):
    print(f"  {scenario_id:<{width}} ", end="", flush=True)


def tick(ok=True):
    print(green(".") if ok else red("x"), end="", flush=True)


def scenario_end(ok=True, note=None):
    suffix = f" {dim(note)}" if note else ""
    print(f" {status(ok, 'ok', 'KO')}{suffix}", flush=True)


def banner(title):
    print(bold(title))
    print(dim("-" * visible_len(title)))


def table(headers, rows):
    """Affiche un tableau aligne dans le terminal (rows: listes de str, deja colorees)."""
    widths = [visible_len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], visible_len(cell))
    line = "  ".join(pad(h, widths[i]) for i, h in enumerate(headers))
    print(bold(line))
    print(dim("  ".join("-" * w for w in widths)))
    for row in rows:
        print("  ".join(pad(cell, widths[i]) for i, cell in enumerate(row)))


def summary_line(campaign_id, ok_count, total, judge_ever=None):
    verdict = status(ok_count == total, "TOUS CONFORMES", "ECARTS DETECTES")
    line = f"{bold(campaign_id)} : {ok_count}/{total} scenarios conformes -> {verdict}"
    if judge_ever is not None:
        line += f"  |  juge LLM observe : {green('OUI') if judge_ever else yellow('NON')}"
    return line
