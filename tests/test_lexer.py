"""
Tests for the Mini Lexical Analyzer Generator.

Run from the project folder with:
    python -m unittest discover -v tests
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lexer  # noqa: E402

SCANNER = lexer.generate_scanner(lexer.load_token_specifications())


def scan(source, show_hidden=False, scanner=SCANNER):
    return lexer.analyze_source_code(source, scanner, show_hidden)


def pairs(source, **kwargs):
    """(type, lexeme) pairs only - easy to compare."""
    tokens, _ = scan(source, **kwargs)
    return [(t["type"], t["lexeme"]) for t in tokens]


def sample_path(name):
    return os.path.join(lexer.BASE_DIR, "samples", name)


class TestBasicTokens(unittest.TestCase):

    def test_01_simple_declaration(self):
        self.assertEqual(pairs("int total = 25;"), [
            ("KEYWORD", "int"), ("IDENTIFIER", "total"),
            ("ASSIGNMENT_OPERATOR", "="), ("NUMBER", "25"), ("DELIMITER", ";")])

    def test_02_keyword_prefixes(self):
        got = pairs("int integer interest intx _int int1 for format")
        self.assertEqual([t for t, _ in got],
                         ["KEYWORD", "IDENTIFIER", "IDENTIFIER", "IDENTIFIER",
                          "IDENTIFIER", "IDENTIFIER", "KEYWORD", "IDENTIFIER"])
        self.assertEqual(pairs("Int INT")[0][0], "IDENTIFIER")     # keywords are case-sensitive

    def test_03_numbers(self):
        self.assertEqual(pairs("10 3.14 .5 2e3 1.5e-2 0x1F 7."), [
            ("NUMBER", "10"), ("FLOAT_NUMBER", "3.14"), ("FLOAT_NUMBER", ".5"),
            ("FLOAT_NUMBER", "2e3"), ("FLOAT_NUMBER", "1.5e-2"), ("NUMBER", "0x1F"),
            ("FLOAT_NUMBER", "7.")])

    def test_04_multi_character_operators(self):
        expected = {
            "==": "RELATIONAL_OPERATOR", "!=": "RELATIONAL_OPERATOR",
            "<=": "RELATIONAL_OPERATOR", ">=": "RELATIONAL_OPERATOR",
            "<": "RELATIONAL_OPERATOR", ">": "RELATIONAL_OPERATOR",
            "++": "ARITHMETIC_OPERATOR", "--": "ARITHMETIC_OPERATOR",
            "&&": "LOGICAL_OPERATOR", "||": "LOGICAL_OPERATOR", "!": "LOGICAL_OPERATOR",
            "+=": "ASSIGNMENT_OPERATOR", "=": "ASSIGNMENT_OPERATOR",
        }
        for operator, token_type in expected.items():
            self.assertEqual(pairs(operator), [(token_type, operator)], operator)
        # a<=b must be three tokens, and a>=b too (maximal munch)
        self.assertEqual([l for _, l in pairs("a>=b")], ["a", ">=", "b"])
        self.assertEqual([l for _, l in pairs("x+++y")], ["x", "++", "+", "y"])

    def test_05_string_and_char_literals(self):
        self.assertEqual(pairs(r'"hi \"there\"" ' + r"'a' '\n'"), [
            ("STRING_LITERAL", r'"hi \"there\""'), ("CHAR_LITERAL", "'a'"), ("CHAR_LITERAL", r"'\n'")])
        # comment markers inside a string are just text
        self.assertEqual(pairs('"// not a comment /* nor this */"'),
                         [("STRING_LITERAL", '"// not a comment /* nor this */"')])

    def test_06_comments(self):
        source = "a // one\n/* two\nlines */ b"
        self.assertEqual([l for _, l in pairs(source)], ["a", "b"])          # hidden by default
        shown = [t for t, _ in pairs(source, show_hidden=True)]
        self.assertIn("SINGLE_LINE_COMMENT", shown)
        self.assertIn("MULTI_LINE_COMMENT", shown)

    def test_07_positions_over_several_lines(self):
        tokens, errors = scan("int a;\n  float b;\n\tx = 1;")
        self.assertEqual(errors, [])
        found = {(t["lexeme"], t["line"], t["column"]) for t in tokens}
        for item in [("int", 1, 1), ("a", 1, 5), (";", 1, 6), ("float", 2, 3),
                     ("b", 2, 9), ("x", 3, 2), ("1", 3, 6)]:
            self.assertIn(item, found)

    def test_07b_positions_after_multiline_comment_and_crlf(self):
        tokens, _ = scan("a /* x\ny */ b")
        self.assertEqual([(t["lexeme"], t["line"], t["column"]) for t in tokens],
                         [("a", 1, 1), ("b", 2, 6)])
        tokens, _ = scan("a\r\nb")
        self.assertEqual((tokens[1]["line"], tokens[1]["column"]), (2, 1))
        tokens, _ = scan('"line one\\\n')                      # string followed by newline handling
        self.assertTrue(tokens == [] or tokens[0]["line"] == 1)


class TestErrors(unittest.TestCase):

    def test_08_invalid_characters(self):
        tokens, errors = scan("int a = 5 @ 3;\n$")
        self.assertEqual([(e["line"], e["column"], e["lexeme"]) for e in errors],
                         [(1, 11, "@"), (2, 1, "$")])
        self.assertEqual(len(tokens), 6)           # int a = 5 3 ;  -> scanning continued after @
        self.assertIn("Invalid character '@'", errors[0]["message"])

    def test_09_empty_source(self):
        self.assertEqual(scan(""), ([], []))
        self.assertEqual(scan("   \n\t\n"), ([], []))
        self.assertEqual(len(scan("   \n", show_hidden=True)[0]), 1)

    def test_11_unterminated_string(self):
        tokens, errors = scan('x = "abc\nint y;')
        self.assertEqual(len(errors), 1)
        self.assertEqual((errors[0]["line"], errors[0]["column"]), (1, 5))
        self.assertIn("Unterminated string", errors[0]["message"])
        self.assertIn(("KEYWORD", "int"), [(t["type"], t["lexeme"]) for t in tokens])

    def test_11_unterminated_comment(self):
        tokens, errors = scan("int x; /* never closed\nmore text")
        self.assertEqual(len(errors), 1)
        self.assertEqual((errors[0]["line"], errors[0]["column"]), (1, 8))
        self.assertIn("Unterminated multi-line comment", errors[0]["message"])
        self.assertEqual(len(tokens), 3)           # int x ;

    def test_11_closed_comment_is_not_an_error(self):
        self.assertEqual(scan("/* ok */ x /* also ok */")[1], [])
        self.assertEqual(scan("/*/")[1][0]["message"].split(":")[0], "Unterminated multi-line comment")

    def test_11_bad_char_literals(self):
        for source in ("'ab'", "''", "'a"):
            tokens, errors = scan(source)
            self.assertEqual((len(tokens), len(errors)), (0, 1), source)


class TestSpecifications(unittest.TestCase):

    def test_10_malformed_specifications(self):
        spec = {"keywords": ["if"], "tokens": [
            {"name": "BROKEN", "pattern": "(unclosed"},        # bad regex
            {"name": "EMPTYISH", "pattern": "a*"},             # can match nothing
            {"pattern": "x"},                                   # no name
            {"name": "NOPATTERN"},                              # no pattern
            {"name": "BAD NAME", "pattern": "y"},               # invalid name
            "not an object",
            {"name": "WORD", "pattern": "[a-z]+"},              # the one valid rule
        ]}
        scanner = lexer.generate_scanner(spec)
        self.assertEqual([r["name"] for r in scanner["rules"]], ["WORD"])
        self.assertEqual(len(scanner["problems"]), 6)
        self.assertEqual([t["lexeme"] for t in scan("abc def", scanner=scanner)[0]], ["abc", "def"])

    def test_10_unusable_specifications(self):
        for bad in (None, [], "text", {"tokens": "no"}, {"keywords": []}, {"tokens": []},
                    {"tokens": [{"name": "X", "pattern": "("}]}):
            with self.assertRaises(lexer.SpecError, msg=repr(bad)):
                lexer.generate_scanner(bad)

    def test_10_bad_keyword_list_is_ignored(self):
        scanner = lexer.generate_scanner({"keywords": "if", "tokens": [{"name": "W", "pattern": "[a-z]+"}]})
        self.assertEqual(len(scanner["problems"]), 1)
        self.assertEqual(scanner["keywords"], set())

    def test_10_missing_and_invalid_json_files(self):
        with self.assertRaises(lexer.SpecError):
            lexer.load_token_specifications("no_such_file.json")
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "bad.json")
            with open(path, "w") as file:
                file.write("{ this is not json")
            with self.assertRaises(lexer.SpecError):
                lexer.load_token_specifications(path)

    def test_zero_length_matches_never_loop(self):
        # (?=a) and \b pass validation but match zero characters at run time.
        spec = {"tokens": [{"name": "LOOK", "pattern": "(?=a)"},
                           {"name": "EDGE", "pattern": r"\b"},
                           {"name": "A", "pattern": "a"}]}
        scanner = lexer.generate_scanner(spec)
        tokens, errors = scan("aaa b", scanner=scanner)
        self.assertEqual([t["lexeme"] for t in tokens], ["a", "a", "a"])
        self.assertEqual([e["lexeme"] for e in errors], [" ", "b"])

    def test_generator_really_depends_on_the_rules(self):
        """Same scanning code, different rules -> different behaviour."""
        spec_a = {"tokens": [{"name": "WORD", "pattern": "[a-z]+"}, {"name": "DIGITS", "pattern": r"\d+"}]}
        spec_b = {"tokens": [{"name": "LETTER", "pattern": "[a-z]"}, {"name": "DIGIT", "pattern": r"\d"}]}
        self.assertEqual(len(scan("ab12", scanner=lexer.generate_scanner(spec_a))[0]), 2)
        self.assertEqual(len(scan("ab12", scanner=lexer.generate_scanner(spec_b))[0]), 4)

    def test_user_can_add_rule_and_keyword_without_code_changes(self):
        spec = lexer.load_token_specifications()
        spec["keywords"].append("print")
        spec["tokens"].insert(0, {"name": "ARROW", "pattern": "->"})
        scanner = lexer.generate_scanner(spec)
        got = [(t["type"], t["lexeme"]) for t in scan("print a->b", scanner=scanner)[0]]
        self.assertEqual(got, [("KEYWORD", "print"), ("IDENTIFIER", "a"), ("ARROW", "->"), ("IDENTIFIER", "b")])

    def test_longest_match_does_not_depend_on_rule_order(self):
        spec = {"tokens": [{"name": "ASSIGN", "pattern": "="}, {"name": "EQUALS", "pattern": "=="}]}
        got = [(t["type"], t["lexeme"]) for t in scan("a==b", scanner=lexer.generate_scanner(
            {"tokens": spec["tokens"] + [{"name": "ID", "pattern": "[a-z]+"}]}))[0]]
        self.assertEqual(got, [("ID", "a"), ("EQUALS", "=="), ("ID", "b")])

    def test_tie_goes_to_earlier_rule(self):
        spec = {"keywords": [], "tokens": [{"name": "IF_WORD", "pattern": "if"},
                                           {"name": "ID", "pattern": "[a-z]+"}]}
        scanner = lexer.generate_scanner(spec)
        self.assertEqual(scan("if", scanner=scanner)[0][0]["type"], "IF_WORD")
        self.assertEqual(scan("iffy", scanner=scanner)[0][0]["type"], "ID")


class TestLargerPrograms(unittest.TestCase):

    def check_positions(self, source, tokens):
        """Independent check: the text at (line, column) must equal the lexeme."""
        lines = source.split("\n")
        for t in tokens:
            first_part = t["lexeme"].split("\n")[0]
            text = lines[t["line"] - 1][t["column"] - 1:]
            self.assertTrue(text.startswith(first_part), t)

    def test_12_larger_program(self):
        source = lexer.read_text_file(sample_path("larger_program.c"))
        tokens, errors = scan(source)
        self.assertEqual(errors, [])
        types = {t["type"] for t in tokens}
        for needed in ("KEYWORD", "IDENTIFIER", "NUMBER", "FLOAT_NUMBER", "STRING_LITERAL", "CHAR_LITERAL",
                       "PREPROCESSOR_DIRECTIVE", "DELIMITER", "ARITHMETIC_OPERATOR", "RELATIONAL_OPERATOR",
                       "LOGICAL_OPERATOR", "ASSIGNMENT_OPERATOR"):
            self.assertIn(needed, types)
        self.assertIn(("IDENTIFIER", "printf"), [(t["type"], t["lexeme"]) for t in tokens])
        self.check_positions(source, tokens)

    def test_nothing_is_lost_or_invented(self):
        """With hidden tokens shown, joining all lexemes must rebuild the source exactly."""
        for name in ("larger_program.c", "sample_program.c"):
            source = lexer.read_text_file(sample_path(name))
            tokens, errors = scan(source, show_hidden=True)
            self.assertEqual(errors, [])
            self.assertEqual("".join(t["lexeme"] for t in tokens), source)
            self.check_positions(source, tokens)

    def test_expected_sample_program(self):
        source = lexer.read_text_file(sample_path("sample_program.c"))
        tokens, errors = scan(source)
        self.assertEqual((len(tokens), len(errors)), (33, 0))
        by_position = {(t["line"], t["column"]): (t["type"], t["lexeme"]) for t in tokens}
        self.assertEqual(by_position[(5, 15)], ("RELATIONAL_OPERATOR", ">="))
        self.assertEqual(by_position[(3, 18)], ("FLOAT_NUMBER", "2.5"))

    def test_error_sample(self):
        source = lexer.read_text_file(sample_path("sample_with_errors.c"))
        tokens, errors = scan(source)
        self.assertEqual([(e["line"], e["column"]) for e in errors],
                         [(2, 20), (3, 16), (4, 18), (5, 17), (8, 1)])


class TestOutput(unittest.TestCase):

    def test_table_and_summary(self):
        tokens, errors = scan("int total = 25;")
        table = lexer.display_tokens(tokens)
        self.assertIn("Token Type", table.splitlines()[0])
        self.assertIn("KEYWORD", table)
        self.assertEqual(lexer.format_summary(tokens, errors), "Total tokens recognized: 5    Lexical errors: 0")
        self.assertEqual(lexer.format_errors([]), "No lexical errors.")

    def test_save_csv_and_txt(self):
        tokens, errors = scan("int a;\n@")
        with tempfile.TemporaryDirectory() as folder:
            csv_path = os.path.join(folder, "sub", "tokens.csv")
            txt_path = os.path.join(folder, "tokens.txt")
            lexer.save_tokens(tokens, errors, csv_path)
            lexer.save_tokens(tokens, errors, txt_path)
            with open(csv_path, encoding="utf-8") as file:
                self.assertEqual(file.readline().strip(), "Token Type,Lexeme,Line,Column")
                self.assertIn("KEYWORD,int,1,1", file.read())
            with open(txt_path, encoding="utf-8") as file:
                self.assertIn("Lexical errors: 1", file.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
