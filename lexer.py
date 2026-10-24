"""
lexer.py - the heart of the Mini Lexical Analyzer Generator.

Two separate stages live in this file (this is what makes it a *generator*):

  STAGE 1 - GENERATION (runs once per set of rules)
      token_specifications.json  --->  generate_scanner()  --->  scanner (compiled rules)

  STAGE 2 - SCANNING (runs once per source program)
      source code + scanner      --->  analyze_source_code()  --->  tokens + errors

The scanning code never mentions "int", "+", ";" and so on. Everything it knows
about the language comes from the compiled rules it receives. Change the JSON
file and the same scanning code recognises a different set of tokens.

Only the Python standard library is used.
"""

import csv
import json
import os
import re

# ---------------------------------------------------------------------------
# Paths used by the program (relative to this file, so it runs from any folder)
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SPEC_PATH = os.path.join(BASE_DIR, "token_specifications.json")
DEFAULT_SAMPLE_PATH = os.path.join(BASE_DIR, "samples", "sample_program.c")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# Used only if samples/sample_program.c has been deleted.
FALLBACK_SAMPLE = """int main() {
    int total = 25;
    float rate = 2.5;

    if (total >= 10) {
        total = total + 5;
    }

    return 0;
}
"""


class SpecError(Exception):
    """Raised when the token specification is unusable as a whole."""


# ===========================================================================
# STAGE 1 - LOADING THE SPECIFICATION AND GENERATING THE SCANNER
# ===========================================================================

def read_text_file(path):
    """Read a text file as UTF-8 (bad bytes are replaced, never crash)."""
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as file:
        return file.read()


def load_token_specifications(path=DEFAULT_SPEC_PATH):
    """Read the JSON specification file and return it as a Python dictionary."""
    try:
        text = read_text_file(path)
    except OSError as error:
        raise SpecError("Cannot read specification file '%s': %s" % (path, error))
    return parse_specification_text(text)


def parse_specification_text(text):
    """Turn JSON text into a dictionary (used by the file loader and the GUI)."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise SpecError("Specification is not valid JSON: %s (line %d, column %d)"
                        % (error.msg, error.lineno, error.colno))


def compile_rule(entry, position, problems):
    """
    Validate ONE token rule and compile its regular expression.

    Returns a rule dictionary, or None when the rule is unusable. Reasons for
    rejection are appended to `problems`, so one bad rule never stops the
    others from working.
    """
    label = "Rule #%d" % position

    if not isinstance(entry, dict):
        problems.append("%s ignored: it must be a JSON object." % label)
        return None

    name = entry.get("name")
    pattern = entry.get("pattern")

    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        problems.append("%s ignored: 'name' must be a word such as KEYWORD or NUMBER." % label)
        return None
    label = "Rule #%d (%s)" % (position, name)

    if not isinstance(pattern, str) or pattern == "":
        problems.append("%s ignored: 'pattern' must be a non-empty string." % label)
        return None

    try:
        regex = re.compile(pattern)          # the real "compilation" step
    except re.error as error:
        problems.append("%s ignored: malformed regular expression (%s)." % (label, error))
        return None

    # A rule that can match nothing at all would never make progress.
    if regex.match("") is not None:
        problems.append("%s ignored: the pattern can match an empty string." % label)
        return None

    return {
        "name": name,
        "pattern": pattern,
        "regex": regex,
        "hidden": entry.get("hidden") is True,
        "keyword_check": entry.get("keyword_check") is True,
        "error_message": entry["error"] if isinstance(entry.get("error"), str) else "",
    }


def generate_scanner(spec_data):
    """
    THE GENERATOR.  Reads the specification and builds a reusable scanner.

    The scanner is just a dictionary:
        "rules"    : ordered list of compiled rules
        "keywords" : set of reserved words
        "problems" : warnings about rules that had to be skipped
    """
    problems = []

    if not isinstance(spec_data, dict):
        raise SpecError("The specification must be a JSON object with 'keywords' and 'tokens'.")

    keywords = spec_data.get("keywords", [])
    if not isinstance(keywords, list) or not all(isinstance(k, str) and k for k in keywords):
        problems.append("'keywords' must be a list of non-empty strings; keyword list ignored.")
        keywords = []

    token_entries = spec_data.get("tokens")
    if not isinstance(token_entries, list):
        raise SpecError("'tokens' must be a list of token rules.")

    rules = []
    for position, entry in enumerate(token_entries, start=1):
        rule = compile_rule(entry, position, problems)
        if rule is not None:
            rules.append(rule)

    if not rules:
        raise SpecError("No valid token rules were found, so no scanner can be generated.")

    return {"rules": rules, "keywords": set(keywords), "problems": problems}


def describe_scanner(scanner):
    """Return a printable list of the generated rules (handy for demonstrations)."""
    lines = ["Generated scanner: %d rules, %d keywords" % (len(scanner["rules"]), len(scanner["keywords"]))]
    for number, rule in enumerate(scanner["rules"], start=1):
        notes = []
        if rule["hidden"]:
            notes.append("hidden")
        if rule["keyword_check"]:
            notes.append("keyword check")
        if rule["error_message"]:
            notes.append("reports error")
        suffix = "  [" + ", ".join(notes) + "]" if notes else ""
        lines.append("%2d. %-26s %s%s" % (number, rule["name"], rule["pattern"], suffix))
    for problem in scanner["problems"]:
        lines.append("WARNING: " + problem)
    return "\n".join(lines)


# ===========================================================================
# STAGE 2 - SCANNING SOURCE CODE WITH THE GENERATED SCANNER
# ===========================================================================

def classify_keyword(lexeme, keywords, default_type="IDENTIFIER"):
    """
    Decide whether a word that looks like an identifier is really a keyword.

    The identifier rule always matches the WHOLE word first (maximal munch), so
    "integer" arrives here as one lexeme and is correctly NOT the keyword "int".
    """
    if lexeme in keywords:
        return "KEYWORD"
    return default_type


def find_longest_match(source, position, rules):
    """
    Maximal munch: try every rule at `position` and keep the LONGEST match.
    If two rules match the same length, the rule listed first wins.
    Zero-length matches are ignored, so the scanner can never get stuck.

    Returns (rule, end_position) or (None, position) when nothing matches.
    """
    best_rule = None
    best_end = position
    for rule in rules:
        match = rule["regex"].match(source, position)
        if match is not None and match.end() > best_end:   # strictly longer only
            best_rule = rule
            best_end = match.end()
    return best_rule, best_end


def advance_position(lexeme, line, column):
    """Return the (line, column) that follows `lexeme`; handles multi-line lexemes."""
    newline_count = lexeme.count("\n")
    if newline_count == 0:
        return line, column + len(lexeme)
    last_newline = lexeme.rfind("\n")
    return line + newline_count, len(lexeme) - last_newline   # characters after it, plus 1


def handle_lexical_errors(line, column, lexeme, reason):
    """Build one lexical-error record (line and column are 1-based)."""
    return {"line": line, "column": column, "lexeme": lexeme, "message": reason}


def analyze_source_code(source, scanner, show_hidden=False):
    """
    Scan `source` using the generated `scanner`.

    Returns (tokens, errors). Each token is a dictionary with the keys
    "type", "lexeme", "line", "column".  Scanning always continues after an
    error, and always moves forward by at least one character.
    """
    tokens = []
    errors = []
    position = 0          # index into the source string
    line = 1              # current line (starts at 1)
    column = 1            # current column (starts at 1)

    while position < len(source):
        rule, end = find_longest_match(source, position, scanner["rules"])

        if rule is None:
            # No rule matches: report ONE bad character, skip it, carry on.
            lexeme = source[position]
            end = position + 1
            errors.append(handle_lexical_errors(
                line, column, lexeme, "Invalid character %r" % lexeme))

        else:
            lexeme = source[position:end]

            if rule["error_message"]:
                # A rule written specifically to catch a malformed token,
                # e.g. an unterminated string or comment.
                reason = "%s: %s" % (rule["error_message"], printable_lexeme(lexeme, 30))
                errors.append(handle_lexical_errors(line, column, lexeme, reason))

            elif not rule["hidden"] or show_hidden:
                token_type = rule["name"]
                if rule["keyword_check"]:
                    token_type = classify_keyword(lexeme, scanner["keywords"], token_type)
                tokens.append({"type": token_type, "lexeme": lexeme,
                               "line": line, "column": column})

        line, column = advance_position(lexeme, line, column)
        position = end

    return tokens, errors


# ===========================================================================
# OUTPUT HELPERS
# ===========================================================================

def printable_lexeme(lexeme, max_length=40):
    """Make a lexeme safe to show in one table cell (escape newlines, shorten)."""
    text = lexeme.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    if len(text) > max_length:
        text = text[:max_length - 3] + "..."
    return text


def display_tokens(tokens):
    """Return the token table as text:  Token Type | Lexeme | Line | Column."""
    headers = ("Token Type", "Lexeme", "Line", "Column")
    rows = [(t["type"], printable_lexeme(t["lexeme"]), str(t["line"]), str(t["column"]))
            for t in tokens]
    widths = [max([len(headers[i])] + [len(row[i]) for row in rows]) for i in range(4)]

    def format_row(cells):
        return " | ".join(cells[i].ljust(widths[i]) for i in range(4)).rstrip()

    lines = [format_row(headers), "-+-".join("-" * w for w in widths)]
    lines.extend(format_row(row) for row in rows)
    return "\n".join(lines)


def format_errors(errors):
    """Return the lexical errors as text, one per line."""
    if not errors:
        return "No lexical errors."
    return "\n".join("Lexical error at line %d, column %d: %s"
                     % (e["line"], e["column"], e["message"]) for e in errors)


def format_summary(tokens, errors):
    """Return the one-line count summary."""
    return "Total tokens recognized: %d    Lexical errors: %d" % (len(tokens), len(errors))


def save_tokens(tokens, errors, path):
    """Save the tokens to a .csv file (by extension) or a plain-text table."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)

    if path.lower().endswith(".csv"):
        with open(path, "w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Token Type", "Lexeme", "Line", "Column"])
            for t in tokens:
                writer.writerow([t["type"], t["lexeme"], t["line"], t["column"]])
    else:
        with open(path, "w", encoding="utf-8") as file:
            file.write(display_tokens(tokens) + "\n\n")
            file.write(format_summary(tokens, errors) + "\n")
            file.write(format_errors(errors) + "\n")
