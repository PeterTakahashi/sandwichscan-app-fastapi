from enum import Enum


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "validation_error"
    INVALID_PAYLOAD = "invalid_payload"
    UNAUTHORIZED = "unauthorized"
    UNAUTHORIZED_API_KEY = "unauthorized_api_key"
    NOT_FOUND = "not_found"
    INVALID_IP = "invalid_ip"
    INVALID_ORIGIN = "invalid_origin"
    EXPIRED_API_KEY = "expired_api_key"
    LOGIN_ACCOUNT_LOCKED = "login_account_locked"
    INVALID_STATE_TOKEN = "invalid_state_token"
    INTERNAL_SERVER_ERROR = "internal_server_error"
