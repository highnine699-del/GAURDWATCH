"""
AES Encryption for Sensitive Evidence Files
Provides encryption for keystrokes, clipboard, and other sensitive data
"""
import os
import hashlib
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64


class EvidenceEncryptor:
    """AES encryption for sensitive evidence files"""
    
    def __init__(self, password: str = None):
        self.password = password or self._generate_password()
        self._key = self._derive_key(self.password)
        self._fernet = Fernet(self._key)
    
    def _generate_password(self) -> str:
        """Generate a random password"""
        return os.urandom(32).hex()
    
    def _derive_key(self, password: str) -> bytes:
        """Derive encryption key from password"""
        salt = b'guardwatch_salt'  # In production, use random salt per session
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def encrypt(self, data: bytes) -> bytes:
        """Encrypt data"""
        return self._fernet.encrypt(data)
    
    def decrypt(self, encrypted_data: bytes) -> bytes:
        """Decrypt data"""
        return self._fernet.decrypt(encrypted_data)
    
    def encrypt_file(self, file_path: Path) -> Path:
        """Encrypt a file and save with .enc extension"""
        encrypted_path = file_path.with_suffix(file_path.suffix + '.enc')
        
        with open(file_path, 'rb') as f:
            data = f.read()
        
        encrypted_data = self.encrypt(data)
        
        with open(encrypted_path, 'wb') as f:
            f.write(encrypted_data)
        
        return encrypted_path
    
    def decrypt_file(self, encrypted_path: Path, output_path: Path = None) -> Path:
        """Decrypt a file"""
        if output_path is None:
            # Remove .enc extension
            output_path = encrypted_path.with_suffix('')
            if output_path.suffix == '.enc':
                output_path = encrypted_path.with_suffix('')
        
        with open(encrypted_path, 'rb') as f:
            encrypted_data = f.read()
        
        decrypted_data = self.decrypt(encrypted_data)
        
        with open(output_path, 'wb') as f:
            f.write(decrypted_data)
        
        return output_path
    
    def encrypt_string(self, text: str) -> str:
        """Encrypt a string and return base64 encoded result"""
        encrypted = self.encrypt(text.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def decrypt_string(self, encrypted_text: str) -> str:
        """Decrypt a base64 encoded string"""
        encrypted = base64.urlsafe_b64decode(encrypted_text.encode())
        decrypted = self.decrypt(encrypted)
        return decrypted.decode()
