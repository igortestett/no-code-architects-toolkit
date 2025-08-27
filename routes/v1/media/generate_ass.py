from flask import Blueprint, jsonify, request
from app_utils import validate_payload, queue_task_wrapper
import logging
from services.ass_toolkit import generate_ass_captions_v1
from services.authentication import authenticate
from services.cloud_storage import upload_file
import os
import requests
import time
import tempfile
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import lru_cache
import jsonschema
import hashlib

# Configurações de otimização
os.environ['PYTHONUNBUFFERED'] = '1'  # Flush logs imediatamente
os.environ['MALLOC_TRIM_THRESHOLD'] = '100000'  # Otimize uso de memória

v1_media_generate_ass_bp = Blueprint('v1_media_generate_ass', __name__)
logger = logging.getLogger(__name__)

# Cache do schema compilado para validação mais rápida
@lru_cache(maxsize=1)
def get_compiled_schema():
    schema = {
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
            "id": {"type": "string"}
        },
        "additionalProperties": False,
        "required": ["media_url"],
        "oneOf": [
            { "required": ["canvas_width", "canvas_height"] },
            { "not": { "anyOf": [ { "required": ["canvas_width"] }, { "required": ["canvas_height"] } ] } }
        ]
    }
    return jsonschema.Draft7Validator(schema)

# Classe para otimizações de conexão
class OptimizedAssGenerator:
    def __init__(self):
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        self.cache = {}
    
    def get_cache_key(self, media_url, settings, replace, exclude_time_ranges, language, canvas_width, canvas_height):
        """Gera chave única para cache baseada nos parâmetros"""
        data_str = f"{media_url}{str(settings)}{str(replace)}{str(exclude_time_ranges)}{language}{canvas_width}{canvas_height}"
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    def upload_file_optimized(self, file_path):
        """Upload otimizado usando sessão reutilizada"""
        return upload_file(file_path)

# Instância global reutilizada
ass_generator = OptimizedAssGenerator()

@contextmanager
def timer(operation_name, job_id):
    """Context manager para medir tempo de operações"""
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        logger.info("Job %s: %s took %.2fs", job_id, operation_name, duration)

@contextmanager
def temporary_file_manager(job_id):
    """Context manager para gerenciar arquivo temporário"""
    temp_path = f"/tmp/ass_{job_id}_{int(time.time())}.ass"
    try:
        yield temp_path
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.debug("Job %s: Cleaned up temporary file %s", job_id, temp_path)
            except OSError as e:
                logger.warning("Job %s: Failed to cleanup %s: %s", job_id, temp_path, str(e))

def handle_error_response(output):
    """Centraliza tratamento de erros"""
    if 'available_fonts' in output:
        return {"error": output['error'], "available_fonts": output['available_fonts']}, "/v1/media/generate/ass", 400
    else:
        return {"error": output['error']}, "/v1/media/generate/ass", 400

def validate_payload_fast(data):
    """Validação rápida usando schema compilado"""
    validator = get_compiled_schema()
    try:
        validator.validate(data)
        return True
    except jsonschema.ValidationError as e:
        logger.error("Validation error: %s", str(e))
        return False

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
        "id": {"type": "string"}
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
    """Versão otimizada da geração de ASS com processamento paralelo e cache"""
    
    # Extrair dados com valores padrão
    media_url = data['media_url']
    settings = data.get('settings', {})
    replace = data.get('replace', [])
    exclude_time_ranges = data.get('exclude_time_ranges', [])
    webhook_url = data.get('webhook_url')
    id_param = data.get('id')
    language = data.get('language', 'auto')
    canvas_width = data.get('canvas_width')
    canvas_height = data.get('canvas_height')
    
    # Log otimizado (uma linha com todas as informações principais)
    logger.info(
        "Job %s: ASS generation request - URL: %s, Language: %s, Canvas: %sx%s, Settings count: %d",
        job_id, media_url, language, canvas_width, canvas_height, len(settings)
    )
    
    # Verificar cache se disponível
    cache_key = ass_generator.get_cache_key(
        media_url, settings, replace, exclude_time_ranges, 
        language, canvas_width, canvas_height
    )
    
    if cache_key in ass_generator.cache:
        logger.info("Job %s: Using cached result", job_id)
        return ass_generator.cache[cache_key], "/v1/media/generate/ass", 200
    
    with timer("Total ASS generation", job_id):
        try:
            # Processamento paralelo usando ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=3) as executor:
                
                # Iniciar geração ASS em thread separada
                with timer("ASS file generation", job_id):
                    generation_future = executor.submit(
                        generate_ass_captions_v1,
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
                    
                    # Aguardar resultado da geração
                    output = generation_future.result(timeout=300)  # 5 minutos timeout
                
                # Verificar se houve erro na geração
                if isinstance(output, dict) and 'error' in output:
                    logger.error("Job %s: Generation error: %s", job_id, output['error'])
                    return handle_error_response(output)
                
                ass_path = output
                logger.info("Job %s: ASS file generated at %s", job_id, ass_path)
                
                # Upload paralelo
                with timer("File upload", job_id):
                    upload_future = executor.submit(upload_file, ass_path)
                    cloud_url = upload_future.result(timeout=60)  # 1 minuto timeout para upload
                
                logger.info("Job %s: ASS file uploaded to cloud storage: %s", job_id, cloud_url)
                
                # Cleanup assíncrono (não bloqueia o retorno)
                cleanup_future = executor.submit(safe_file_cleanup, ass_path, job_id)
                
                # Cache do resultado para requisições futuras similares
                ass_generator.cache[cache_key] = cloud_url
                
                # Limitar tamanho do cache (simples LRU)
                if len(ass_generator.cache) > 100:
                    # Remove o primeiro item (mais antigo)
                    oldest_key = next(iter(ass_generator.cache))
                    del ass_generator.cache[oldest_key]
                
                return cloud_url, "/v1/media/generate/ass", 200
                
        except Exception as e:
            logger.error("Job %s: Error during ASS generation process - %s", job_id, str(e), exc_info=True)
            return {"error": str(e)}, "/v1/media/generate/ass", 500

def safe_file_cleanup(file_path, job_id):
    """Cleanup seguro de arquivo com tratamento de erros"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.debug("Job %s: Successfully cleaned up file %s", job_id, file_path)
    except OSError as e:
        logger.warning("Job %s: Failed to cleanup file %s: %s", job_id, file_path, str(e))

# Função opcional para limpeza periódica do cache
def cleanup_cache():
    """Limpa cache periodicamente para evitar uso excessivo de memória"""
    if len(ass_generator.cache) > 50:
        # Manter apenas os 25 mais recentes
        items = list(ass_generator.cache.items())
        ass_generator.cache = dict(items[-25:])
        logger.info("Cache cleaned up, kept %d items", len(ass_generator.cache))

# Adicione ao final do arquivo para monitoramento opcional
def get_performance_stats():
    """Retorna estatísticas de performance para monitoramento"""
    return {
        "cache_size": len(ass_generator.cache),
        "cache_keys": list(ass_generator.cache.keys())[:5]  # Primeiras 5 chaves para debug
    }
