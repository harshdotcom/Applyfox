#!/usr/bin/env python3
"""
latex_compiler.py - Compiles LaTeX CVs directly into genuine Overleaf-quality PDFs
using the standalone Tectonic LaTeX engine or system pdflatex/xelatex.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Union


def find_latex_compiler() -> Optional[Tuple[str, str]]:
    """Locate an available real LaTeX compiler."""
    # 1. Project-local standalone Tectonic engine
    local_tectonic = Path("bin/tectonic").resolve()
    if local_tectonic.is_file() and os.access(local_tectonic, os.X_OK):
        return ("tectonic", str(local_tectonic))

    # 2. User home ~/.local/bin/tectonic
    user_tectonic = Path.home() / ".local" / "bin" / "tectonic"
    if user_tectonic.is_file() and os.access(user_tectonic, os.X_OK):
        return ("tectonic", str(user_tectonic))

    # 3. System binaries
    for cmd in ["tectonic", "xelatex", "pdflatex", "lualatex"]:
        path = shutil.which(cmd)
        if path:
            return (cmd, path)

    return None


def compile_tex_to_pdf(
    tex_path_or_content: Union[str, Path],
    output_dir: Union[str, Path],
    output_filename: str = "tailored_cv.pdf"
) -> Tuple[bool, Optional[Path], str]:
    """
    Compile LaTeX source into a real PDF.
    Returns (success: bool, pdf_path: Optional[Path], log_message: str).
    """
    compiler_info = find_latex_compiler()
    if not compiler_info:
        return (
            False,
            None,
            "No LaTeX compiler found. Please ensure bin/tectonic or pdflatex is installed."
        )

    compiler_type, compiler_bin = compiler_info
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = output_dir / output_filename

    # Read content to ensure compatibility across engines
    is_temp = False
    str_input = str(tex_path_or_content)
    if r"\documentclass" in str_input or r"\begin{document}" in str_input:
        content = str_input
        source_tex = output_dir / "_temp_compile.tex"
        is_temp = True
    else:
        source_tex = Path(tex_path_or_content)
        if not source_tex.is_file():
            return (False, None, f"Source LaTeX file not found: {source_tex}")
        content = source_tex.read_text(encoding="utf-8")

    # Guard glyphtounicode for XeTeX/Tectonic compatibility
    if r"\input{glyphtounicode}" in content and r"\ifdefined\pdfgentounicode" not in content:
        content = content.replace(
            r"\input{glyphtounicode}",
            "\\ifdefined\\pdfgentounicode\n  \\input{glyphtounicode}\n  \\pdfgentounicode=1\n\\fi"
        )
        # If modifying in place for an existing file or temp
        source_tex.write_text(content, encoding="utf-8")
    elif is_temp:
        source_tex.write_text(content, encoding="utf-8")

    try:
        if compiler_type == "tectonic":
            cmd = [
                compiler_bin,
                "-o", str(output_dir),
                str(source_tex)
            ]
        elif compiler_type in ("xelatex", "pdflatex", "lualatex"):
            cmd = [
                compiler_bin,
                "-interaction=nonstopmode",
                f"-output-directory={output_dir}",
                str(source_tex)
            ]
        else:
            cmd = [compiler_bin, str(source_tex)]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)

        # Expected output filename for tectonic
        default_pdf_name = source_tex.stem + ".pdf"
        generated_pdf = output_dir / default_pdf_name

        if generated_pdf.is_file():
            if generated_pdf != target_pdf:
                shutil.move(str(generated_pdf), str(target_pdf))
            # Cleanup temp tex if created
            if source_tex.name == "_temp_compile.tex":
                try:
                    source_tex.unlink()
                except Exception:
                    pass
            return (True, target_pdf, "Compilation successful.")
        else:
            return (False, None, f"LaTeX compilation error:\n{res.stdout}")

    except Exception as e:
        return (False, None, f"Execution failed: {str(e)}")
