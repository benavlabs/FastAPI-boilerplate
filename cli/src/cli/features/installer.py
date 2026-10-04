"""Execute a ``FeaturePlan`` against the user's project.

V1 supports file rendering only. Codemods and hooks raise
``NotImplementedError`` so plans can declare them today and the
installer will gain support over time without breaking the contract.
"""

from __future__ import annotations

import stat
from dataclasses import dataclass, field
from pathlib import Path

from ..lib.prompts import confirm_overwrite, info, success, warn
from ..lib.render import Renderer
from .base import FeaturePlan


@dataclass
class InstallResult:
    """Summary of what an installer pass actually did."""

    files_written: list[Path] = field(default_factory=list)
    files_skipped: list[Path] = field(default_factory=list)


class FeatureInstaller:
    """Apply a ``FeaturePlan`` to disk.

    Construction options control the prompting / I/O behavior.
    """

    def __init__(self, *, dry_run: bool = False, assume_yes: bool = False, quiet: bool = False) -> None:
        self.dry_run = dry_run
        self.assume_yes = assume_yes
        self.quiet = quiet

    def apply(self, plan: FeaturePlan) -> InstallResult:
        result = InstallResult()
        if plan.codemods:
            raise NotImplementedError("Codemod operations are not yet supported by the installer.")
        if plan.hooks:
            raise NotImplementedError("Post-install hooks are not yet supported by the installer.")

        renderer: Renderer | None = None
        if plan.files and plan.templates_root is not None:
            renderer = Renderer(plan.templates_root)

        for op in plan.files:
            if op.target.exists():
                if op.skip_if_exists:
                    if not self.quiet:
                        warn(f"skip {op.target} (exists)")
                    result.files_skipped.append(op.target)
                    continue
                if not op.overwrite and not self.dry_run:
                    if not confirm_overwrite(str(op.target), assume_yes=self.assume_yes):
                        if not self.quiet:
                            warn(f"skip {op.target} (kept existing)")
                        result.files_skipped.append(op.target)
                        continue

            if renderer is None:
                raise RuntimeError(f"Plan has files but no templates_root: cannot render {op.template!r}")

            content = renderer.render(op.template, plan.template_context)

            if self.dry_run:
                if not self.quiet:
                    replacing = " (replacing what is there)" if op.target.exists() else ""
                    info(f"would write {op.target} ({len(content)} bytes){replacing}")
                result.files_written.append(op.target)
                continue

            op.target.parent.mkdir(parents=True, exist_ok=True)
            op.target.write_text(content, encoding="utf-8")
            if op.executable:
                _make_executable(op.target)
            if not self.quiet:
                success(f"wrote {op.target}")
            result.files_written.append(op.target)

        return result


def _make_executable(path: Path) -> None:
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
