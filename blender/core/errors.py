"""Pipeline exception types.

Every failure raised inside the pipeline carries the asset id and the stage so
the build report and the CI log can say exactly what broke, e.g.

    ERROR: [chr_worker_miner_01] stage=deformation: elbow.L joint collapsed (0.31 < 0.45)
"""


class PipelineError(Exception):
    """Base class for all pipeline failures."""


class ConfigError(PipelineError):
    """Invalid or missing source specification / configuration."""


class ToolchainError(PipelineError):
    """Wrong Blender / exporter version or missing tool."""


class AssetBuildError(PipelineError):
    """A single asset failed in a specific stage."""

    def __init__(self, asset_id, stage, message):
        self.asset_id = asset_id
        self.stage = stage
        self.message = message
        super().__init__(f"[{asset_id}] stage={stage}: {message}")


class ValidationIssue:
    """A single validation finding. Errors fail the build; warnings only pass
    when their code is explicitly allowed in pipeline_config.json."""

    __slots__ = ("severity", "code", "message", "asset_id", "check")

    def __init__(self, severity, code, message, asset_id=None, check=None):
        if severity not in ("error", "warning"):
            raise ValueError(f"invalid severity {severity!r}")
        self.severity = severity
        self.code = code
        self.message = message
        self.asset_id = asset_id
        self.check = check

    def as_dict(self):
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "asset_id": self.asset_id,
            "check": self.check,
        }

    def __repr__(self):
        return f"{self.severity.upper()} {self.code}: {self.message}"


class ValidationFailed(PipelineError):
    """Raised when a validation stage produced blocking issues."""

    def __init__(self, asset_id, stage, issues):
        self.asset_id = asset_id
        self.stage = stage
        self.issues = list(issues)
        lines = "; ".join(f"{i.code}: {i.message}" for i in self.issues[:12])
        more = "" if len(self.issues) <= 12 else f" (+{len(self.issues) - 12} more)"
        super().__init__(f"[{asset_id}] stage={stage}: validation failed: {lines}{more}")
