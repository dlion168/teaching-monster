#!/usr/bin/env python3
"""
Math Renderer Module

Renders LaTeX mathematical equations as PNG images for embedding in slides.
Uses matplotlib's native LaTeX rendering engine.
"""

import os
import re
import hashlib
from pathlib import Path
from typing import Optional, Tuple

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from matplotlib import mathtext


def _find_matching_brace(s: str, open_idx: int) -> int:
    """Return index of the '}' matching the '{' at open_idx, or -1."""
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    return -1


def _strip_macro_drop_first_arg(latex: str, macro: str) -> str:
    """Strip \\macro{ARG1}{ARG2} -> ARG2 (drop first {} group, keep second).
    Used for \\color and \\textcolor."""
    pattern = '\\' + macro
    search_from = 0
    while True:
        idx = latex.find(pattern, search_from)
        if idx == -1:
            return latex
        end_of_name = idx + len(pattern)
        # Ensure full-token match (e.g. don't match \\colorful as \\color)
        if end_of_name < len(latex) and latex[end_of_name].isalpha():
            search_from = end_of_name
            continue
        start1 = latex.find('{', end_of_name)
        if start1 == -1:
            search_from = end_of_name
            continue
        end1 = _find_matching_brace(latex, start1)
        if end1 == -1:
            return latex
        # Look for optional second {ARG2}, skipping whitespace between args
        j = end1 + 1
        while j < len(latex) and latex[j] in ' \t':
            j += 1
        if j < len(latex) and latex[j] == '{':
            end2 = _find_matching_brace(latex, j)
            if end2 != -1:
                inner = latex[j + 1:end2]
                latex = latex[:idx] + inner + latex[end2 + 1:]
                search_from = idx + len(inner)
                continue
        # No second arg — just drop \\macro{ARG1}
        latex = latex[:idx] + latex[end1 + 1:]
        search_from = idx


def _strip_macro_keep_arg(latex: str, macro: str) -> str:
    """Strip \\macro{X} -> X (keep contents, drop wrapper).
    Used for \\cancel, \\boxed, \\text, etc."""
    pattern = '\\' + macro
    search_from = 0
    while True:
        idx = latex.find(pattern, search_from)
        if idx == -1:
            return latex
        end_of_name = idx + len(pattern)
        if end_of_name < len(latex) and latex[end_of_name].isalpha():
            search_from = end_of_name
            continue
        start1 = latex.find('{', end_of_name)
        if start1 == -1:
            search_from = end_of_name
            continue
        end1 = _find_matching_brace(latex, start1)
        if end1 == -1:
            return latex
        inner = latex[start1 + 1:end1]
        latex = latex[:idx] + inner + latex[end1 + 1:]
        search_from = idx + len(inner)


def sanitize_for_mathtext(latex: str) -> str:
    """Convert common unsupported LaTeX macros into mathtext-compatible form.

    Mathtext is matplotlib's built-in math parser. It supports a subset of LaTeX.
    This function rewrites the most common LLM-emitted incompatibilities."""
    # Strip color wrappers (keep the content)
    latex = _strip_macro_drop_first_arg(latex, 'color')
    latex = _strip_macro_drop_first_arg(latex, 'textcolor')

    # Strip wrappers that just decorate the inner content
    for macro in ('cancel', 'bcancel', 'xcancel', 'boxed', 'underline'):
        latex = _strip_macro_keep_arg(latex, macro)

    # Replace bold/italic text wrappers BEFORE the generic \\text rewrite,
    # otherwise \\text would partially match \\textbf / \\textit.
    latex = re.sub(r'\\textbf(?=\s*\{)', r'\\mathbf', latex)
    latex = re.sub(r'\\textit(?=\s*\{)', r'\\mathit', latex)

    # Replace text-mode wrappers with mathrm (which mathtext supports)
    for macro in ('textrm', 'textsf', 'texttt', 'text'):
        pattern = '\\' + macro
        search_from = 0
        while True:
            idx = latex.find(pattern, search_from)
            if idx == -1:
                break
            end_of_name = idx + len(pattern)
            if end_of_name < len(latex) and latex[end_of_name].isalpha():
                search_from = end_of_name
                continue
            latex = latex[:idx] + '\\mathrm' + latex[end_of_name:]
            search_from = idx + len('\\mathrm')

    # Token-level substitutions: macro names mapping to supported equivalents
    token_subs = {
        r'\implies': r'\Rightarrow',
        r'\iff': r'\Leftrightarrow',
        r'\dfrac': r'\frac',
        r'\tfrac': r'\frac',
        r'\boldsymbol': r'\mathbf',
        r'\bm': r'\mathbf',
    }
    for old, new in token_subs.items():
        # word-boundary at end (next char must not be a letter)
        latex = re.sub(re.escape(old) + r'(?![A-Za-z])', new.replace('\\', r'\\'), latex)

    # Drop LaTeX line breaks (not supported)
    latex = latex.replace('\\\\', ' ')

    # Drop align/cases environments — keep only their content
    latex = re.sub(r'\\begin\{(?:align\*?|cases|gather\*?|equation\*?)\}', '', latex)
    latex = re.sub(r'\\end\{(?:align\*?|cases|gather\*?|equation\*?)\}', '', latex)
    # & alignment markers are not supported — drop them
    latex = latex.replace('&', ' ')

    return latex


def aggressive_strip_to_text(latex: str) -> str:
    """Last-resort: strip all backslash macros and braces so the result is at
    least readable as plain text. Used as final fallback when mathtext fails."""
    # First run the normal sanitizer
    s = sanitize_for_mathtext(latex)
    # Remove remaining backslash macros (\\foo or \\foo{...})
    s = re.sub(r'\\[A-Za-z]+', '', s)
    # Remove $ delimiters
    s = s.replace('$', '')
    # Remove braces
    s = s.replace('{', '').replace('}', '')
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s


class MathRenderer:
    """Render LaTeX math equations to PNG images."""

    def __init__(self, cache_dir: str = None):
        """
        Initialize the Math Renderer.

        Args:
            cache_dir: Directory to cache rendered images (default: ./math_cache)
        """
        self.cache_dir = Path(cache_dir) if cache_dir else Path("tmp/math_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def render_latex(
        self,
        latex: str,
        font_size: int = 24,
        color: str = "#000000",
        dpi: int = 300,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Render a LaTeX math expression to PNG.

        Args:
            latex: LaTeX math string (e.g., "E = mc^2" or "\\frac{1}{2}")
            font_size: Font size in points
            color: Text color in hex format
            dpi: Resolution in dots per inch
            output_path: Custom output path (if None, uses cache)

        Returns:
            Path to the generated PNG file, or None if rendering failed
        """
        # Normalize LaTeX (sanitize + ensure math mode)
        latex_normalized = self._normalize_latex(latex)

        # Generate cache key
        cache_key = self._generate_cache_key(latex_normalized, font_size, color, dpi)

        # Check cache first
        if output_path is None:
            output_path = str(self.cache_dir / f"{cache_key}.png")
            if os.path.exists(output_path):
                return output_path

        # Primary attempt: render sanitized LaTeX as math
        try:
            self._render_to_file(latex_normalized, output_path, font_size, color, dpi)
            return output_path
        except Exception as e:
            print(f"Math rendering error (sanitized math attempt): {e}")
            print(f"LaTeX string: {latex}")
            print(f"Sanitized: {latex_normalized}")

        # Fallback: render as plain text (no math mode) so the slide is not blank
        try:
            plain = aggressive_strip_to_text(latex)
            if not plain:
                return None
            print(f"Math rendering: falling back to plain-text render of '{plain}'")
            self._render_to_file(
                plain, output_path, font_size, color, dpi, as_plain_text=True
            )
            return output_path
        except Exception as e:
            print(f"Math rendering fallback also failed: {e}")
            return None

    def _normalize_latex(self, latex: str) -> str:
        """
        Sanitize unsupported macros, then wrap in math-mode delimiters.

        Args:
            latex: Raw LaTeX string

        Returns:
            Normalized LaTeX with proper delimiters
        """
        latex = latex.strip()

        # Strip outer math delimiters (we re-add them after sanitization)
        if latex.startswith('$$') and latex.endswith('$$'):
            inner = latex[2:-2]
        elif latex.startswith('$') and latex.endswith('$'):
            inner = latex[1:-1]
        else:
            inner = latex

        inner = sanitize_for_mathtext(inner)
        return f'${inner}$'

    def _generate_cache_key(
        self,
        latex: str,
        font_size: int,
        color: str,
        dpi: int
    ) -> str:
        """Generate a unique cache key for the rendered equation."""
        content = f"{latex}|{font_size}|{color}|{dpi}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _render_to_file(
        self,
        latex: str,
        output_path: str,
        font_size: int,
        color: str,
        dpi: int,
        as_plain_text: bool = False,
    ):
        """
        Actually render the LaTeX to a PNG file using matplotlib.

        Args:
            latex: Normalized LaTeX string (or plain text if as_plain_text=True)
            output_path: Where to save the PNG
            font_size: Font size in points
            color: Hex color code
            dpi: Resolution
            as_plain_text: If True, render without math mode (fallback path)
        """
        # Convert hex color to RGB tuple
        rgb = self._hex_to_rgb(color)

        # Create figure with transparent background
        fig = plt.figure(figsize=(0.01, 0.01))
        fig.patch.set_alpha(0.0)

        try:
            # Render the math text (or plain text on fallback path)
            text_kwargs = dict(
                fontsize=font_size,
                color=rgb,
                ha='center',
                va='center',
                transform=fig.transFigure,
            )
            if as_plain_text:
                text_kwargs['fontfamily'] = 'monospace'
            text = fig.text(0.5, 0.5, latex, **text_kwargs)

            # Get tight bounding box
            fig.canvas.draw()
            bbox = text.get_window_extent(fig.canvas.get_renderer())
            bbox_inches = bbox.transformed(fig.dpi_scale_trans.inverted())

            # Expand bbox slightly for padding
            bbox_inches = bbox_inches.padded(0.1)

            # Save with tight bbox
            plt.savefig(
                output_path,
                dpi=dpi,
                bbox_inches=bbox_inches,
                transparent=True,
                format='png',
                pad_inches=0
            )

        finally:
            plt.close(fig)

    def _hex_to_rgb(self, hex_color: str) -> Tuple[float, float, float]:
        """
        Convert hex color to RGB tuple (0-1 range).

        Args:
            hex_color: Hex color string like "#FF0000"

        Returns:
            RGB tuple with values in [0, 1]
        """
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
        return (r, g, b)

    def estimate_size(self, latex: str, font_size: int) -> Tuple[float, float]:
        """
        Estimate the rendered size of a LaTeX equation in inches.

        Args:
            latex: LaTeX string
            font_size: Font size in points

        Returns:
            Tuple of (width_inches, height_inches)
        """
        # Rough heuristic: scale with font size and character count
        # This is approximate - actual rendering may vary
        char_count = len(latex)
        base_width = 0.1 * font_size / 24  # Base width per character
        base_height = 0.5 * font_size / 24  # Base height

        width = base_width * char_count
        height = base_height

        # Adjust for complex expressions
        if '\\frac' in latex or '\\sum' in latex or '\\int' in latex:
            height *= 1.5
        if '\\sqrt' in latex:
            height *= 1.3

        return (width, height)
