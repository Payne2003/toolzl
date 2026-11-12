class BotError(Exception):
    """Lỗi nghiệp vụ có thông điệp thân thiện để hiển thị cho người dùng."""


class ValidationError(BotError):
    pass


class ApprovalError(BotError):
    pass


class GateBlocked(BotError):
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


class NotFound(BotError):
    pass
