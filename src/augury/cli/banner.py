"""What the run says about itself while it works.

A review of a real backend runs for minutes across several agents. Printing
nothing makes it indistinguishable from a hang; printing everything makes the
one line that matters impossible to find. This prints what a reader needs to
follow the investigation: what is being reviewed, who is reviewing it, and what
each step cost.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

TAGLINE = "Reads the code. Makes a falsifiable claim. Runs the experiment."

SUBTITLE = (
    "An engineering review for codebases assembled faster than they were designed. "
    "It reads the deployment first, follows the request path, and reports what it "
    "did not look at."
)


def opening(console: Console, *, target: str, provider: str, model: str) -> None:
    """The banner, once, at the start of a run."""
    console.print(
        Panel(
            f"[bold]AUGURY[/bold]\n[dim]{TAGLINE}[/dim]\n\n{SUBTITLE}",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print(f"  reviewing  [bold]{target}[/bold]")
    console.print(f"  model      {provider}/{model}\n")


def stage(console: Console, number: int, of: int, name: str, detail: str) -> None:
    """One pipeline stage announcing itself.

    Numbered because the order is the argument: the deployment is read before
    the code, and the code is walked outward from where a request arrives.
    """
    console.print(f"[cyan]{number}/{of}[/cyan] [bold]{name}[/bold]  [dim]{detail}[/dim]")


def note(console: Console, text: str) -> None:
    console.print(f"      [dim]{text}[/dim]")
