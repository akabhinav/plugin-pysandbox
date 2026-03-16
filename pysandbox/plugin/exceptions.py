"""Plugin-related exceptions."""


class PluginError(Exception):
    """Base exception for plugin operations."""


class PluginNotFoundError(PluginError):
    """Raised when a requested plugin is not in the registry."""


class PluginInstallError(PluginError):
    """Raised when plugin installation fails."""

    def __init__(self, plugin_id: str, reason: str):
        self.plugin_id = plugin_id
        self.reason = reason
        super().__init__(f"Failed to install '{plugin_id}': {reason}")


class PluginRemoveError(PluginError):
    """Raised when plugin removal fails."""

    def __init__(self, plugin_id: str, reason: str):
        self.plugin_id = plugin_id
        self.reason = reason
        super().__init__(f"Failed to remove '{plugin_id}': {reason}")


class ManifestValidationError(PluginError):
    """Raised when a plugin manifest is invalid."""


class ConfigValidationError(PluginError):
    """Raised when user-supplied config doesn't match the manifest schema."""
