"""
Digital Signature for Reports
Provides cryptographic signing of evidence reports for authenticity verification
"""
import hashlib
import json
from pathlib import Path
from typing import Optional
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
import base64


class DigitalSigner:
    """Digital signature generator for evidence reports"""
    
    def __init__(self, private_key_path: Path = None, public_key_path: Path = None):
        self.private_key_path = private_key_path or Path("private_key.pem")
        self.public_key_path = public_key_path or Path("public_key.pem")
        self._private_key = None
        self._public_key = None
        
        # Load or generate keys
        self._load_or_generate_keys()
    
    def _load_or_generate_keys(self) -> None:
        """Load existing keys or generate new ones"""
        if self.private_key_path.exists() and self.public_key_path.exists():
            # Load existing keys
            with open(self.private_key_path, "rb") as f:
                self._private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend()
                )
            with open(self.public_key_path, "rb") as f:
                self._public_key = serialization.load_pem_public_key(
                    f.read(),
                    backend=default_backend()
                )
        else:
            # Generate new keys
            self._private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            self._public_key = self._private_key.public_key()
            
            # Save keys
            self._save_keys()
    
    def _save_keys(self) -> None:
        """Save keys to files"""
        private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        public_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        with open(self.private_key_path, "wb") as f:
            f.write(private_pem)
        
        with open(self.public_key_path, "wb") as f:
            f.write(public_pem)
    
    def sign_data(self, data: bytes) -> str:
        """Sign data and return base64 encoded signature"""
        signature = self._private_key.sign(
            data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode()
    
    def sign_file(self, file_path: Path) -> str:
        """Sign a file and return signature"""
        with open(file_path, "rb") as f:
            data = f.read()
        return self.sign_data(data)
    
    def sign_json(self, data: dict) -> str:
        """Sign JSON data (canonicalized)"""
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return self.sign_data(json_str.encode())
    
    def verify_data(self, data: bytes, signature: str) -> bool:
        """Verify data signature"""
        try:
            sig_bytes = base64.b64decode(signature.encode())
            self._public_key.verify(
                sig_bytes,
                data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except Exception:
            return False
    
    def verify_file(self, file_path: Path, signature: str) -> bool:
        """Verify file signature"""
        with open(file_path, "rb") as f:
            data = f.read()
        return self.verify_data(data, signature)
    
    def verify_json(self, data: dict, signature: str) -> bool:
        """Verify JSON data signature"""
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return self.verify_data(json_str.encode(), signature)
    
    def get_public_key_pem(self) -> str:
        """Get public key as PEM string"""
        pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem.decode()
