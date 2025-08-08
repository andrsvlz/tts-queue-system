#!/bin/bash

echo "🎙️ TTS QUEUE SYSTEM MANAGER"
echo "============================"

# Función para mostrar ayuda
show_help() {
    echo "Uso: $0 [comando]"
    echo ""
    echo "Comandos disponibles:"
    echo "  start         - Iniciar todo el sistema (RabbitMQ, Redis, API, Workers, Dashboard)"
    echo "  stop          - Detener todo el sistema"
    echo "  restart       - Reiniciar todo el sistema"
    echo "  status        - Ver estado de todos los servicios"
    echo "  logs          - Ver logs de todos los servicios"
    echo "  scale [N]     - Escalar workers a N instancias"
    echo "  api-only      - Solo iniciar API y dependencias"
    echo "  workers-only  - Solo iniciar workers"
    echo "  dashboard     - Solo iniciar dashboard"
    echo "  test          - Realizar llamada de prueba"
    echo "  setup         - Configurar Asterisk para el sistema de colas"
    echo "  clean         - Limpiar contenedores, volúmenes e imágenes"
    echo "  help          - Mostrar esta ayuda"
}

# Función para iniciar todo el sistema
start_system() {
    echo "🚀 Iniciando sistema completo de colas TTS..."
    
    # Verificar que docker-compose esté disponible
    if ! command -v docker-compose &> /dev/null; then
        echo "❌ docker-compose no está instalado"
        exit 1
    fi
    
    # Iniciar servicios
    docker-compose up -d
    
    echo "⏳ Esperando que los servicios inicien..."
    sleep 30
    
    echo "✅ Sistema iniciado!"
    echo ""
    echo "📡 Servicios disponibles:"
    echo "   - RabbitMQ Management: http://localhost:15672 (tts_user/tts_password_2024)"
    echo "   - API REST: http://localhost:5000"
    echo "   - Dashboard: http://localhost:8080"
    echo "   - Redis: localhost:6379"
    echo ""
    echo "🧪 Para probar: $0 test"
}

# Función para detener el sistema
stop_system() {
    echo "🛑 Deteniendo sistema de colas TTS..."
    docker-compose down
    echo "✅ Sistema detenido"
}

# Función para reiniciar el sistema
restart_system() {
    echo "🔄 Reiniciando sistema..."
    stop_system
    sleep 5
    start_system
}

# Función para ver estado
show_status() {
    echo "📊 Estado del sistema:"
    docker-compose ps
    echo ""
    echo "📈 Estadísticas rápidas:"
    curl -s http://localhost:5000/health | python3 -m json.tool 2>/dev/null || echo "API no disponible"
}

# Función para ver logs
show_logs() {
    echo "📋 Logs del sistema (Ctrl+C para salir):"
    docker-compose logs -f
}

# Función para escalar workers
scale_workers() {
    local num_workers=${1:-3}
    echo "⚖️ Escalando a $num_workers workers..."
    
    # Detener workers actuales
    docker-compose stop tts-worker-1 tts-worker-2 tts-worker-3
    docker-compose rm -f tts-worker-1 tts-worker-2 tts-worker-3
    
    # Crear archivo temporal de compose con N workers
    cat > docker-compose.override.yml << EOF
version: '3.8'
services:
EOF
    
    for i in $(seq 1 $num_workers); do
        cat >> docker-compose.override.yml << EOF
  tts-worker-$i:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker
    container_name: tts-worker-$i
    restart: unless-stopped
    environment:
      - RABBITMQ_URL=amqp://tts_user:tts_password_2024@rabbitmq:5672/tts_vhost
      - REDIS_URL=redis://redis:6379/0
      - WORKER_ID=worker-$i
      - WORKER_CONCURRENCY=1
      - ASTERISK_HOST=host.docker.internal
    depends_on:
      rabbitmq:
        condition: service_healthy
      redis:
        condition: service_started
    networks:
      - tts_network
    volumes:
      - ./logs:/app/logs
      - /var/lib/asterisk/sounds:/var/lib/asterisk/sounds
      - /var/spool/asterisk/outgoing:/var/spool/asterisk/outgoing

EOF
    done
    
    # Iniciar workers escalados
    docker-compose up -d
    
    echo "✅ Sistema escalado a $num_workers workers"
    rm -f docker-compose.override.yml
}

# Función para configurar Asterisk
setup_asterisk() {
    echo "⚙️ Configurando Asterisk para sistema de colas..."
    
    # Copiar configuración de extensiones
    sudo cp config/extensions_queue.conf /etc/asterisk/extensions.conf
    sudo chown asterisk:asterisk /etc/asterisk/extensions.conf
    
    # Recargar configuración
    sudo asterisk -rx "dialplan reload"
    
    echo "✅ Asterisk configurado para sistema de colas"
    echo "📋 Extensión principal: tts_playback"
}

# Función para realizar prueba
test_system() {
    echo "🧪 Realizando llamada de prueba..."
    
    # Verificar que la API esté disponible
    if ! curl -s http://localhost:5000/health > /dev/null; then
        echo "❌ API no está disponible. Ejecuta: $0 start"
        exit 1
    fi
    
    # Realizar llamada de prueba
    response=$(curl -s -X POST http://localhost:5000/tts/call \
        -H 'Content-Type: application/json' \
        -d '{
            "text": "Hola, esta es una prueba del sistema de colas TTS con RabbitMQ. El sistema está funcionando correctamente.",
            "phone_number": "3005050149",
            "priority": "normal"
        }')
    
    echo "📞 Respuesta de la API:"
    echo "$response" | python3 -m json.tool
    
    # Extraer job_id para seguimiento
    job_id=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))" 2>/dev/null)
    
    if [ ! -z "$job_id" ]; then
        echo ""
        echo "🔍 Para verificar estado del trabajo:"
        echo "curl http://localhost:5000/tts/status/$job_id"
        echo ""
        echo "📊 Para ver dashboard: http://localhost:8080"
    fi
}

# Función para limpiar todo
clean_system() {
    echo "🧹 Limpiando sistema completo..."
    
    # Detener y eliminar contenedores
    docker-compose down -v
    
    # Eliminar imágenes
    docker-compose down --rmi all
    
    # Limpiar volúmenes huérfanos
    docker volume prune -f
    
    # Limpiar archivos temporales
    rm -f docker-compose.override.yml
    
    echo "✅ Sistema limpiado completamente"
}

# Procesar argumentos
case "$1" in
    start)
        start_system
        ;;
    stop)
        stop_system
        ;;
    restart)
        restart_system
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    scale)
        scale_workers $2
        ;;
    api-only)
        docker-compose up -d rabbitmq redis tts-api
        ;;
    workers-only)
        docker-compose up -d tts-worker-1 tts-worker-2 tts-worker-3
        ;;
    dashboard)
        docker-compose up -d tts-dashboard
        ;;
    test)
        test_system
        ;;
    setup)
        setup_asterisk
        ;;
    clean)
        clean_system
        ;;
    help)
        show_help
        ;;
    "")
        show_help
        ;;
    *)
        echo "❌ Comando no válido: $1"
        show_help
        exit 1
        ;;
esac
