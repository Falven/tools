__all__ = ["render_heatmap"]

import base64
import io
from typing import Any


def render_heatmap(
    rows: list[str],
    cols: list[str],
    values: list[list[float]],
    title: str = "",
    subtitle: str = "",
    scale: str = "score",
    cell_text: list[list[str]] | None = None,
    suppressed_mask: list[list[bool]] | None = None,
    target_col_index: int | None = None,
    divider_after_col: int | None = None,
) -> dict:
    """Render a deterministic PNG heatmap and return base64 image data."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    matrix = _validate_matrix(values, len(rows), len(cols), "values")
    labels = _validate_text_matrix(cell_text, len(rows), len(cols), "cell_text") if cell_text is not None else None
    suppressed = _validate_bool_matrix(suppressed_mask, len(rows), len(cols), "suppressed_mask") if suppressed_mask is not None else None
    fig, ax = plt.subplots(figsize=(1.45 * len(cols) + 1.6, 0.62 * len(rows) + 1.6), dpi=200)
    vmin, vmax = _scale_bounds(matrix, scale)
    image = ax.imshow(matrix, cmap="YlOrRd", aspect="auto", vmin=vmin, vmax=vmax)

    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(cols, rotation=20, ha="right", fontsize=9, fontfamily="monospace")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows, fontsize=9, fontfamily="monospace")

    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            is_suppressed = bool(suppressed and suppressed[i][j])
            text = labels[i][j] if labels else (f"{value:.0f}" if abs(value) >= 1 else f"{value:.2f}")
            if is_suppressed:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=True, color="#E5E7EB", alpha=0.78))
                text = text or "Suppressed"
            ax.text(j, i, text, ha="center", va="center", fontsize=8, color="#16181D", fontfamily="monospace")

    if target_col_index is not None:
        ax.add_patch(plt.Rectangle((target_col_index - 0.5, -0.5), 1, len(rows), fill=False, edgecolor="#7F1D1D", linewidth=2.0))
    if divider_after_col is not None:
        ax.axvline(divider_after_col + 0.5, color="#374151", linewidth=1.4)
    if title:
        ax.set_title(title, fontsize=11)
    if subtitle:
        ax.set_xlabel(subtitle, fontsize=8, labelpad=12)
    fig.colorbar(image, ax=ax, shrink=0.7)
    fig.tight_layout()

    output = io.BytesIO()
    fig.savefig(output, format="png")
    plt.close(fig)
    image_png_b64 = base64.b64encode(output.getvalue()).decode("ascii")
    return {
        "format": "image/png;base64",
        "image_png_b64": image_png_b64,
        "renderStatus": "HEATMAP_RENDER_OK",
        "rows": len(rows),
        "cols": len(cols),
        "scale": scale,
        "cmap": "YlOrRd",
        "targetColumn": target_col_index,
        "mock": False,
        "source_material": "crm-copilot-skills-sandbox/whitespace-heatmap/SKILL.md",
        "sourceCoverage": {"renderer": {"status": "MATCHED"}, "uiDisplay": {"status": "EY_VALIDATE", "reason": "Validate actual inline image rendering through ToolForge/Copilot, not only JSON output."}},
    }


def _validate_matrix(values: Any, row_count: int, col_count: int, name: str) -> list[list[float]]:
    if not isinstance(values, list) or len(values) != row_count:
        raise ValueError(f"{name} must have exactly {row_count} rows.")
    matrix = []
    for row in values:
        if not isinstance(row, list) or len(row) != col_count:
            raise ValueError(f"{name} rows must each have exactly {col_count} columns.")
        matrix.append([float(value) for value in row])
    return matrix


def _validate_text_matrix(values: Any, row_count: int, col_count: int, name: str) -> list[list[str]]:
    if not isinstance(values, list) or len(values) != row_count:
        raise ValueError(f"{name} must have exactly {row_count} rows.")
    matrix = []
    for row in values:
        if not isinstance(row, list) or len(row) != col_count:
            raise ValueError(f"{name} rows must each have exactly {col_count} columns.")
        matrix.append([str(value) for value in row])
    return matrix


def _validate_bool_matrix(values: Any, row_count: int, col_count: int, name: str) -> list[list[bool]]:
    if not isinstance(values, list) or len(values) != row_count:
        raise ValueError(f"{name} must have exactly {row_count} rows.")
    matrix = []
    for row in values:
        if not isinstance(row, list) or len(row) != col_count:
            raise ValueError(f"{name} rows must each have exactly {col_count} columns.")
        matrix.append([bool(value) for value in row])
    return matrix


def _scale_bounds(values: list[list[float]], scale: str) -> tuple[float | None, float | None]:
    if scale in {"penetration", "score"}:
        return 1.0, 4.0
    if scale == "row_relative":
        return 0.0, 1.0
    return None, None
