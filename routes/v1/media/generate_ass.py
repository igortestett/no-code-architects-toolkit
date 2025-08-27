from flask import Blueprint, jsonify, request
from app_utils import validate_payload, queue_task_wrapper
import logging
from services.ass_toolkit import generate_ass_captions_v1
from services.authentication import authenticate
from services.cloud_storage import upload_file
import os
import requests
import shutil  # NOVO: para copiar arquivos
v1_media_generate_ass_bp = Blueprint('v1_media_generate_ass', __name__)
logger = logging.getLogger(__name__)

@v1_media_generate_ass_bp.route('/v1/media/generate/ass', methods=['POST'])
@authenticate
@validate_payload({
    # ... [deixe o schema do payload igual ao seu acima] ...
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
    download_direct = data.get('download_direct', True)

    logger.info(f"Job {job_id}: Received ASS generation request for {media_url}")

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

        if isinstance(output, dict) and 'error' in output:
            if 'available_fonts' in output:
                return ({"error": output['error'], "available_fonts": output['available_fonts']}, '/v1/media/generate/ass', 400)
            else:
                return ({"error": output['error']}, '/v1/media/generate/ass', 400)

        ass_path = output
        logger.info(f"Job {job_id}: ASS file generated at {ass_path}")

        if not os.path.exists(ass_path):
            logger.error(f"Job {job_id}: Generated file does not exist at {ass_path}")
            return ({"error": "Failed to generate ASS file - file not found"}, '/v1/media/generate/ass', 500)

        file_size = os.path.getsize(ass_path)
        logger.info(f"Job {job_id}: Generated file size: {file_size} bytes")
        if file_size == 0:
            logger.error(f"Job {job_id}: Generated file is empty")
            return ({"error": "Generated ASS file is empty"}, '/v1/media/generate/ass', 500)

        # Gera nome de arquivo único
        filename = f"captions_{id or job_id}.ass"
        final_path = f"/tmp/{filename}"
        shutil.copy2(ass_path, final_path)  # Garantir que está na pasta /tmp com o nome correto
        logger.info(f"Job {job_id}: Copied ASS file to {final_path}")

        # Sempre retorna um dicionário com a URL de download para ser usado pelo cliente (não send_file !)
        download_url = f"/download/{filename}"

        # Por padrão (download_direct = True), retorna só a URL que pluga no endpoint de download
        response_data = {
            "success": True,
            "download_url": download_url,
            "file_type": "ass",
            "job_id": job_id,
            "file_size": file_size,
            "filename": filename,
            "message": "ASS file generated successfully"
        }

        # Se webhook_url fornecido, envia notificação
        if webhook_url:
            try:
                webhook_payload = {
                    "job_id": job_id,
                    "status": "completed",
                    "download_url": download_url,
                    "file_type": "ass"
                }
                requests.post(webhook_url, json=webhook_payload, timeout=10)
                logger.info(f"Job {job_id}: Webhook notification sent to {webhook_url}")
            except Exception as webhook_error:
                logger.warning(f"Job {job_id}: Failed to send webhook notification - {str(webhook_error)}")

        return (response_data, '/v1/media/generate/ass', 200)

    except Exception as e:
        logger.error(f"Job {job_id}: Error during ASS generation process - {str(e)}", exc_info=True)
        return ({"error": str(e)}, '/v1/media/generate/ass', 500)

