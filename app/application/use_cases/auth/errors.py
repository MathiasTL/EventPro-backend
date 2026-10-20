class AuthError(Exception):
    """Error base del dominio de autenticación."""


class InvalidCredentialsError(AuthError):
    """Correo/contraseña incorrectos o refresh token inválido, revocado o vencido."""


class UserInactiveError(AuthError):
    """El usuario está desactivado (is_active = false)."""
