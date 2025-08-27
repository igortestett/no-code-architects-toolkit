# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

from flask import Flask, request, send_file, abort, jsonify, send_from_directory
from queue import Queue
from services.webhook import send_webhook
import threading
import uuid
import os
import time
import logging
from version import BUILD_NUMBER  # Import the BUILD_NUMBER
from app_utils import log_job_status, discover_and_register_blueprints  # Import the discover_and_register_blueprints function

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_QUEUE_LENGTH = int(os.environ.get('MAX_QUEUE_LENGTH', 0))

def create_app():
    app = Flask(__name__)
    
    # Create a queue to hold tasks
    task_queue = Queue()
    queue_id = id(task_queue)  # Generate a single queue_id for this worker
    
    # Function to process tasks from the queue
    def process_queue():
        while True:
            job_id, data, task_func, queue_start_time = task_queue.get()
            queue_time = time.time() - queue_start_time
            run_start_time = time.time()
            pid = os.getpid()  # Get the PID of the actual processing thread
            
            # Log job status as running
            log_job_status(job_id, {
                "job_status": "running",
                "job_id": job_id,
                "queue_id": queue_id,
                "process_id": pid,
                "response": None
            })
            
            response = task_func()
            run_time = time.time() - run_start_time
            total_time = time.time() - queue_start_time
            response_data = {
                "endpoint": response[1],
                "code": response[2],
                "id": data.get("id"),
                "job_id": job_id,
                "response": response[0] if response[2] == 200 else None,
                "message": "success" if response[2] == 200 else response[0],
                "pid": pid,
                "queue_id": queue_id,
                "run_time": round(run_time, 3),
                "queue_time": round(queue_time, 3),
                "total_time": round(total_time, 3),
                "queue_length": task_queue.qsize(),
                "build_number": BUILD_NUMBER  # Add build number to response
            }
            
            # Log job status as done
            log_job_status(job_id, {
                "job_status": "done",
                "job_id": job_id,
                "queue_id": queue_id,
                "process_id": pid,
                "response": response_data
            })
            # Only send webhook if webhook_url has an actual value (not an empty string)
            if data.get("webhook_url") and data.get("webhook_url") != "":
                send_webhook(data.get("webhook_url"), response_data)
            task_queue.task_done()
    
    # Start the queue processing in a separate thread
    threading.Thread(target=process_queue, daemon=True).start()
    
    # Decorator to add tasks to the queue or bypass it
    def queue_task(bypass_queue=False):
        def decorator(f):
            def wrapper(*args, **kwargs):
                job_id = str(uuid.uuid4())
                data = request.json if request.is_json else {}
                pid = os.getpid()  # Get PID for non-queued tasks
                start_time = time.time()
                
                if bypass_queue or 'webhook_url' not in data:
                    
                    # Log job status as running immediately (bypassing queue)
                    log_job_status(job_id, {
                        "job_status": "running",
                        "job_id": job_id,
                        "queue_id": queue_id,
                        "process_id": pid,
                        "response": None
                    })
                    
                    response = f(job_id=job_id, data=data, *args, **kwargs)
                    run_time = time.time() - start_time
                    
                    response_obj = {
                        "code": response[2],
                        "id": data.get("id"),
                        "job_id": job_id,
                        "response": response[0] if response[2] == 200 else None,
                        "message": "success" if response[2] == 200 else response[0],
                        "run_time": round(run_time, 3),
                        "queue_time": 0,
                        "total_time": round(run_time, 3),
                        "pid": pid,
                        "queue_id": queue_id,
                        "queue_length": task_queue.qsize(),
                        "build_number": BUILD_NUMBER  # Add build number to response
                    }
                    
                    # Log job status as done
                    log_job_status(job_id, {
                        "job_status": "done",
                        "job_id": job_id,
                        "queue_id": queue_id,
                        "process_id": pid,
                        "response": response_obj
                    })
                    
                    return response_obj, response[2]
                else:
                    if MAX_QUEUE_LENGTH > 0 and task_queue.qsize() >= MAX_QUEUE_LENGTH:
                        error_response = {
                            "code": 429,
                            "id": data.get("id"),
                            "job_id": job_id,
                            "message": f"MAX_QUEUE_LENGTH ({MAX_QUEUE_LENGTH}) reached",
                            "pid": pid,
                            "queue_id": queue_id,
                            "queue_length": task_queue.qsize(),
                            "build_number": BUILD_NUMBER  # Add build number to response
                        }
                        
                        # Log the queue overflow error
                        log_job_status(job_id, {
                            "job_status": "done",
                            "job_id": job_id,
                            "queue_id": queue_id,
                            "process_id": pid,
                            "response": error_response
                        })
                        
                        return error_response, 429
                    
                    # Log job status as queued
                    log_job_status(job_id, {
                        "job_status": "queued",
                        "job_id": job_id,
                        "queue_id": queue_id,
                        "process_id": pid,
                        "response": None
                    })
                    
                    task_queue.put((job_id, data, lambda: f(job_id=job_id, data=data, *args, **kwargs), start_time))
                    
                    return {
                        "code": 202,
                        "id": data.get("id"),
                        "job_id": job_id,
                        "message": "processing",
                        "pid": pid,
                        "queue_id": queue_id,
                        "max_queue_length": MAX_QUEUE_LENGTH if MAX_QUEUE_LENGTH > 0 else "unlimited",
                        "queue_length": task_queue.qsize(),
                        "build_number": BUILD_NUMBER  # Add build number to response
                    }, 202
            return wrapper
        return decorator
    
    app.queue_task = queue_task
    
    # ==============================
    # ENDPOINTS DE DOWNLOAD - NOVO
    # ==============================
    
    @app.route('/download/<filename>')
    def download_file(filename):
        """
        Endpoint para download dos arquivos gerados (força download)
        """
        file_path = os.path.join('/tmp', filename)
        
        # Verificar se o arquivo existe
        if not os.path.exists(file_path):
            logger.error(f"File not found for download: {file_path}")
            abort(404)
        
        try:
            logger.info(f"Serving file for download: {filename}")
            return send_file(file_path, as_attachment=True, download_name=filename)
        except Exception as e:
            logger.error(f"Error serving file {filename} for download: {str(e)}")
            abort(500)

    @app.route('/files/<filename>')
    def serve_file(filename):
        """
        Endpoint para servir arquivos diretamente (abre no navegador)
        """
        file_path = os.path.join('/tmp', filename)
        
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            abort(404)
        
        try:
            logger.info(f"Serving file: {filename}")
            return send_file(file_path)
        except Exception as e:
            logger.error(f"Error serving file {filename}: {str(e)}")
            abort(500)

    @app.route('/files')
    def list_files():
        """
        Endpoint para listar arquivos disponíveis para download
        """
        try:
            # Filtrar apenas arquivos de mídia
            media_extensions = ('.mp4', '.avi', '.mov', '.jpg', '.jpeg', '.png', '.gif', '.mp3', '.wav', '.m4a', '.pdf')
            files = [f for f in os.listdir('/tmp') if f.lower().endswith(media_extensions)]
            
            base_url = request.url_root.rstrip('/')
            
            file_list = []
            for filename in files:
                file_path = os.path.join('/tmp', filename)
                try:
                    file_size = os.path.getsize(file_path)
                    file_info = {
                        'filename': filename,
                        'download_url': f"{base_url}/download/{filename}",
                        'view_url': f"{base_url}/files/{filename}",
                        'size': file_size,
                        'size_mb': round(file_size / 1024 / 1024, 2)
                    }
                    file_list.append(file_info)
                except OSError:
                    # Skip files that can't be accessed
                    continue
            
            # Ordenar por nome do arquivo
            file_list.sort(key=lambda x: x['filename'])
            
            return jsonify({
                'status': 'success',
                'files': file_list,
                'total': len(file_list)
            })
        except Exception as e:
            logger.error(f"Error listing files: {str(e)}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/cleanup')
    def cleanup_files():
        """
        Endpoint para limpeza de arquivos antigos (opcional)
        """
        try:
            deleted_count = 0
            current_time = time.time()
            # Deletar arquivos com mais de 1 hora
            max_age = 3600  # 1 hora em segundos
            
            for filename in os.listdir('/tmp'):
                if filename.lower().endswith(('.mp4', '.avi', '.mov', '.jpg', '.jpeg', '.png', '.gif', '.mp3', '.wav', '.m4a')):
                    file_path = os.path.join('/tmp', filename)
                    try:
                        file_age = current_time - os.path.getmtime(file_path)
                        if file_age > max_age:
                            os.remove(file_path)
                            deleted_count += 1
                            logger.info(f"Deleted old file: {filename}")
                    except OSError:
                        continue
            
            return jsonify({
                'status': 'success',
                'deleted_files': deleted_count,
                'message': f'Deleted {deleted_count} old files'
            })
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # ==============================
    # FIM DOS ENDPOINTS DE DOWNLOAD
    # ==============================
    
    # Register special route for Next.js root asset paths first
    from routes.v1.media.feedback import create_root_next_routes
    create_root_next_routes(app)
    
    # Use the discover_and_register_blueprints function to register all blueprints
    discover_and_register_blueprints(app)
    
    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
