# Solución para ERR_UNEXPECTED_PROXY_AUTH

## Problema
El error `net::ERR_UNEXPECTED_PROXY_AUTH` ocurre cuando el navegador recibe una respuesta HTTP 407 (Proxy Authentication Required) al intentar acceder a localhost. Esto es común en entornos corporativos con proxy configurado.

## Soluciones Implementadas

### 1. Headers Mejorados en fetch()
Se agregaron headers adicionales en la llamada fetch:
- `X-Requested-With: XMLHttpRequest` - Indica que es una llamada AJAX
- `credentials: 'same-origin'` - Usa credenciales solo para el mismo origen
- `mode: 'same-origin'` - Restringe la solicitud al mismo origen

### 2. Script de Bypass de Proxy (proxy_bypass.js)
Creado un script helper que:
- Usa 127.0.0.1 en lugar de localhost (evita resolución DNS)
- Agrega headers para bypass de proxy
- Proporciona una función wrapper para llamadas API

## Configuración del Sistema Operativo

### Windows
1. **Variables de entorno** - Agregar localhost a NO_PROXY:
   ```
   NO_PROXY=localhost,127.0.0.1,*.local
   no_proxy=localhost,127.0.0.1,*.local
   ```

2. **Internet Explorer/Edge** - Excluir localhost del proxy:
   - Configuración → Opciones de Internet → Conexiones → Configuración de LAN
   - Avanzado → Excepciones: agregar `localhost;127.0.0.1;*.local`

3. **Chrome** - Lanzar con flags especiales:
   ```
   chrome.exe --proxy-bypass-list="localhost;127.0.0.1;*.local"
   ```

### Configuración de Flask/Python
Agregar estas variables de entorno antes de ejecutar:
```bash
set NO_PROXY=localhost,127.0.0.1
set HTTP_PROXY=
set HTTPS_PROXY=
python app.py
```

## Solución Alternativa en app.py

Si el problema persiste, modificar app.py para agregar headers de bypass:

```python
@app.after_request
def after_request(response):
    # Headers para evitar proxy caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response
```

## Testing

1. **Verificar sin proxy**:
   ```bash
   curl -X POST http://127.0.0.1:5000/api/neuro_rag \
        -H "Content-Type: application/json" \
        -d '{"type":"function_call","parameters":{"query":"test"}}'
   ```

2. **Verificar headers**:
   ```bash
   curl -I http://127.0.0.1:5000/api/neuro_rag
   ```

3. **Browser DevTools**:
   - Network tab → Verificar que las solicitudes van a 127.0.0.1:5000
   - No debe aparecer header "Proxy-Authorization"

## Recomendación Principal

Para desarrollo local, usar **127.0.0.1** en lugar de **localhost** en todas las URLs:
- Frontend: http://127.0.0.1:5000
- API calls: http://127.0.0.1:5000/api/...

Esto evita la resolución DNS y generalmente bypasea el proxy corporativo.