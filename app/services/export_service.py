"""
Export Service for handling data exports.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging
import json
import zipfile
import io

logger = logging.getLogger(__name__)


class ExportService:
    """Service for handling data exports."""
    
    def __init__(self):
        """Initialize the export service."""
        self.export_formats = ['json', 'markdown', 'zip']
    
    def export_room_data(self, room_id: str, format: str = 'json') -> Dict[str, Any]:
        """Export room data in specified format."""
        if format not in self.export_formats:
            raise ValueError(f"Unsupported export format: {format}")
        
        # Mock room data for testing
        room_data = {
            "room_id": room_id,
            "name": f"Test Room {room_id}",
            "type": "main",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "messages": [],
            "memory": []
        }
        
        if format == 'json':
            return room_data
        elif format == 'markdown':
            return self._convert_to_markdown(room_data)
        elif format == 'zip':
            return self._create_zip_export(room_data)
    
    def _convert_to_markdown(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert data to markdown format."""
        markdown_content = f"""# {data['name']}
        
**Room ID:** {data['room_id']}
**Type:** {data['type']}
**Created:** {data['created_at']}

## Messages
{len(data['messages'])} messages

## Memory
{len(data['memory'])} memory entries
"""
        
        return {
            "content": markdown_content,
            "filename": f"room_{data['room_id']}.md"
        }
    
    def _create_zip_export(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a zip file export."""
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add JSON file
            zip_file.writestr(f"room_{data['room_id']}.json", json.dumps(data, indent=2))
            
            # Add markdown file
            markdown_data = self._convert_to_markdown(data)
            zip_file.writestr(markdown_data['filename'], markdown_data['content'])
        
        zip_buffer.seek(0)
        
        return {
            "content": zip_buffer.getvalue(),
            "filename": f"room_{data['room_id']}_export.zip"
        }
    
    def get_export_status(self, export_id: str) -> Dict[str, Any]:
        """Get export status."""
        return {
            "export_id": export_id,
            "status": "completed",
            "created_at": datetime.now(timezone.utc).isoformat()
        }


# Global service instance
export_service: Optional[ExportService] = None


def get_export_service() -> ExportService:
    """Get the global export service instance."""
    global export_service
    if export_service is None:
        export_service = ExportService()
    return export_service

