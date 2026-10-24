"""
gui.py - Tkinter front-end for the Mini Lexical Analyzer Generator.

The GUI contains NO scanning logic. It only calls functions from lexer.py:
    lexer.generate_scanner()      when you press "Generate Scanner"
    lexer.analyze_source_code()   when you press "Analyze"
"""

import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import lexer

EDITOR_FONT = ("Consolas", 11)


def set_read_only_text(widget, text):
    """Replace the contents of a read-only Text widget."""
    widget.config(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", text)
    widget.config(state="disabled")


def run_gui():
    root = tk.Tk()
    root.title("Mini Lexical Analyzer Generator")
    root.geometry("1150x740")
    root.minsize(900, 560)

    # Shared data for the button handlers below.
    state = {"scanner": None, "tokens": [], "errors": [], "token_by_row": {}}
    show_hidden_var = tk.BooleanVar(value=False)

    # ------------------------------------------------------------------ layout
    toolbar = ttk.Frame(root, padding=6)
    toolbar.pack(fill="x")

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    main_tab = ttk.Frame(notebook)
    rules_tab = ttk.Frame(notebook)
    notebook.add(main_tab, text="Source Code and Tokens")
    notebook.add(rules_tab, text="Token Rules (JSON)")

    # --- main tab: editor (left), token table (right), errors (bottom)
    panes = ttk.PanedWindow(main_tab, orient="horizontal")
    # (packed further down, after the bottom areas, so the error box is never squeezed out)

    editor_frame = ttk.LabelFrame(panes, text="Source code (type, paste or load a file)")
    source_text = scrolledtext.ScrolledText(editor_frame, wrap="none", font=EDITOR_FONT, undo=True)
    source_text.pack(fill="both", expand=True, padx=4, pady=4)
    cursor_label = ttk.Label(editor_frame, text="Ln 1, Col 1")
    cursor_label.pack(anchor="e", padx=6)
    panes.add(editor_frame, weight=1)

    table_frame = ttk.LabelFrame(panes, text="Token table")
    columns = ("type", "lexeme", "line", "column")
    token_table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
    for name, title, width in (("type", "Token Type", 160), ("lexeme", "Lexeme", 120),
                               ("line", "Line", 50), ("column", "Column", 60)):
        token_table.heading(name, text=title)
        token_table.column(name, width=width, minwidth=45, stretch=(name == "lexeme"), anchor="w" if name in ("type", "lexeme") else "center")
    table_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=token_table.yview)
    token_table.configure(yscrollcommand=table_scroll.set)
    token_table.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
    table_scroll.pack(side="right", fill="y", pady=4)
    panes.add(table_frame, weight=1)

    error_frame = ttk.LabelFrame(main_tab, text="Lexical errors")
    error_frame.pack(side="bottom", fill="x", pady=(6, 0))
    status_frame = ttk.Frame(main_tab)
    status_frame.pack(side="bottom", fill="x", pady=(6, 0))
    summary_label = ttk.Label(status_frame, text="Total tokens recognized: 0    Lexical errors: 0",
                              font=("Segoe UI", 10, "bold"))
    summary_label.pack(anchor="w")
    scanner_label = ttk.Label(status_frame, text="Scanner: not generated yet")
    scanner_label.pack(anchor="w")

    panes.pack(side="top", fill="both", expand=True)
    error_text = tk.Text(error_frame, height=6, wrap="none", state="disabled",
                         font=EDITOR_FONT, foreground="#9b1c1c")
    error_text.pack(fill="x", padx=4, pady=4)

    # --- rules tab: JSON editor
    rules_bar = ttk.Frame(rules_tab, padding=4)
    rules_bar.pack(fill="x")
    rules_text = scrolledtext.ScrolledText(rules_tab, wrap="none", font=EDITOR_FONT, undo=True)
    rules_text.pack(fill="both", expand=True, padx=4, pady=4)

    # Highlight colours inside the source editor.
    source_text.tag_configure("selected_token", background="#ffe08a")
    source_text.tag_configure("error_mark", background="#f6b8b8")

    # ---------------------------------------------------------------- handlers
    def update_cursor_label(event=None):
        line, column = source_text.index("insert").split(".")
        cursor_label.config(text="Ln %s, Col %d" % (line, int(column) + 1))

    def clear_marks():
        source_text.tag_remove("selected_token", "1.0", "end")
        source_text.tag_remove("error_mark", "1.0", "end")

    def clear_results():
        token_table.delete(*token_table.get_children())
        state["token_by_row"] = {}
        state["tokens"] = []
        state["errors"] = []
        set_read_only_text(error_text, "")
        summary_label.config(text="Total tokens recognized: 0    Lexical errors: 0")
        clear_marks()

    def load_sample():
        if os.path.exists(lexer.DEFAULT_SAMPLE_PATH):
            sample = lexer.read_text_file(lexer.DEFAULT_SAMPLE_PATH)
        else:
            sample = lexer.FALLBACK_SAMPLE
        source_text.delete("1.0", "end")
        source_text.insert("1.0", sample)
        clear_results()

    def load_source_file():
        path = filedialog.askopenfilename(
            title="Open source file",
            initialdir=os.path.join(lexer.BASE_DIR, "samples"),
            filetypes=[("C or text files", "*.c *.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            content = lexer.read_text_file(path)
        except OSError as error:
            messagebox.showerror("Cannot open file", str(error))
            return
        source_text.delete("1.0", "end")
        source_text.insert("1.0", content)
        clear_results()

    def generate_scanner_from_rules():
        """Read the JSON in the rules tab and build a new scanner from it."""
        try:
            spec_data = lexer.parse_specification_text(rules_text.get("1.0", "end-1c"))
            scanner = lexer.generate_scanner(spec_data)
        except lexer.SpecError as error:
            messagebox.showerror("Cannot generate scanner",
                                 "%s\n\nThe previous scanner (if any) is still in use." % error)
            return False
        state["scanner"] = scanner
        text = "Scanner generated: %d rules, %d keywords" % (len(scanner["rules"]), len(scanner["keywords"]))
        if scanner["problems"]:
            text += "  (%d rule problem(s) - see the error area)" % len(scanner["problems"])
            set_read_only_text(error_text, "\n".join("Specification warning: " + p for p in scanner["problems"]))
        scanner_label.config(text=text)
        return True

    def open_rules_file():
        path = filedialog.askopenfilename(title="Open token specification",
                                          initialdir=lexer.BASE_DIR,
                                          filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            content = lexer.read_text_file(path)
        except OSError as error:
            messagebox.showerror("Cannot open file", str(error))
            return
        rules_text.delete("1.0", "end")
        rules_text.insert("1.0", content)
        generate_scanner_from_rules()

    def save_rules_file():
        path = filedialog.asksaveasfilename(title="Save token specification", defaultextension=".json",
                                            initialdir=lexer.BASE_DIR, filetypes=[("JSON files", "*.json")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(rules_text.get("1.0", "end-1c"))
        except OSError as error:
            messagebox.showerror("Cannot save file", str(error))

    def analyze():
        if state["scanner"] is None and not generate_scanner_from_rules():
            return
        source = source_text.get("1.0", "end-1c")
        tokens, errors = lexer.analyze_source_code(source, state["scanner"], show_hidden_var.get())

        clear_results()
        state["tokens"], state["errors"] = tokens, errors

        for token in tokens:
            row = token_table.insert("", "end", values=(
                token["type"], lexer.printable_lexeme(token["lexeme"]), token["line"], token["column"]))
            state["token_by_row"][row] = token

        set_read_only_text(error_text, lexer.format_errors(errors))
        summary_label.config(text=lexer.format_summary(tokens, errors))

        for error in errors:                      # mark bad input in red
            start = "%d.%d" % (error["line"], error["column"] - 1)
            source_text.tag_add("error_mark", start, "%s+%dc" % (start, len(error["lexeme"])))

    def on_row_selected(event=None):
        selection = token_table.selection()
        if not selection:
            return
        token = state["token_by_row"].get(selection[0])
        if token is None:
            return
        source_text.tag_remove("selected_token", "1.0", "end")
        start = "%d.%d" % (token["line"], token["column"] - 1)
        source_text.tag_add("selected_token", start, "%s+%dc" % (start, len(token["lexeme"])))
        source_text.see(start)

    def save_tokens_to_file():
        if not state["tokens"] and not state["errors"]:
            messagebox.showinfo("Nothing to save", "Press Analyze first.")
            return
        os.makedirs(lexer.OUTPUT_DIR, exist_ok=True)
        path = filedialog.asksaveasfilename(
            title="Save tokens", defaultextension=".csv", initialdir=lexer.OUTPUT_DIR,
            filetypes=[("CSV file", "*.csv"), ("Text file", "*.txt")])
        if not path:
            return
        try:
            lexer.save_tokens(state["tokens"], state["errors"], path)
        except OSError as error:
            messagebox.showerror("Cannot save file", str(error))

    def clear_all():
        source_text.delete("1.0", "end")
        clear_results()

    def mark_rules_edited(event=None):
        scanner_label.config(text="Rules edited - press 'Generate Scanner' to apply the changes")

    # ----------------------------------------------------------------- buttons
    for label, command in (("Load File", load_source_file), ("Load Sample", load_sample),
                           ("Generate Scanner", generate_scanner_from_rules), ("Analyze", analyze),
                           ("Save Tokens", save_tokens_to_file), ("Clear", clear_all)):
        ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=3)
    ttk.Checkbutton(toolbar, text="Show whitespace and comments",
                    variable=show_hidden_var).pack(side="left", padx=12)

    for label, command in (("Open Rules File", open_rules_file), ("Save Rules File", save_rules_file),
                           ("Generate Scanner", generate_scanner_from_rules)):
        ttk.Button(rules_bar, text=label, command=command).pack(side="left", padx=3)

    token_table.bind("<<TreeviewSelect>>", on_row_selected)
    source_text.bind("<KeyRelease>", update_cursor_label)
    source_text.bind("<ButtonRelease-1>", update_cursor_label)
    rules_text.bind("<KeyRelease>", mark_rules_edited)

    # ----------------------------------------------------------- initial state
    try:
        rules_text.insert("1.0", lexer.read_text_file(lexer.DEFAULT_SPEC_PATH))
    except OSError as error:
        messagebox.showwarning("Specification missing",
                               "Could not read token_specifications.json:\n%s" % error)
    generate_scanner_from_rules()
    load_sample()

    root.mainloop()
