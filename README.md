# 🎙️ Sistema de Colas TTS con RabbitMQ y Asterisk

Sistema profesional de colas para llamadas TTS (Text-to-Speech) usando **RabbitMQ**, **Redis**, **Asterisk** y **Google Translate**.

## 🎯 Características

- ✅ **RabbitMQ** para gestión de colas robusta
- ✅ **Workers escalables** (configurable de 1 a N workers)
- ✅ **Redis** para cache y estado de trabajos
- ✅ **API REST** para enviar trabajos
- ✅ **Dashboard web** para monitoreo en tiempo real
- ✅ **Colas de prioridad** (normal y alta prioridad)
- ✅ **Integración completa** con Asterisk
- ✅ **Docker Compose** para despliegue fácil

## 🏗️ Arquitectura

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   API REST  │───▶│  RabbitMQ   │───▶│   Workers   │
│             │    │   Queues    │    │   (1-N)     │
└─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│    Redis    │    │  Dashboard  │    │  Asterisk   │
│   (Estado)  │    │ (Monitoreo) │    │    PBX      │
└─────────────┘    └─────────────┘    └─────────────┘
```

## 🚀 Inicio Rápido

### 1. Configurar el sistema:
```bash
cd tts-queue-system
chmod +x manage.sh

# Configurar Asterisk
./manage.sh setup

# Iniciar todo el sistema
./manage.sh start
```

### 2. Realizar llamada TTS:
```bash
# Llamada de prueba
./manage.sh test

# O usando curl directamente
curl -X POST http://localhost:5000/tts/call \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Hola, esta es una prueba del sistema de colas TTS",
    "phone_number": "3005050149",
    "priority": "normal"
  }'
```

### 3. Monitorear el sistema:
- **Dashboard**: http://localhost:8080
- **RabbitMQ Management**: http://localhost:15672 (tts_user/tts_password_2024)
- **API Health**: http://localhost:5000/health

## 📋 Comandos Disponibles

| Comando | Descripción |
|---------|-------------|
| `./manage.sh start` | Iniciar todo el sistema |
| `./manage.sh stop` | Detener todo el sistema |
| `./manage.sh status` | Ver estado de servicios |
| `./manage.sh scale 5` | Escalar a 5 workers |
| `./manage.sh test` | Realizar llamada de prueba |
| `./manage.sh logs` | Ver logs en tiempo real |
| `./manage.sh dashboard` | Solo iniciar dashboard |
| `./manage.sh clean` | Limpiar todo |

## 🔧 Configuración de Workers

### Escalar workers dinámicamente:
```bash
# Escalar a 5 workers
./manage.sh scale 5

# Escalar a 1 worker
./manage.sh scale 1

# Ver estado actual
./manage.sh status
```

### Variables de entorno para workers:
- `WORKER_CONCURRENCY`: Trabajos simultáneos por worker (default: 1)
- `WORKER_ID`: ID único del worker
- `RABBITMQ_URL`: URL de conexión a RabbitMQ
- `REDIS_URL`: URL de conexión a Redis

## 📡 API REST

### Endpoints principales:

#### Crear llamada TTS:
```bash
POST /tts/call
Content-Type: application/json

{
  "text": "Mensaje a convertir en voz",
  "phone_number": "3005050149",
  "language": "es",
  "priority": "normal"  // "normal" o "high"
}
```

#### Verificar estado de trabajo:
```bash
GET /tts/status/{job_id}
```

#### Estadísticas del sistema:
```bash
GET /queue/stats
```

#### Health check:
```bash
GET /health
```

## 🎛️ Dashboard de Monitoreo

El dashboard web (http://localhost:8080) muestra:

- **📊 Estadísticas de colas** (normal, prioridad, resultados)
- **👷 Estado de workers** (total, activos, inactivos)
- **📋 Trabajos** (total, por estado, recientes)
- **🔄 Actualización automática** cada 5 segundos

## 🔄 Flujo de Procesamiento

1. **Cliente envía** solicitud TTS a la API REST
2. **API valida** y envía trabajo a cola RabbitMQ
3. **Worker disponible** toma trabajo de la cola
4. **Worker genera** audio TTS con Google Translate
5. **Worker crea** archivo de llamada para Asterisk
6. **Asterisk procesa** la llamada automáticamente
7. **Estado se actualiza** en Redis y cola de resultados

## 🏷️ Tipos de Colas

### Cola Normal (`tts_calls`):
- Trabajos de prioridad normal
- Procesamiento FIFO (First In, First Out)

### Cola de Prioridad (`tts_priority`):
- Trabajos de alta prioridad
- Se procesan antes que los normales

### Cola de Resultados (`tts_results`):
- Resultados de trabajos completados
- Para auditoría y monitoreo

## 📊 Estados de Trabajos

| Estado | Descripción |
|--------|-------------|
| `queued` | En cola esperando procesamiento |
| `processing` | Siendo procesado por un worker |
| `completed` | Completado exitosamente |
| `failed` | Falló durante el procesamiento |

## 🛠️ Troubleshooting

### Problema: Workers no procesan trabajos
```bash
# Verificar estado de workers
./manage.sh status

# Ver logs de workers
docker-compose logs tts-worker-1

# Reiniciar workers
docker-compose restart tts-worker-1 tts-worker-2 tts-worker-3
```

### Problema: RabbitMQ no conecta
```bash
# Verificar estado de RabbitMQ
docker-compose logs rabbitmq

# Reiniciar RabbitMQ
docker-compose restart rabbitmq
```

### Problema: Asterisk no reproduce audio
```bash
# Verificar configuración de Asterisk
./manage.sh setup

# Verificar permisos de archivos de audio
ls -la /var/lib/asterisk/sounds/en_US_f_Allison/
```

## 📈 Monitoreo y Métricas

### Métricas disponibles:
- **Trabajos en cola** por tipo
- **Workers activos/inactivos**
- **Trabajos procesados** por worker
- **Tiempo de procesamiento** promedio
- **Tasa de éxito/fallo**

### Logs estructurados:
- **API**: Solicitudes HTTP y errores
- **Workers**: Procesamiento de trabajos
- **RabbitMQ**: Estado de colas
- **Redis**: Operaciones de cache

## 🔒 Seguridad

### Credenciales por defecto:
- **RabbitMQ**: `tts_user` / `tts_password_2024`
- **Redis**: Sin contraseña (solo localhost)

### Para producción:
1. Cambiar credenciales por defecto
2. Configurar SSL/TLS
3. Implementar autenticación en API
4. Configurar firewall

## 🎉 Ejemplo Completo

```bash
# 1. Iniciar sistema
./manage.sh start

# 2. Escalar a 3 workers
./manage.sh scale 3

# 3. Realizar llamada de alta prioridad
curl -X POST http://localhost:5000/tts/call \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Mensaje urgente del sistema de emergencia",
    "phone_number": "3005050149",
    "priority": "high"
  }'

# 4. Monitorear en dashboard
# Abrir: http://localhost:8080

# 5. Ver estadísticas
curl http://localhost:5000/queue/stats
```

---

**¡Sistema de colas TTS profesional listo para producción! 🎙️📞🚀**
