"""Charts drawn from real Yahoo Finance data: inline SVG lines and HTML bars, theme-aware."""
from html import escape


def line(series, w=320, h=96, pad=4):
    vals = [v for _, v in series]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    step = (w - 2 * pad) / (len(vals) - 1)
    pts = [(pad + i * step, pad + (h - 2 * pad) * (1 - (v - lo) / span)) for i, v in enumerate(vals)]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = d + f" L{pts[-1][0]:.1f},{h - pad} L{pts[0][0]:.1f},{h - pad} Z"
    cls = "up" if vals[-1] >= vals[0] else "down"
    return (f'<svg class="spark {cls}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
            f'<path class="area" d="{area}"/><path class="ln" d="{d}"/></svg>')


def fmt(v):
    return f"{v:,.2f}" if abs(v) < 100000 else f"{v:,.0f}"


def bars(rows):
    """rows: [(label, pct)]. Diverging bars around zero."""
    rows = [r for r in rows if r[1] is not None]
    if not rows:
        return ""
    vmax = max(abs(v) for _, v in rows) or 1
    out = ['<div class="bars split">']
    for label, v in rows:
        pct = abs(v) / vmax * 50
        pos = f"left:{50 - pct:.2f}%" if v < 0 else "left:50%"
        sign = "+" if v > 0 else "−" if v < 0 else ""
        out.append(f'<div class="bar"><span class="bl">{escape(label)}</span><span class="bt">'
                   f'<span class="bf {"pos" if v >= 0 else "neg"}" style="{pos};width:{max(pct, .6):.2f}%"></span></span>'
                   f'<span class="bv">{sign}{abs(v):.2f}%</span></div>')
    out.append("</div>")
    return "".join(out)
