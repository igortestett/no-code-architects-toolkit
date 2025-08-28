from flask import Blueprint, jsonify, request
from app_utils import validate_payload, queue_task_wrapper
import logging
from services.ass_toolkit import generate_ass_captions_v1
from services.authentication import authenticate
from services.cloud_storage import upload_file
import os
import requests
import shutil

v1_media_generate_ass_bp = Blueprint('v1_media_generate_ass', __name__)
logger = logging.getLogger(__name__)

@v1_media_generate_ass_bp.route('/v1/media/generate/ass', methods=['POST'])
@authenticate
@validate_payload({
    # ... [seu schema existente] ...
})
@queue_task_wrapper(bypass_queue=False)
def generate_ass_v1(job_id, data):
    # ... [código existente até a parte da resposta] ...
    
    try:
        # ... [processamento existente] ...
        
        # Gera nome de arquivo único
        filename = f"captions_{id or job_id}.ass"
        final_path = f"/tmp/{filename}"
        shutil.copy2(ass_path, final_path)
        
        # ALTERAÇÃO AQUI: Construir URL completa
        base_url = request.url_root.rstrip('/')  # Remove barra final se existir
        download_url = f"{base_url}/download/{filename}"
        
        response_data = {
            "success": True,
            "download_url": download_url,  # Agora será URL completa
            "file_type": "ass",
            "job_id": job_id,
            "file_size": file_size,
            "filename": filename,
            "message": "ASS file generated successfully"
        }
        
        # ... [resto do código igual] ...
        
        return (response_data, '/v1/media/generate/ass', 200)
        
    except Exception as e:
        # ... [tratamento de erro existente] ...
