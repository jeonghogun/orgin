"""
Security and Encryption Utilities
"""

import os
import base64
import hashlib
import hmac
import secrets
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config.settings import settings

logger = logging.getLogger(__name__)


class EncryptionManager:
    """암호화 관리자"""
    
    def __init__(self):
        self.encryption_key = self._get_or_create_key()
        self.cipher_suite = Fernet(self.encryption_key)

    def _normalise_key(self, key: str) -> Optional[bytes]:
        """Validate and normalise a Fernet key string."""

        key_bytes = key.encode()
        try:
            Fernet(key_bytes)
            return key_bytes
        except (ValueError, TypeError):
            try:
                decoded = base64.urlsafe_b64decode(key_bytes)
                reencoded = base64.urlsafe_b64encode(decoded)
                Fernet(reencoded)
                return reencoded
            except Exception as exc:
                logger.error("Invalid encryption key provided: %s", exc)
        return None

    def _get_or_create_key(self) -> bytes:
        """Return a stable encryption key or raise if misconfigured."""

        candidate = settings.ENCRYPTION_KEY or os.getenv("ENCRYPTION_KEY")
        if candidate:
            normalised = self._normalise_key(candidate)
            if normalised:
                return normalised
            raise ValueError("ENCRYPTION_KEY is not a valid Fernet key")

        if settings.TESTING or settings.DEBUG:
            logger.warning(
                "ENCRYPTION_KEY not provided. Generating ephemeral key for test/debug runs."
            )
            new_key = Fernet.generate_key()
            os.environ["ENCRYPTION_KEY"] = new_key.decode()
            return new_key

        raise RuntimeError(
            "ENCRYPTION_KEY must be configured in production environments."
        )
    
    def encrypt(self, data: str) -> str:
        """데이터 암호화"""
        try:
            encrypted_data = self.cipher_suite.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted_data).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise
    
    def decrypt(self, encrypted_data: str) -> str:
        """데이터 복호화"""
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = self.cipher_suite.decrypt(encrypted_bytes)
            return decrypted_data.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise
    
    def hash_password(self, password: str, salt: Optional[str] = None) -> tuple[str, str]:
        """비밀번호 해싱"""
        if not salt:
            salt = secrets.token_hex(16)
        
        # PBKDF2를 사용한 해싱
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt.encode(),
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key.decode(), salt
    
    def verify_password(self, password: str, hashed_password: str, salt: str) -> bool:
        """비밀번호 검증"""
        try:
            expected_hash, _ = self.hash_password(password, salt)
            return hmac.compare_digest(hashed_password, expected_hash)
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False


class APIKeyManager:
    """API 키 관리자"""
    
    def __init__(self):
        self.encryption_manager = EncryptionManager()
        self.rotation_interval = settings.API_KEY_ROTATION_INTERVAL
        self.keys: Dict[str, Dict[str, Any]] = {}
    
    def generate_api_key(self, service: str, expires_in: Optional[int] = None) -> str:
        """API 키 생성"""
        if not expires_in:
            expires_in = self.rotation_interval
        
        # 랜덤 키 생성
        key = secrets.token_urlsafe(32)
        
        # 키 정보 저장
        self.keys[service] = {
            "key": key,
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(seconds=expires_in),
            "is_active": True
        }
        
        logger.info(f"API key generated for {service}")
        return key
    
    def validate_api_key(self, service: str, key: str) -> bool:
        """API 키 검증"""
        if service not in self.keys:
            return False
        
        key_info = self.keys[service]
        
        # 키 일치 확인
        if not hmac.compare_digest(key_info["key"], key):
            return False
        
        # 만료 확인
        if datetime.now() > key_info["expires_at"]:
            key_info["is_active"] = False
            logger.warning(f"API key expired for {service}")
            return False
        
        return key_info["is_active"]
    
    def rotate_api_key(self, service: str) -> str:
        """API 키 로테이션"""
        # 새 키 생성
        new_key = self.generate_api_key(service)
        
        # 기존 키 비활성화 (점진적 전환을 위해)
        if service in self.keys:
            self.keys[service]["is_active"] = False
        
        logger.info(f"API key rotated for {service}")
        return new_key
    
    def get_key_info(self, service: str) -> Optional[Dict[str, Any]]:
        """키 정보 조회"""
        if service not in self.keys:
            return None
        
        key_info = self.keys[service].copy()
        key_info["key"] = "***"  # 보안을 위해 키는 숨김
        return key_info
    
    def cleanup_expired_keys(self):
        """만료된 키 정리"""
        current_time = datetime.now()
        expired_services = []
        
        for service, key_info in self.keys.items():
            if current_time > key_info["expires_at"]:
                expired_services.append(service)
        
        for service in expired_services:
            del self.keys[service]
            logger.info(f"Expired API key removed for {service}")


class AccessControl:
    """접근 제어"""
    
    def __init__(self):
        self.max_login_attempts = settings.MAX_LOGIN_ATTEMPTS
        self.lockout_duration = settings.LOGIN_LOCKOUT_DURATION
        self.failed_attempts: Dict[str, Dict[str, Any]] = {}
    
    def record_failed_attempt(self, identifier: str):
        """실패한 로그인 시도 기록"""
        if identifier not in self.failed_attempts:
            self.failed_attempts[identifier] = {
                "count": 0,
                "first_attempt": datetime.now(),
                "last_attempt": datetime.now()
            }
        
        self.failed_attempts[identifier]["count"] += 1
        self.failed_attempts[identifier]["last_attempt"] = datetime.now()
        
        logger.warning(f"Failed login attempt for {identifier}: {self.failed_attempts[identifier]['count']}")
    
    def record_successful_attempt(self, identifier: str):
        """성공한 로그인 시도 기록"""
        if identifier in self.failed_attempts:
            del self.failed_attempts[identifier]
            logger.info(f"Successful login for {identifier}, resetting failed attempts")
    
    def is_locked_out(self, identifier: str) -> bool:
        """계정 잠금 여부 확인"""
        if identifier not in self.failed_attempts:
            return False
        
        attempt_info = self.failed_attempts[identifier]
        
        # 최대 시도 횟수 초과 확인
        if attempt_info["count"] >= self.max_login_attempts:
            # 잠금 시간 확인
            lockout_end = attempt_info["last_attempt"] + timedelta(seconds=self.lockout_duration)
            
            if datetime.now() < lockout_end:
                remaining_time = (lockout_end - datetime.now()).total_seconds()
                logger.warning(f"Account {identifier} is locked out for {remaining_time:.0f} more seconds")
                return True
            else:
                # 잠금 시간이 지났으면 초기화
                del self.failed_attempts[identifier]
                return False
        
        return False
    
    def get_remaining_attempts(self, identifier: str) -> int:
        """남은 시도 횟수 조회"""
        if identifier not in self.failed_attempts:
            return self.max_login_attempts
        
        return max(0, self.max_login_attempts - self.failed_attempts[identifier]["count"])
    
    def cleanup_old_attempts(self):
        """오래된 시도 기록 정리"""
        current_time = datetime.now()
        expired_identifiers = []
        
        for identifier, attempt_info in self.failed_attempts.items():
            # 잠금 시간이 지난 기록 정리
            lockout_end = attempt_info["last_attempt"] + timedelta(seconds=self.lockout_duration)
            if current_time > lockout_end:
                expired_identifiers.append(identifier)
        
        for identifier in expired_identifiers:
            del self.failed_attempts[identifier]


# 전역 인스턴스들
encryption_manager = EncryptionManager()
api_key_manager = APIKeyManager()
access_control = AccessControl()


# 편의 함수들
def encrypt_sensitive_data(data: str) -> str:
    """민감한 데이터 암호화"""
    return encryption_manager.encrypt(data)


def decrypt_sensitive_data(encrypted_data: str) -> str:
    """암호화된 데이터 복호화"""
    return encryption_manager.decrypt(encrypted_data)


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """비밀번호 해싱"""
    return encryption_manager.hash_password(password, salt)


def verify_password(password: str, hashed_password: str, salt: str) -> bool:
    """비밀번호 검증"""
    return encryption_manager.verify_password(password, hashed_password, salt)


def generate_api_key(service: str, expires_in: Optional[int] = None) -> str:
    """API 키 생성"""
    return api_key_manager.generate_api_key(service, expires_in)


def validate_api_key(service: str, key: str) -> bool:
    """API 키 검증"""
    return api_key_manager.validate_api_key(service, key)


def is_account_locked(identifier: str) -> bool:
    """계정 잠금 여부 확인"""
    return access_control.is_locked_out(identifier)


def record_login_failure(identifier: str):
    """로그인 실패 기록"""
    access_control.record_failed_attempt(identifier)


def record_login_success(identifier: str):
    """로그인 성공 기록"""
    access_control.record_successful_attempt(identifier)
