from .manual import apply_spec, load_spec

__all__ = ["write_script", "load_spec", "apply_spec"]


def write_script(*args, **kwargs):
    # Lazy import so the Claude/Anthropic dependency is only needed when you
    # actually use the API writer (not for the manual / chat-authored path).
    from .writer import write_script as _write_script
    return _write_script(*args, **kwargs)
