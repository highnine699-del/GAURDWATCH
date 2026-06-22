"""
Cryptographic Hashing for Evidence Integrity Verification
Provides SHA256 hashing for all evidence files
"""
import hashlib
from pathlib import Path
from typing import Dict, Optional
import json


class EvidenceHasher:
    """Manages SHA256 hashes for evidence integrity verification"""
    
    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.hashes_file = session_dir / "evidence_hashes.json"
        self._hashes: Dict[str, str] = {}
        self._load_hashes()
    
    def _load_hashes(self) -> None:
        """Load existing hashes from file"""
        if self.hashes_file.exists():
            try:
                with open(self.hashes_file, 'r', encoding='utf-8') as f:
                    self._hashes = json.load(f)
            except Exception:
                self._hashes = {}
    
    def _save_hashes(self) -> None:
        """Save hashes to file"""
        try:
            with open(self.hashes_file, 'w', encoding='utf-8') as f:
                json.dump(self._hashes, f, indent=2)
        except Exception as e:
            print(f"[Hasher] Failed to save hashes: {e}")
    
    def hash_file(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file"""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            print(f"[Hasher] Failed to hash file {file_path}: {e}")
            return ""
    
    def register_file(self, file_path: Path) -> str:
        """Register a file and store its hash"""
        relative_path = file_path.relative_to(self.session_dir)
        file_hash = self.hash_file(file_path)
        
        if file_hash:
            self._hashes[str(relative_path)] = file_hash
            self._save_hashes()
        
        return file_hash
    
    def verify_file(self, file_path: Path) -> bool:
        """Verify a file's integrity against stored hash"""
        relative_path = file_path.relative_to(self.session_dir)
        stored_hash = self._hashes.get(str(relative_path))
        
        if not stored_hash:
            return False  # File not registered
        
        current_hash = self.hash_file(file_path)
        return current_hash == stored_hash
    
    def verify_all(self) -> Dict[str, bool]:
        """Verify all registered files"""
        results = {}
        for relative_path, stored_hash in self._hashes.items():
            file_path = self.session_dir / relative_path
            if file_path.exists():
                results[str(relative_path)] = self.verify_file(file_path)
            else:
                results[str(relative_path)] = False  # File missing
        
        return results
    
    def get_hash(self, file_path: Path) -> Optional[str]:
        """Get stored hash for a file"""
        relative_path = file_path.relative_to(self.session_dir)
        return self._hashes.get(str(relative_path))
    
    def remove_hash(self, file_path: Path) -> None:
        """Remove hash for a file"""
        relative_path = file_path.relative_to(self.session_dir)
        if str(relative_path) in self._hashes:
            del self._hashes[str(relative_path)]
            self._save_hashes()
    
    def generate_integrity_report(self) -> str:
        """Generate integrity verification report"""
        results = self.verify_all()
        
        report = ["Evidence Integrity Report", "=" * 50, ""]
        
        total = len(results)
        valid = sum(1 for v in results.values() if v)
        invalid = total - valid
        
        report.append(f"Total files: {total}")
        report.append(f"Valid: {valid}")
        report.append(f"Invalid/Missing: {invalid}")
        report.append("")
        
        if invalid > 0:
            report.append("Invalid or missing files:")
            for path, is_valid in results.items():
                if not is_valid:
                    report.append(f"  ✗ {path}")
        
        return "\n".join(report)
