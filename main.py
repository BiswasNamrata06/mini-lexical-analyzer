"""
main.py - starting point of the Mini Lexical Analyzer Generator.

    python main.py                         open the graphical interface (Tkinter)
    python main.py samples/sample_program.c   command-line mode for one file
    python main.py --cli                   command-line mode on the default sample

Options (command-line mode):
    --spec FILE      use a different token specification (JSON)
    --show-hidden    also list whitespace and comments
    --show-rules     print the generated scanner rules first
    --save FILE      save tokens to FILE (.csv or .txt)
"""

import argparse
import os
import sys

import lexer


def build_argument_parser():
    parser = argparse.ArgumentParser(description="Mini Lexical Analyzer Generator")
    parser.add_argument("source", nargs="?", help="source file (.c or .txt) to analyze")
    parser.add_argument("--cli", action="store_true", help="force command-line mode")
    parser.add_argument("--spec", default=lexer.DEFAULT_SPEC_PATH, help="token specification JSON file")
    parser.add_argument("--show-hidden", action="store_true", help="also show whitespace and comments")
    parser.add_argument("--show-rules", action="store_true", help="print the generated scanner rules")
    parser.add_argument("--save", metavar="FILE", help="save tokens to a .csv or .txt file")
    return parser


def run_command_line(arguments):
    """Generate the scanner, analyze one source file, print the results."""
    # Stage 1: generate the scanner from the specification.
    try:
        spec_data = lexer.load_token_specifications(arguments.spec)
        scanner = lexer.generate_scanner(spec_data)
    except lexer.SpecError as error:
        print("Specification error: %s" % error)
        return 2

    if arguments.show_rules or scanner["problems"]:
        print(lexer.describe_scanner(scanner))
        print()

    # Read the source code (default: the bundled sample).
    if arguments.source:
        try:
            source = lexer.read_text_file(arguments.source)
        except OSError as error:
            print("Cannot read source file: %s" % error)
            return 2
    elif os.path.exists(lexer.DEFAULT_SAMPLE_PATH):
        source = lexer.read_text_file(lexer.DEFAULT_SAMPLE_PATH)
    else:
        source = lexer.FALLBACK_SAMPLE

    # Stage 2: scan the source with the generated scanner.
    tokens, errors = lexer.analyze_source_code(source, scanner, arguments.show_hidden)

    print(lexer.display_tokens(tokens))
    print()
    print(lexer.format_summary(tokens, errors))
    print(lexer.format_errors(errors))

    if arguments.save:
        try:
            lexer.save_tokens(tokens, errors, arguments.save)
            print("Tokens saved to %s" % arguments.save)
        except OSError as error:
            print("Could not save tokens: %s" % error)
            return 2
    return 0


def main(argv=None):
    arguments = build_argument_parser().parse_args(argv)

    if arguments.cli or arguments.source:
        return run_command_line(arguments)

    try:
        import gui                       # needs Tkinter
    except ImportError:
        print("Tkinter is not available on this Python, so the GUI cannot start.")
        print("Running command-line mode on the default sample instead.\n")
        return run_command_line(arguments)

    gui.run_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
