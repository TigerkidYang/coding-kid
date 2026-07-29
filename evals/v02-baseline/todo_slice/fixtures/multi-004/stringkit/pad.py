def pad_center(text: str, width: int, fill: str = " ") -> str:
    """Center text in a field of the given width."""
    if len(text) >= width:
        return text
    # BUG: pads only on the right
    return text + fill * (width - len(text))
