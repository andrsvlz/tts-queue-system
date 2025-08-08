#!/usr/bin/env python3
"""
API REST para sistema de colas TTS con RabbitMQ
"""

from flask import Flask, request, jsonify
import pika
import redis
import json
import uuid
import os
from datetime import datetime
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuración
RABBITMQ_URL = os.getenv('RABBITMQ_URL', 'amqp://tts_user:tts_password_2024@localhost:5672/tts_vhost')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', 5000))

# Conexiones
redis_client = None
rabbitmq_connection = None
rabbitmq_channel = None

def init_connections():
    """Inicializar conexiones a RabbitMQ y Redis"""
    global redis_client, rabbitmq_connection, rabbitmq_channel
    
    try:
        # Conectar a Redis
        redis_client = redis.from_url(REDIS_URL)
        redis_client.ping()
        logger.info("✅ Conectado a Redis")
        
        # Conectar a RabbitMQ
        parameters = pika.URLParameters(RABBITMQ_URL)
        rabbitmq_connection = pika.BlockingConnection(parameters)
        rabbitmq_channel = rabbitmq_connection.channel()
        
        # Declarar colas
        rabbitmq_channel.queue_declare(queue='tts_calls', durable=True)
        rabbitmq_channel.queue_declare(queue='tts_priority', durable=True)
        rabbitmq_channel.queue_declare(queue='tts_results', durable=True)
        
        logger.info("✅ Conectado a RabbitMQ y colas declaradas")
        
    except Exception as e:
        logger.error(f"❌ Error conectando: {e}")
        raise

class TTSQueueManager:
    def __init__(self):
        self.redis = redis_client
        self.channel = rabbitmq_channel
    
    def enqueue_tts_call(self, text, phone_number="3005050149", language="es", priority="normal"):
        """Enviar trabajo TTS a la cola"""
        try:
            # Generar ID único para el trabajo
            job_id = str(uuid.uuid4())
            
            # Crear trabajo
            job_data = {
                'job_id': job_id,
                'text': text,
                'phone_number': phone_number,
                'language': language,
                'priority': priority,
                'created_at': datetime.now().isoformat(),
                'status': 'queued'
            }
            
            # Guardar estado en Redis
            self.redis.setex(f"job:{job_id}", 3600, json.dumps(job_data))
            
            # Enviar a cola apropiada
            queue_name = 'tts_priority' if priority == 'high' else 'tts_calls'
            
            self.channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=json.dumps(job_data),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Hacer mensaje persistente
                    message_id=job_id,
                    timestamp=int(datetime.now().timestamp())
                )
            )
            
            logger.info(f"📤 Trabajo {job_id} enviado a cola {queue_name}")
            return job_data
            
        except Exception as e:
            logger.error(f"❌ Error enviando trabajo: {e}")
            raise
    
    def get_job_status(self, job_id):
        """Obtener estado de un trabajo"""
        try:
            job_data = self.redis.get(f"job:{job_id}")
            if job_data:
                return json.loads(job_data)
            return None
        except Exception as e:
            logger.error(f"❌ Error obteniendo estado: {e}")
            return None
    
    def get_queue_stats(self):
        """Obtener estadísticas de las colas"""
        try:
            stats = {}
            
            # Estadísticas de RabbitMQ
            normal_queue = self.channel.queue_declare(queue='tts_calls', passive=True)
            priority_queue = self.channel.queue_declare(queue='tts_priority', passive=True)
            results_queue = self.channel.queue_declare(queue='tts_results', passive=True)
            
            stats['queues'] = {
                'normal': normal_queue.method.message_count,
                'priority': priority_queue.method.message_count,
                'results': results_queue.method.message_count
            }
            
            # Estadísticas de Redis
            stats['redis'] = {
                'total_jobs': len(self.redis.keys("job:*")),
                'active_workers': len(self.redis.keys("worker:*"))
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo estadísticas: {e}")
            return {}

# Instancia del gestor de colas
queue_manager = None

@app.before_request
def startup():
    """Inicializar al arrancar la aplicación"""
    global queue_manager
    if queue_manager is None:
        init_connections()
        queue_manager = TTSQueueManager()

@app.route('/health', methods=['GET'])
def health_check():
    """Verificar estado del sistema"""
    try:
        # Verificar conexiones
        redis_client.ping()
        rabbitmq_channel.queue_declare(queue='tts_calls', passive=True)
        
        stats = queue_manager.get_queue_stats()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'connections': {
                'redis': 'connected',
                'rabbitmq': 'connected'
            },
            'stats': stats
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/tts/call', methods=['POST'])
def create_tts_call():
    """Crear nueva llamada TTS (enviar a cola)"""
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({
                'success': False,
                'error': 'Campo "text" es requerido'
            }), 400
        
        text = data['text']
        phone_number = data.get('phone_number', '3005050149')
        language = data.get('language', 'es')
        priority = data.get('priority', 'normal')
        
        # Validaciones
        if len(text.strip()) == 0:
            return jsonify({
                'success': False,
                'error': 'El texto no puede estar vacío'
            }), 400
        
        if len(text) > 1000:
            return jsonify({
                'success': False,
                'error': 'El texto no puede exceder 1000 caracteres'
            }), 400
        
        if priority not in ['normal', 'high']:
            priority = 'normal'
        
        # Enviar a cola
        job_data = queue_manager.enqueue_tts_call(text, phone_number, language, priority)
        
        return jsonify({
            'success': True,
            'job_id': job_data['job_id'],
            'status': 'queued',
            'message': 'Llamada TTS enviada a cola para procesamiento',
            'queue': 'priority' if priority == 'high' else 'normal',
            'estimated_wait': '30-60 segundos',
            'timestamp': job_data['created_at']
        }), 202
        
    except Exception as e:
        logger.error(f"❌ Error en /tts/call: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/tts/status/<job_id>', methods=['GET'])
def get_call_status(job_id):
    """Obtener estado de una llamada TTS"""
    try:
        job_data = queue_manager.get_job_status(job_id)
        
        if not job_data:
            return jsonify({
                'success': False,
                'error': 'Trabajo no encontrado'
            }), 404
        
        return jsonify({
            'success': True,
            'job_id': job_id,
            'status': job_data.get('status', 'unknown'),
            'text': job_data.get('text', ''),
            'phone_number': job_data.get('phone_number', ''),
            'created_at': job_data.get('created_at', ''),
            'processed_at': job_data.get('processed_at', ''),
            'completed_at': job_data.get('completed_at', ''),
            'worker_id': job_data.get('worker_id', ''),
            'error': job_data.get('error', '')
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo estado: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/queue/stats', methods=['GET'])
def get_queue_statistics():
    """Obtener estadísticas del sistema de colas"""
    try:
        stats = queue_manager.get_queue_stats()
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'statistics': stats
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo estadísticas: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/workers/scale', methods=['POST'])
def scale_workers():
    """Escalar número de workers (placeholder para implementación futura)"""
    try:
        data = request.get_json()
        desired_workers = data.get('workers', 3)
        
        return jsonify({
            'success': True,
            'message': f'Solicitud de escalado a {desired_workers} workers recibida',
            'note': 'Implementar con Docker Compose o Kubernetes'
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    print("🚀 Iniciando API de Colas TTS...")
    print(f"📡 RabbitMQ: {RABBITMQ_URL}")
    print(f"📊 Redis: {REDIS_URL}")
    print(f"🌐 API: http://{API_HOST}:{API_PORT}")
    
    app.run(host=API_HOST, port=API_PORT, debug=True)
