#!/usr/bin/env python3
"""
Dashboard para monitorear sistema de colas TTS
"""

from flask import Flask, render_template, jsonify
import pika
import redis
import json
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

# Conexiones globales
redis_client = None
rabbitmq_connection = None
rabbitmq_channel = None

def init_connections():
    """Inicializar conexiones"""
    global redis_client, rabbitmq_connection, rabbitmq_channel
    
    try:
        # Redis
        redis_client = redis.from_url(REDIS_URL)
        redis_client.ping()
        
        # RabbitMQ
        parameters = pika.URLParameters(RABBITMQ_URL)
        rabbitmq_connection = pika.BlockingConnection(parameters)
        rabbitmq_channel = rabbitmq_connection.channel()
        
        logger.info("✅ Dashboard conectado a Redis y RabbitMQ")
        
    except Exception as e:
        logger.error(f"❌ Error conectando dashboard: {e}")
        raise

class DashboardManager:
    def __init__(self):
        self.redis = redis_client
        self.channel = rabbitmq_channel
    
    def get_system_stats(self):
        """Obtener estadísticas del sistema"""
        try:
            stats = {}
            
            # Estadísticas de colas RabbitMQ
            normal_queue = self.channel.queue_declare(queue='tts_calls', passive=True)
            priority_queue = self.channel.queue_declare(queue='tts_priority', passive=True)
            results_queue = self.channel.queue_declare(queue='tts_results', passive=True)
            
            stats['queues'] = {
                'normal': {
                    'name': 'Normal Calls',
                    'count': normal_queue.method.message_count,
                    'consumers': normal_queue.method.consumer_count
                },
                'priority': {
                    'name': 'Priority Calls',
                    'count': priority_queue.method.message_count,
                    'consumers': priority_queue.method.consumer_count
                },
                'results': {
                    'name': 'Results',
                    'count': results_queue.method.message_count,
                    'consumers': results_queue.method.consumer_count
                }
            }
            
            # Estadísticas de workers
            worker_keys = self.redis.keys("worker:*")
            workers = []
            total_processed = 0
            
            for key in worker_keys:
                worker_data = json.loads(self.redis.get(key))
                workers.append(worker_data)
                total_processed += worker_data.get('processed_jobs', 0)
            
            stats['workers'] = {
                'total': len(workers),
                'active': len([w for w in workers if w.get('status') == 'processing']),
                'idle': len([w for w in workers if w.get('status') == 'idle']),
                'total_processed': total_processed,
                'details': workers
            }
            
            # Estadísticas de trabajos
            job_keys = self.redis.keys("job:*")
            jobs = []
            job_stats = {'queued': 0, 'processing': 0, 'completed': 0, 'failed': 0}
            
            for key in job_keys:
                job_data = json.loads(self.redis.get(key))
                jobs.append(job_data)
                status = job_data.get('status', 'unknown')
                if status in job_stats:
                    job_stats[status] += 1
            
            stats['jobs'] = {
                'total': len(jobs),
                'by_status': job_stats,
                'recent': sorted(jobs, key=lambda x: x.get('created_at', ''), reverse=True)[:10]
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo estadísticas: {e}")
            return {}

# Instancia del gestor
dashboard_manager = None

@app.before_request
def startup():
    """Inicializar al arrancar"""
    global dashboard_manager
    if dashboard_manager is None:
        init_connections()
        dashboard_manager = DashboardManager()

@app.route('/')
def index():
    """Página principal del dashboard"""
    return render_template('dashboard.html')

@app.route('/api/stats')
def get_stats():
    """API para obtener estadísticas"""
    try:
        stats = dashboard_manager.get_system_stats()
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'stats': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health')
def health():
    """Health check del dashboard"""
    try:
        redis_client.ping()
        rabbitmq_channel.queue_declare(queue='tts_calls', passive=True)
        return jsonify({'status': 'healthy'})
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

if __name__ == '__main__':
    print("🚀 Iniciando Dashboard TTS...")
    print(f"📡 RabbitMQ: {RABBITMQ_URL}")
    print(f"📊 Redis: {REDIS_URL}")
    print("🌐 Dashboard: http://localhost:8080")
    
    app.run(host='0.0.0.0', port=8080, debug=True)
