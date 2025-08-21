// Fix para el problema de sincronización de Tool Call IDs
// Problema: Los eventos delta llegan antes que el conversation.item.created

class ToolCallManager {
    constructor() {
        // Registro principal de tool calls activas
        this.activeCalls = new Map();
        
        // Buffer temporal para deltas que llegan antes del item.created
        this.pendingDeltas = new Map();
        
        // Registro de llamadas completadas para evitar duplicados
        this.completedCalls = new Set();
        
        // Timeout para limpiar buffers viejos (30 segundos)
        this.cleanupInterval = 30000;
        
        this.startCleanup();
    }
    
    // Registrar una nueva tool call cuando llega conversation.item.created
    registerToolCall(callId, name, item) {
        console.log(`[ToolCallManager] Registering tool call: ${callId} (${name})`);
        
        // Si hay deltas pendientes, procesarlos ahora
        if (this.pendingDeltas.has(callId)) {
            const deltas = this.pendingDeltas.get(callId);
            console.log(`[ToolCallManager] Processing ${deltas.length} pending deltas for ${callId}`);
            
            // Crear la entrada con los deltas acumulados
            this.activeCalls.set(callId, {
                name: name,
                args: deltas.join(''),
                item: item,
                startTime: Date.now(),
                status: 'collecting_args'
            });
            
            // Limpiar el buffer
            this.pendingDeltas.delete(callId);
        } else {
            // Crear entrada nueva sin deltas
            this.activeCalls.set(callId, {
                name: name,
                args: '',
                item: item,
                startTime: Date.now(),
                status: 'collecting_args'
            });
        }
        
        return true;
    }
    
    // Manejar deltas de argumentos
    handleArgumentDelta(callId, delta) {
        // Si la call ya está registrada, agregar el delta
        if (this.activeCalls.has(callId)) {
            const call = this.activeCalls.get(callId);
            call.args += delta;
            return true;
        }
        
        // Si no está registrada, guardar en buffer temporal
        if (!this.pendingDeltas.has(callId)) {
            this.pendingDeltas.set(callId, []);
            console.log(`[ToolCallManager] Buffering deltas for unregistered call: ${callId}`);
        }
        
        this.pendingDeltas.get(callId).push(delta);
        return false; // Indica que fue bufferizado
    }
    
    // Completar argumentos y preparar para ejecución
    completeArguments(callId) {
        const call = this.activeCalls.get(callId);
        
        if (!call) {
            // Intentar reconstruir desde deltas pendientes
            if (this.pendingDeltas.has(callId)) {
                console.warn(`[ToolCallManager] Reconstructing call from pending deltas: ${callId}`);
                const args = this.pendingDeltas.get(callId).join('');
                
                // Crear entrada reconstruida
                this.activeCalls.set(callId, {
                    name: 'unknown', // Se actualizará cuando llegue el item
                    args: args,
                    item: null,
                    startTime: Date.now(),
                    status: 'reconstructed'
                });
                
                this.pendingDeltas.delete(callId);
                return this.activeCalls.get(callId);
            }
            
            console.error(`[ToolCallManager] Cannot complete unknown call: ${callId}`);
            return null;
        }
        
        call.status = 'ready_to_execute';
        console.log(`[ToolCallManager] Arguments complete for ${callId}: ${call.args.length} chars`);
        return call;
    }
    
    // Marcar como ejecutando
    markExecuting(callId) {
        const call = this.activeCalls.get(callId);
        if (call) {
            call.status = 'executing';
            call.executionStartTime = Date.now();
        }
        return call;
    }
    
    // Completar ejecución y limpiar
    completeExecution(callId, result) {
        const call = this.activeCalls.get(callId);
        
        if (!call) {
            console.error(`[ToolCallManager] Cannot complete unknown call: ${callId}`);
            return false;
        }
        
        // Calcular tiempos
        const totalTime = Date.now() - call.startTime;
        const executionTime = call.executionStartTime ? 
            Date.now() - call.executionStartTime : 0;
        
        console.log(`[ToolCallManager] Completed ${callId} - Total: ${totalTime}ms, Execution: ${executionTime}ms`);
        
        // Mover a completadas y limpiar de activas
        this.completedCalls.add(callId);
        this.activeCalls.delete(callId);
        
        return {
            callId,
            result,
            totalTime,
            executionTime
        };
    }
    
    // Verificar si una call está activa
    isActive(callId) {
        return this.activeCalls.has(callId);
    }
    
    // Verificar si una call ya fue completada
    isCompleted(callId) {
        return this.completedCalls.has(callId);
    }
    
    // Obtener información de una call
    getCall(callId) {
        return this.activeCalls.get(callId);
    }
    
    // Limpiar buffers viejos periódicamente
    startCleanup() {
        setInterval(() => {
            const now = Date.now();
            const timeout = this.cleanupInterval;
            
            // Limpiar deltas pendientes viejos
            for (const [callId, deltas] of this.pendingDeltas) {
                // Asumimos que si están más de 30 segundos, son obsoletos
                console.log(`[ToolCallManager] Cleaning old pending deltas: ${callId}`);
                this.pendingDeltas.delete(callId);
            }
            
            // Limpiar calls activas muy viejas (más de 2 minutos)
            for (const [callId, call] of this.activeCalls) {
                if (now - call.startTime > 120000) {
                    console.warn(`[ToolCallManager] Cleaning stale active call: ${callId}`);
                    this.activeCalls.delete(callId);
                }
            }
            
            // Limpiar registro de completadas si es muy grande
            if (this.completedCalls.size > 100) {
                this.completedCalls.clear();
                console.log(`[ToolCallManager] Cleared completed calls registry`);
            }
        }, this.cleanupInterval);
    }
    
    // Obtener estadísticas
    getStats() {
        return {
            activeCalls: this.activeCalls.size,
            pendingDeltas: this.pendingDeltas.size,
            completedCalls: this.completedCalls.size,
            activeCallIds: Array.from(this.activeCalls.keys()),
            pendingDeltaIds: Array.from(this.pendingDeltas.keys())
        };
    }
}

// Exportar para uso en voice_live_interface.html
window.ToolCallManager = ToolCallManager;

console.log('[ToolCallManager] Tool Call synchronization fix loaded');