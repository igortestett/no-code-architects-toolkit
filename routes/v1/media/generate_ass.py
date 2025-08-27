from flask import Blueprint, jsonify, request, send_file
from app_utils import validate_payload, queue_task_wrapper
import logging
from services.ass_toolkit import generate_ass_captions_v1
from services.authentication import authenticate
from services.cloud_storage import upload_file
import os
import requests
import tempfile

v1_media_generate_ass_bp = Blueprint('v1_media_generate_ass', __name__)
logger = logging.getLogger(__name__)

@v1_media_generate_ass_bp.route('/v1/media/generate/ass', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "media_url": {"type": "string", "format": "uri"},
        "canvas_width": {"type": "integer", "minimum": 1},
        "canvas_height": {"type": "integer", "minimum": 1},
        "settings": {
            "type": "object",
            "properties": {
                "line_color": {"type": "string"},
                "word_color": {"type": "string"},
                "outline_color": {"type": "string"},
                "all_caps": {"type": "boolean"},
                "max_words_per_line": {"type": "integer"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "position": {
                    "type": "string",
                    "enum": [
                        "bottom_left", "bottom_center", "bottom_right",
                        "middle_left", "middle_center", "middle_right",
                        "top_left", "top_center", "top_right"
                    ]
                },
                "alignment": {
                    "type": "string",
                    "enum": ["left", "center", "right"]
                },
                "font_family": {"type": "string"},
                "font_size": {"type": "integer"},
                "bold": {"type": "boolean"},
                "italic": {"type": "boolean"},
                "underline": {"type": "boolean"},
                "strikeout": {"type": "boolean"},
                "style": {
                    "type": "string",
                    "enum": ["classic", "karaoke", "highlight", "underline", "word_by_word"]
                },
                "outline_width": {"type": "integer"},
                "spacing": {"type": "integer"},
                "angle": {"type": "integer"},
                "shadow_offset": {"type": "integer"}
            },
            "additionalProperties": False
        },
        "replace": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "find": {"type": "string"},
                    "replace": {"type": "string"}
                },
                "required": ["find", "replace"]
            }
        },
        "exclude_time_ranges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": { "type": "string" },
                    "end": { "type": "string" }
                },
                "required": ["start", "end"],
                "additionalProperties": False
            }
        },
        "language": {"type": "string"},
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"},
        "download_direct": {"type": "boolean"}
    },
    "additionalProperties": False,
    "required": ["media_url"],
    "oneOf": [
        { "required": ["canvas_width", "canvas_height"] },
        { "not": { "anyOf": [ { "required": ["canvas_width"] }, { "required": ["canvas_height"] } ] } }
    ]
})
@queue_task_wrapper(bypass_queue=False)
def generate_ass_v1(job_id, data):
    media_url = data['media_url']
    settings = data.get('settings', {})
    replace = data.get('replace', [])
    exclude_time_ranges = data.get('exclude_time_ranges', [])
    webhook_url = data.get('webhook_url')
    id = data.get('id')
    language = data.get('language', 'auto')
    canvas_width = data.get('canvas_width')
    canvas_height = data.get('canvas_height')
    download_direct = data.get('download_direct', True)  # PADRÃO AGORA É True
    
    logger.info(f"Job {job_id}: Received ASS generation request for {media_url}")
    logger.info(f"Job {job_id}: Settings received: {settings}")
    logger.info(f"Job {job_id}: Replace rules received: {replace}")
    logger.info(f"Job {job_id}: Exclude time ranges received: {exclude_time_ranges}")
    logger.info(f"Job {job_id}: Download direct: {download_direct}")
    
    try:
        output = generate_ass_captions_v1(
            media_url,
            captions=None,
            settings=settings,
            replace=replace,
            exclude_time_ranges=exclude_time_ranges,
            job_id=job_id,
            language=language,
            PlayResX=canvas_width,
            PlayResY=canvas_height
        )
        
        # Tratamento de erros existente
        if isinstance(output, dict) and 'error' in output:
            if 'available_fonts' in output:
                return {"error": output['error'], "available_fonts": output['available_fonts']}, 400
            else:
                return {"error": output['error']}, 400
        
        ass_path = output
        logger.info(f"Job {job_id}: ASS file generated at {ass_path}")
        
        # Verificar se o arquivo foi gerado corretamente
        if not os.path.exists(ass_path):
            logger.error(f"Job {job_id}: Generated file does not exist at {ass_path}")
            return {"error": "Failed to generate ASS file - file not found"}, 500
        
        # Verificar o tamanho do arquivo
        file_size = os.path.getsize(ass_path)
        logger.info(f"Job {job_id}: Generated file size: {file_size} bytes")
        
        if file_size == 0:
            logger.error(f"Job {job_id}: Generated file is empty")
            return {"error": "Generated ASS file is empty"}, 500
        
        # COMPORTAMENTO PADRÃO: Download direto (download_direct = True por padrão)
        if download_direct:
            try:
                # Gerar nome do arquivo baseado no job_id ou id fornecido
                filename = f"captions_{id or job_id}.ass"
                
                logger.info(f"Job {job_id}: Sending file directly for download as {filename}")
                
                # Retornar o arquivo para download
                return send_file(
                    ass_path,
                    as_attachment=True,
                    download_name=filename,
                    mimetype='text/plain'
                )
                
            except Exception as e:
                logger.error(f"Job {job_id}: Error sending file for download - {str(e)}")
                # Se falhar o download direto, continuar com upload para cloud
                pass
        
        # Fallback: upload para cloud storage (apenas se download_direct = False ou falhar)
        try:
            cloud_url = upload_file(ass_path)
            logger.info(f"Job {job_id}: ASS file uploaded to cloud storage: {cloud_url}")
            
            # Limpar arquivo local
            os.remove(ass_path)
            logger.info(f"Job {job_id}: Cleaned up local ASS file")
            
            # Retornar resposta estruturada com informações do arquivo
            response_data = {
                "success": True,
                "download_url": cloud_url,
                "file_type": "ass",
                "job_id": job_id,
                "file_size": file_size,
                "message": "ASS file generated successfully"
            }
            
            # Se webhook_url fornecido, enviar notificação (opcional)
            if webhook_url:
                try:
                    webhook_payload = {
                        "job_id": job_id,
                        "status": "completed",
                        "download_url": cloud_url,
                        "file_type": "ass"
                    }
                    requests.post(webhook_url, json=webhook_payload, timeout=10)
                    logger.info(f"Job {job_id}: Webhook notification sent to {webhook_url}")
                except Exception as webhook_error:
                    logger.warning(f"Job {job_id}: Failed to send webhook notification - {str(webhook_error)}")
            
            return response_data, 200
            
        except Exception as upload_error:
            logger.error(f"Job {job_id}: Error uploading file to cloud storage - {str(upload_error)}")
            
            # Se o upload falhar, tentar retornar o arquivo diretamente como fallback final
            if os.path.exists(ass_path):
                try:
                    filename = f"captions_{id or job_id}.ass"
                    logger.info(f"Job {job_id}: Cloud upload failed, sending file directly as fallback")
                    
                    return send_file(
                        ass_path,
                        as_attachment=True,
                        download_name=filename,
                        mimetype='text/plain'
                    )
                except Exception as fallback_error:
                    logger.error(f"Job {job_id}: Fallback direct download also failed - {str(fallback_error)}")
                    return {"error": f"Failed to upload file and direct download: {str(fallback_error)}"}, 500
            else:
                return {"error": f"File upload failed and local file no longer exists: {str(upload_error)}"}, 500
        
    except Exception as e:
        logger.error(f"Job {job_id}: Error during ASS generation process - {str(e)}", exc_info=True)
        return {"error": str(e)}, 500
