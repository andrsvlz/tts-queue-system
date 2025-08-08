#!/usr/bin/env python3
"""
Worker para procesar llamadas TTS desde RabbitMQ
"""

import pika
import redis
import json
import os
import time
import uuid
import subprocess
from datetime import datetime
from gtts import gTTS
from pydub import AudioSegment
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración
RABBITMQ_URL = os.getenv('RABBITMQ_URL', 'amqp://tts_user:tts_password_2024@localhost:5672/tts_vhost')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
WORKER_ID = os.getenv('WORKER_ID', f'worker-{uuid.uuid4().hex[:8]}')
WORKER_CONCURRENCY = int(os.getenv('WORKER_CONCURRENCY', 1))
ASTERISK_HOST = os.getenv('ASTERISK_HOST', 'localhost')

# Directorios de Asterisk
ASTERISK_SOUNDS_DIR = '/var/lib/asterisk/sounds/en_US_f_Allison'
ASTERISK_SPOOL_DIR = '/var/spool/asterisk/outgoing'

class TTSWorker:
    def __init__(self):
        self.worker_id = WORKER_ID
        self.redis = None
        self.connection = None
        self.channel = None
        self.is_running = False
        
    def connect(self):
        """Conectar a RabbitMQ y Redis"""
        try:
            # Conectar a Redis
            self.redis = redis.from_url(REDIS_URL)
            self.redis.ping()
            logger.info(f"✅ Worker {self.worker_id} conectado a Redis")
            
            # Conectar a RabbitMQ
            parameters = pika.URLParameters(RABBITMQ_URL)
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Declarar colas
            self.channel.queue_declare(queue='tts_calls', durable=True)
            self.channel.queue_declare(queue='tts_priority', durable=True)
            self.channel.queue_declare(queue='tts_results', durable=True)
            
            # Configurar QoS para procesar un mensaje a la vez
            self.channel.basic_qos(prefetch_count=WORKER_CONCURRENCY)
            
            logger.info(f"✅ Worker {self.worker_id} conectado a RabbitMQ")
            
            # Registrar worker en Redis
            self.register_worker()
            
        except Exception as e:
            logger.error(f"❌ Error conectando worker {self.worker_id}: {e}")
            raise
    
    def register_worker(self):
        """Registrar worker en Redis"""
        worker_data = {
            'worker_id': self.worker_id,
            'status': 'idle',
            'started_at': datetime.now().isoformat(),
            'processed_jobs': 0,
            'last_heartbeat': datetime.now().isoformat()
        }
        self.redis.setex(f"worker:{self.worker_id}", 300, json.dumps(worker_data))
        logger.info(f"📝 Worker {self.worker_id} registrado")
    
    def update_worker_status(self, status, current_job=None):
        """Actualizar estado del worker"""
        try:
            worker_data = self.redis.get(f"worker:{self.worker_id}")
            if worker_data:
                data = json.loads(worker_data)
                data['status'] = status
                data['last_heartbeat'] = datetime.now().isoformat()
                if current_job:
                    data['current_job'] = current_job
                elif 'current_job' in data:
                    del data['current_job']
                
                self.redis.setex(f"worker:{self.worker_id}", 300, json.dumps(data))
        except Exception as e:
            logger.error(f"❌ Error actualizando estado worker: {e}")
    
    def generate_tts_audio(self, text, language='es'):
        """Generar audio TTS"""
        try:
            audio_id = uuid.uuid4().hex[:8]
            logger.info(f"🎵 Generando audio TTS: {text[:50]}...")
            
            # Generar audio con Google TTS
            tts = gTTS(text=text, lang=language, slow=False)
            temp_mp3 = f'/tmp/tts_{audio_id}.mp3'
            tts.save(temp_mp3)
            
            # Convertir a formato GSM para Asterisk
            audio = AudioSegment.from_mp3(temp_mp3)
            audio = audio.set_frame_rate(8000).set_channels(1)
            
            # Guardar en directorio de Asterisk
            gsm_file = f'{ASTERISK_SOUNDS_DIR}/tts_{audio_id}.gsm'
            audio.export(gsm_file, format='gsm')
            
            # Cambiar permisos
            os.system(f'sudo chown root:root {gsm_file}')
            os.system(f'sudo chmod 644 {gsm_file}')
            
            # Limpiar archivo temporal
            os.remove(temp_mp3)
            
            logger.info(f"✅ Audio TTS generado: tts_{audio_id}.gsm")
            return f'tts_{audio_id}'
            
        except Exception as e:
            logger.error(f"❌ Error generando audio TTS: {e}")
            raise
    
    def create_asterisk_call(self, phone_number, audio_filename, job_id):
        """Crear archivo de llamada para Asterisk"""
        try:
            # Crear archivo de llamada
            call_content = f"""Channel: SIP/mysipbk/{phone_number}
Context: internal
Extension: tts_playback
Priority: 1
Set: AUDIO_FILE={audio_filename}
Set: JOB_ID={job_id}
Set: PHONE_NUMBER={phone_number}
MaxRetries: 2
RetryTime: 60
WaitTime: 30
"""
            
            # Escribir archivo temporal
            call_file = f'/tmp/call_{job_id}.call'
            with open(call_file, 'w') as f:
                f.write(call_content)
            
            # Mover al directorio de spool de Asterisk
            spool_file = f'{ASTERISK_SPOOL_DIR}/call_{job_id}.call'
            os.system(f'sudo mv {call_file} {spool_file}')
            os.system(f'sudo chown asterisk:asterisk {spool_file}')
            
            logger.info(f"📞 Archivo de llamada creado: {spool_file}")
            return spool_file
            
        except Exception as e:
            logger.error(f"❌ Error creando llamada Asterisk: {e}")
            raise
    
    def process_tts_job(self, job_data):
        """Procesar trabajo TTS completo"""
        job_id = job_data['job_id']
        
        try:
            logger.info(f"🔄 Procesando trabajo {job_id}")
            
            # Actualizar estado en Redis
            job_data['status'] = 'processing'
            job_data['processed_at'] = datetime.now().isoformat()
            job_data['worker_id'] = self.worker_id
            self.redis.setex(f"job:{job_id}", 3600, json.dumps(job_data))
            
            # Actualizar estado del worker
            self.update_worker_status('processing', job_id)
            
            # Generar audio TTS
            audio_filename = self.generate_tts_audio(
                job_data['text'], 
                job_data.get('language', 'es')
            )
            
            # Crear llamada Asterisk
            call_file = self.create_asterisk_call(
                job_data['phone_number'],
                audio_filename,
                job_id
            )
            
            # Marcar como completado
            job_data['status'] = 'completed'
            job_data['completed_at'] = datetime.now().isoformat()
            job_data['audio_file'] = audio_filename
            job_data['call_file'] = call_file
            self.redis.setex(f"job:{job_id}", 3600, json.dumps(job_data))
            
            # Enviar resultado a cola de resultados
            self.channel.basic_publish(
                exchange='',
                routing_key='tts_results',
                body=json.dumps(job_data)
            )
            
            logger.info(f"✅ Trabajo {job_id} completado exitosamente")
            
            # Actualizar contador de trabajos procesados
            worker_data = json.loads(self.redis.get(f"worker:{self.worker_id}"))
            worker_data['processed_jobs'] = worker_data.get('processed_jobs', 0) + 1
            self.redis.setex(f"worker:{self.worker_id}", 300, json.dumps(worker_data))
            
        except Exception as e:
            logger.error(f"❌ Error procesando trabajo {job_id}: {e}")
            
            # Marcar como fallido
            job_data['status'] = 'failed'
            job_data['error'] = str(e)
            job_data['failed_at'] = datetime.now().isoformat()
            self.redis.setex(f"job:{job_id}", 3600, json.dumps(job_data))
            
            raise
        finally:
            # Volver a estado idle
            self.update_worker_status('idle')
    
    def callback(self, ch, method, properties, body):
        """Callback para procesar mensajes de la cola"""
        try:
            # Parsear trabajo
            job_data = json.loads(body)
            
            # Procesar trabajo
            self.process_tts_job(job_data)
            
            # Confirmar procesamiento
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.error(f"❌ Error en callback: {e}")
            # Rechazar mensaje (volverá a la cola)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def start_consuming(self):
        """Iniciar consumo de mensajes"""
        try:
            logger.info(f"🚀 Worker {self.worker_id} iniciando consumo...")
            
            # Configurar consumidores para ambas colas (prioridad primero)
            self.channel.basic_consume(
                queue='tts_priority',
                on_message_callback=self.callback
            )
            
            self.channel.basic_consume(
                queue='tts_calls',
                on_message_callback=self.callback
            )
            
            self.is_running = True
            logger.info(f"✅ Worker {self.worker_id} listo para procesar trabajos")
            
            # Iniciar consumo
            self.channel.start_consuming()
            
        except KeyboardInterrupt:
            logger.info(f"🛑 Worker {self.worker_id} detenido por usuario")
            self.stop()
        except Exception as e:
            logger.error(f"❌ Error en worker {self.worker_id}: {e}")
            raise
    
    def stop(self):
        """Detener worker"""
        self.is_running = False
        if self.channel:
            self.channel.stop_consuming()
        if self.connection:
            self.connection.close()
        
        # Desregistrar worker
        self.redis.delete(f"worker:{self.worker_id}")
        logger.info(f"🛑 Worker {self.worker_id} detenido")

def main():
    """Función principal"""
    logger.info(f"🚀 Iniciando TTS Worker {WORKER_ID}")
    logger.info(f"📡 RabbitMQ: {RABBITMQ_URL}")
    logger.info(f"📊 Redis: {REDIS_URL}")
    logger.info(f"🔧 Concurrencia: {WORKER_CONCURRENCY}")
    
    worker = TTSWorker()
    
    try:
        worker.connect()
        worker.start_consuming()
    except Exception as e:
        logger.error(f"❌ Error fatal en worker: {e}")
    finally:
        worker.stop()

if __name__ == '__main__':
    main()
