from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class AuthenticationError(AppError):
    def __init__(self, message: str = "帳號或密碼錯誤") -> None:
        super().__init__("AUTHENTICATION_FAILED", message, 401)


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "沒有執行此操作的權限") -> None:
        super().__init__("PERMISSION_DENIED", message, 403)


class ResourceNotFoundError(AppError):
    def __init__(self, resource: str) -> None:
        super().__init__("RESOURCE_NOT_FOUND", f"找不到指定的{resource}", 404)


class StorageError(AppError):
    def __init__(self, message: str = "物件儲存操作失敗") -> None:
        super().__init__("STORAGE_ERROR", message, 503)
