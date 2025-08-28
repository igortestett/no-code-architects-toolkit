# Copyright (c) 2025 Stephen G. Pope
from flask import Blueprint, request
from app_utils import *
import logging
import shutil
from services.caption_video import process_captioning
from services.authentication import authenticate
import os

caption_bp = Blueprint('caption', __name__)
logger = logging.getLogger(__name__)

@caption_bp.route('/caption-video', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "video_url": {"type": "string", "format": "uri"},
        "srt": {"type": "string"},
        "ass": {"type": "string"},
        "options": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "option": {"type": "string"},
                    "value": {}  # Allow any type for value
                },
                "required": ["option", "value"]
            }
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["video_url"],
    "oneOf": [
        {"required": ["srt"]},
        {"required": ["ass"]}
    ],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def caption_video(job_id, data):
    video_url = data['video_url']
    caption_srt = data.get('srt')
    caption_ass = data.get('ass')
    options = data.get('options', [])
    webhook_url = data.get('webhook_url')
    id = data.get('id')
    
    logger.info(f"Job {job_id}: Received captioning request for {video_url}")
    logger.info(f"Job {job_id}: Options received: {options}")
    
    if caption_ass is not None:
        captions = caption_ass
        caption_type = "ass"
    else:
        captions = caption_srt
        caption_type = "srt"
    
    try:
        output_filename = process_captioning(video_url, captions, caption_type, options, job_id)
        logger.info(f"Job {job_id}: Captioning process completed successfully")
        
        # Verificar se o arquivo foi gerado
        if not os.path.exists(output_filename):
            logger.error(f"Job {job_id}: Output file not found: {output_filename}")
            return ({"error": "Output file not found"}, "/caption-video", 500)
        
        # Gerar nome final para o arquivo de download
        final_filename = f"{job_id}_captioned.mp4"
        final_path = f"/tmp/{final_filename}"
        
        # Garantir que /tmp existe
        os.makedirs("/tmp", exist_ok=True)
        
        # Mover/copiar arquivo para /tmp com nome correto
        if output_filename != final_path:
            shutil.move(output_filename, final_path)
            logger.info(f"Job {job_id}: Moved file to {final_path}")
        
        # Verificar se o arquivo final existe e não está vazio
        if not os.path.exists(final_path):
            logger.error(f"Job {job_id}: Final file not found: {final_path}")
            return ({"error": "Final file not found"}, "/caption-video", 500)
        
        file_size = os.path.getsize(final_path)
        if file_size == 0:
            logger.error(f"Job {job_id}: Final file is empty")
            return ({"error": "Generated file is empty"}, "/caption-video", 500)
        
        logger.info(f"Job {job_id}: Final file ready: {final_path} ({file_size} bytes)")
        
        # Construir URL completa de download
        base_url = request.url_root.rstrip('/')
        download_url = f"{base_url}/download/{final_filename}"
        
        logger.info(f"Job {job_id}: Generated download URL: {download_url}")
        
        return (download_url, "/caption-video", 200)
        
    except Exception as e:
        logger.error(f"Job {job_id}: Error during captioning process - {str(e)}", exc_info=True)
        return ({"error": str(e)}, "/caption-video", 500)
