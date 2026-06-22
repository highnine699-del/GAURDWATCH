"""
Report Generator with Multiple Export Formats
Supports PDF, HTML, JSON, CSV, ZIP exports with digital signatures
"""
import json
import csv
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from database import EvidenceDatabase
from hashing import EvidenceHasher
from digital_signature import DigitalSigner
from config import config


class ReportGenerator:
    """Generates evidence reports in multiple formats"""
    
    def __init__(self, db: EvidenceDatabase, session_dir: Path, session_id: str):
        self.db = db
        self.session_dir = session_dir
        self.session_id = session_id
        self.hasher = EvidenceHasher(session_dir)
        self.signer = DigitalSigner()
    
    def generate_html_report(self) -> Path:
        """Generate HTML evidence report"""
        events = self.db.get_events(session_id=self.session_id, limit=500)
        stats = self.db.get_session_stats(self.session_id)
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>GuardWatch Evidence Report — {self.session_id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .header {{ background: #1a1a2e; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .stat-card {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #e94560; }}
        .stat-label {{ color: #666; font-size: 12px; }}
        .event {{ background: white; padding: 15px; margin-bottom: 10px; border-radius: 8px; border-left: 4px solid #ddd; }}
        .event.HIGH {{ border-left-color: #e94560; background: #fff5f5; }}
        .event-time {{ color: #888; font-size: 12px; }}
        .event-type {{ font-weight: bold; color: #333; }}
        .event-detail {{ margin-top: 5px; color: #555; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🛡️ GuardWatch Evidence Report</h1>
        <p>Session: {self.session_id}</p>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="stats">
        <div class="stat-card">
            <div class="stat-value">{stats.get('total_events', 0)}</div>
            <div class="stat-label">Total Events</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{stats.get('high_priority_events', 0)}</div>
            <div class="stat-label">High Priority</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{stats.get('duration_secs', 0) // 60}</div>
            <div class="stat-label">Duration (minutes)</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{stats.get('file_counts', {}).get('webcam', 0)}</div>
            <div class="stat-label">Webcam Photos</div>
        </div>
    </div>
    
    <h2>Event Log</h2>
"""
        
        for event in events:
            html += f"""
    <div class="event {event.get('priority', 'INFO')}">
        <div class="event-time">{event.get('timestamp', '')}</div>
        <div class="event-type">{event.get('event_type', '')}</div>
        <div class="event-detail">{event.get('detail', '')}</div>
    </div>
"""
        
        html += """
</body>
</html>
"""
        
        output_path = self.session_dir / "evidence_report.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        return output_path
    
    def generate_json_report(self) -> Path:
        """Generate JSON evidence report"""
        events = self.db.get_events(session_id=self.session_id, limit=1000)
        stats = self.db.get_session_stats(self.session_id)
        
        report = {
            "session_id": self.session_id,
            "generated_at": datetime.now().isoformat(),
            "statistics": stats,
            "events": events,
            "integrity": self.hasher.generate_integrity_report()
        }
        
        # Add digital signature if enabled
        if config.storage.get("sign_reports", False):
            signature = self.signer.sign_json(report)
            report["digital_signature"] = signature
            report["public_key"] = self.signer.get_public_key_pem()
        
        output_path = self.session_dir / "evidence_report.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # Sign the file itself
        if config.storage.get("sign_reports", False):
            signature = self.signer.sign_file(output_path)
            sig_path = self.session_dir / "evidence_report.json.sig"
            with open(sig_path, 'w') as f:
                f.write(signature)
        
        return output_path
    
    def generate_csv_report(self) -> Path:
        """Generate CSV evidence report"""
        events = self.db.get_events(session_id=self.session_id, limit=1000)
        
        output_path = self.session_dir / "evidence_report.csv"
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Event Type', 'Priority', 'Detail', 'Source'])
            
            for event in events:
                writer.writerow([
                    event.get('timestamp', ''),
                    event.get('event_type', ''),
                    event.get('priority', ''),
                    event.get('detail', ''),
                    event.get('source', '')
                ])
        
        return output_path
    
    def generate_zip_export(self) -> Path:
        """Generate ZIP archive of all evidence"""
        output_path = self.session_dir.parent / f"{self.session_id}_evidence.zip"
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in self.session_dir.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(self.session_dir.parent)
                    zipf.write(file_path, arcname)
        
        return output_path
    
    def generate_pdf_report(self) -> Path:
        """Generate PDF evidence report (requires weasyprint)"""
        try:
            from weasyprint import HTML
            
            html_path = self.generate_html_report()
            pdf_path = self.session_dir / "evidence_report.pdf"
            
            HTML(filename=str(html_path)).write_pdf(str(pdf_path))
            
            return pdf_path
        except ImportError:
            print("[Report] weasyprint not installed, PDF generation skipped")
            return None
        except Exception as e:
            print(f"[Report] PDF generation failed: {e}")
            return None
    
    def generate_session_summary(self) -> Dict:
        """Generate session summary for shutdown"""
        stats = self.db.get_session_stats(self.session_id)
        high_priority = self.db.get_high_priority_events(self.session_id, limit=100)
        
        # Calculate risk level
        risk_score = stats.get('high_priority_events', 0)
        if risk_score >= 5:
            risk_level = "CRITICAL"
        elif risk_score >= 3:
            risk_level = "HIGH"
        elif risk_score >= 1:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
        
        return {
            "session_id": self.session_id,
            "start_time": stats.get('start_time', ''),
            "end_time": stats.get('end_time', ''),
            "duration_minutes": stats.get('duration_secs', 0) // 60,
            "total_events": stats.get('total_events', 0),
            "high_priority_events": stats.get('high_priority_events', 0),
            "file_counts": stats.get('file_counts', {}),
            "risk_level": risk_level,
            "top_events": high_priority[:10]
        }
    
    def export(self, format_type: str) -> Path:
        """Export evidence in specified format"""
        format_type = format_type.lower()
        
        if format_type == 'html':
            return self.generate_html_report()
        elif format_type == 'json':
            return self.generate_json_report()
        elif format_type == 'csv':
            return self.generate_csv_report()
        elif format_type == 'zip':
            return self.generate_zip_export()
        elif format_type == 'pdf':
            return self.generate_pdf_report()
        else:
            raise ValueError(f"Unsupported format: {format_type}")
