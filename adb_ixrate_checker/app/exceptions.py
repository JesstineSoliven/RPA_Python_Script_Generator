class AdbIxrateError(Exception):
    pass


class InterfaceFileNotFoundError(AdbIxrateError):
    pass


class InterfaceFileParseError(AdbIxrateError):
    pass


class RateFetchError(AdbIxrateError):
    pass


class WebDriverError(AdbIxrateError):
    pass


class ConfigurationError(AdbIxrateError):
    pass
