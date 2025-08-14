// chat.js - Versión combinada con funcionalidades del backend y de la UI

// ================================
// 🔗 SECCIÓN: Variables globales
// ================================

var clientId
var speechRecognizer
var isSpeaking = false
var isListening = false
var isFirstRecognizingEvent = true
var statusWebRTC = 'firstConnection'
var isReconnecting = false
var recognitionStartedTime
var chatResponseReceivedTime
var sessionActive = false
var peerConnection
var isKeyboardActive = false
var headerTimeout
var lastMouseMoveTime = new Date()
var testModeActive = false
var lastSpeakTime
var firstTokenLatencyRegex = new RegExp(/<FTL>(\d+)<\/FTL>/)
var firstSentenceLatencyRegex = new RegExp(/<FSL>(\d+)<\/FSL>/)
let audioContext = null; // Inicializar fuera para alcance global

//Empezar la sesión apenas se carga la página
window.onload = function () {
    clientId = document.getElementById('clientId').value

    // Configurar estado inicial del modo de prueba
    document.getElementById("testMode").checked = false

    // Setup header auto-hide
    //setupHeaderAutoHide()

    // Setup message input
    setupMessageInput()

    // Seteo de intervalo para reconexión
    //setInterval(() => {
    //    checkHung()
    // console.log('Checkeo conexión de video remoto: checkHung')
    //}, 10000) // Check session activity every 2 seconds

    // Inicializar AudioContext pero no lo "resume" todavía
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    window.startSession();
    window.requestAudioVideoPermissions();
}

async function requestAudioVideoPermissions() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: true
        });
        console.log("Permisos otorgados");
        // Detener inmediatamente si solo querés los permisos y no usar el stream ahora
        stream.getTracks().forEach(track => track.stop());
    } catch (error) {
        console.error("Permiso denegado o error:", error);
        alert("Necesitamos permiso para usar micrófono y cámara.");
    }
}

// ================================
// 🔗 SECCIÓN: Funciones aux

function applyCorrections(text) {
    const corrections = {
        "ipf": "YPF",
        "Y griega P F": "YPF",
        "IPF": "YPF",
        "iipf": "YPF",
        "ypf": "YPF",
        "ypf.": "YPF",
        "latch": "LaCh",
        "lauch": "LaCh",
        "lage": "LaJe",
        "lagge": "LaCh",
        "lagh": "LaCh",
        "dns": "DLS",
        "de ls": "DLS",
        "d ls": "DLS",
        "bbm": "VM",
        "bm": "VM",
        "doble uv": "W",
        "uv": "V",
        "retik": "RTIC",
        "retic": "RTIC",
        "tic": "RTIC",
        "tik": "RTIC",
        "npc": "NPT",
        "cnpt": "NPT",
        "CNPT": "NPT",
        "ctp": "NPT",
        "CPT": "NPT",
        "daia": "DA&IA",
        "daya": "DA&IA",
        "d ls": "DLS",
        "d S": "DLS",
        "ds": "DLS",
        "dvds": "DLS",
        "BPE":"VPE",
        "bpe":"VPE",
        "VP":"VPE",
        "BP":"VPE",
        "BI PI":"VP",
        "bi pi":"VP",
        "VI PI":"VP",
        "Vi pi":"VP",
        "ATER":"TER",
        "ater":"TER",
        "Ater":"TER",
        "TED":"TER",
        "ted":"TER",
        "Halcón":"Hubcore",
        "Halcon":"Hubcore",
        "HALCON":"Hubcore",
        "Hub core":"Hubcore",
        "HUB CORE":"Hubcore"
        // Agregá más correcciones aquí
    };

    const regex = new RegExp("\\b(" + Object.keys(corrections).join("|") + ")\\b", "gi");

    return text.replace(regex, match => corrections[match.toLowerCase()] || match);
}

// ================================
// 🔗 SECCIÓN: Conectividad con Backend
// ================================

// === SpeechContext-PhraseDetection Configurations ===
// TrailingSilenceTimeout: Controla cuánto tiempo espera el reconocimiento antes de finalizar después de detectar un silencio.
// InitialSilenceTimeout: Define cuánto tiempo espera el sistema antes de cancelar si no se detecta habla al principio.
// Dictation.Segmentation.Mode: Controla cuánto tiempo espera el reconocimiento antes de finalizar después de detectar un silencio.
// Dictation.Segmentation.SegmentationSilenceTimeoutMs: Controla el umbral de silencio para segmentar frases en dictado.

function createSpeechRecognizer() {
    if (testModeActive) return; // No crear reconocedor en modo prueba

    fetch('/api/getSpeechToken', {
        method: 'GET',
    })
        .then(response => {
            if (response.ok) {
                
                const speechRegion = response.headers.get('SpeechRegion')
                const speechPrivateEndpoint = response.headers.get('SpeechPrivateEndpoint')
                response.text().then(text => {
                    const speechToken = text
                    const speechUrl  = speechPrivateEndpoint ? `wss://${speechPrivateEndpoint.replace('https://', '')}stt/speech/universal/v2`  : `wss://${speechRegion}.stt.speech.microsoft.com/speech/universal/v2`;
                    const speechRecognitionConfig = SpeechSDK.SpeechConfig.fromEndpoint(new URL(speechUrl)) 
                    speechRecognitionConfig.authorizationToken = speechToken
                    speechRecognitionConfig.setProperty(SpeechSDK.PropertyId.SpeechServiceConnection_LanguageIdMode, "Continuous")
                    speechRecognitionConfig.setProperty("SpeechContext-PhraseDetection.TrailingSilenceTimeout", "15000") // 15000
                    speechRecognitionConfig.setProperty("SpeechContext-PhraseDetection.InitialSilenceTimeout", "10000") // 10000
                    speechRecognitionConfig.setProperty("SpeechContext-PhraseDetection.Dictation.Segmentation.Mode", "None") //Custom
                    speechRecognitionConfig.setProperty("SpeechContext-PhraseDetection.Dictation.Segmentation.SegmentationSilenceTimeoutMs", "5000") // 1000
                    var sttLocales = document.getElementById('sttLocales').value.split(',')
                    var autoDetectSourceLanguageConfig = SpeechSDK.AutoDetectSourceLanguageConfig.fromLanguages(sttLocales)
                    speechRecognizer = SpeechSDK.SpeechRecognizer.FromConfig(speechRecognitionConfig, autoDetectSourceLanguageConfig, SpeechSDK.AudioConfig.fromDefaultMicrophoneInput())
                })
            } else {
                throw new Error(`Failed fetching speech token: ${response.status} ${response.statusText}`)
            }
        })
}


// Handle user query. Send user query to the chat API and display the response.
function handleUserQuery(userQuery) {
    let chatRequestSentTime = new Date()
    fetch('/api/chat', {
        method: 'POST',
        headers: {
            'ClientId': clientId,
            'SystemPrompt': document.getElementById('prompt').value,
            'Content-Type': 'text/plain'
        },
        body: userQuery
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Chat API response status: ${response.status} ${response.statusText}`)
            }

            let chatHistoryTextArea = document.getElementById('chatHistory')
            const assistantBubble = document.createElement("div");
            assistantBubble.className = "chat-bubble assistant";
            assistantBubble.innerHTML = `
            <div class="avatar-assistant">
                <img src="static/image/avatar-assistant.png" alt="harry-icon">
            </div>
            <div class="bubble"><span id="bot-msg-last"></span></div>
            `;

            chatHistoryTextArea.appendChild(assistantBubble);

            const reader = response.body.getReader()
            // Function to recursively read chunks from the stream
            function read() {
                return reader.read().then(({ value, done }) => {
                    // Check if there is still data to read
                    if (done) {
                        // Stream complete
                        return
                    }

                    // Process the chunk of data (value)
                    let chunkString = new TextDecoder().decode(value, { stream: true })

                    if (firstTokenLatencyRegex.test(chunkString)) {
                        let aoaiFirstTokenLatency = parseInt(firstTokenLatencyRegex.exec(chunkString)[0].replace('<FTL>', '').replace('</FTL>', ''))
                        chunkString = chunkString.replace(firstTokenLatencyRegex, '')
                        if (chunkString === '') {
                            return read()
                        }
                    }
                    if (firstSentenceLatencyRegex.test(chunkString)) {
                        let aoaiFirstSentenceLatency = parseInt(firstSentenceLatencyRegex.exec(chunkString)[0].replace('<FSL>', '').replace('</FSL>', ''))
                        chatResponseReceivedTime = new Date()
                        let chatLatency = chatResponseReceivedTime - chatRequestSentTime
                        let appServiceLatency = chatLatency - aoaiFirstSentenceLatency
                        let latencyLogTextArea = document.getElementById('latencyLog')
                        latencyLogTextArea.innerHTML += `App service latency: ${appServiceLatency} ms\n`
                        latencyLogTextArea.innerHTML += `AOAI latency: ${aoaiFirstSentenceLatency} ms\n`
                        latencyLogTextArea.scrollTop = latencyLogTextArea.scrollHeight
                        chunkString = chunkString.replace(firstSentenceLatencyRegex, '')
                        if (chunkString === '') {
                            return read()
                        }
                    }
                    // Seleccionar específicamente la última burbuja del asistente
                    const assistantBubbles = document.querySelectorAll('.chat-bubble.assistant');
                    const lastAssistantBubble = assistantBubbles[assistantBubbles.length - 1];
                    const targetSpan = lastAssistantBubble.querySelector('span[id="bot-msg-last"]');
                    targetSpan.innerHTML += `${chunkString}`;
                    chatHistoryTextArea.scrollTop = chatHistoryTextArea.scrollHeight

                    // Continue reading the next chunk
                    return read()
                })
            }
            // Start reading the stream
            return read()
        })
}

// ================================
// 🎤 SECCIÓN: Toggle Micrófono y Reconocimiento
// ================================

window.stopSpeaking = () => {

    if (speechRecognizer && isListening) {
        // Detengo el microfono
        window.toggleMicrophone()
        isListening = false
        return;
    }
    if (isSpeaking) {
        // Deshabilitar el botón temporalmente para evitar múltiples clics
        const stopButton = document.getElementById("stopButton")
        stopButton.disabled = true

        // Detener la completación de texto en ChatHistory
        if (window.currentTextStream) {
            window.currentTextStream.cancel()
        }

        fetch("/api/stopSpeaking", {
            method: "POST",
            headers: {
                ClientId: clientId,
            },
            body: "",
        })
            .then((response) => {
                if (response.ok) {
                    // Ocultar animación de ondas sonoras
                    isSpeaking = false
                    toggleSoundWave(false)
                } else {
                    throw new Error(`Failed to stop speaking: ${response.status} ${response.statusText}`)
                }
            })
            .finally(() => {
                // Habilitar el botón nuevamente después de un breve retraso
                setTimeout(() => {
                    stopButton.disabled = false
                }, 200)
            })
        return;
    } else {
        console.log("El avatar no está hablando, no es necesario detenerlo.");
        return;
    }
}

window.toggleMicrophone = () => {
    const micButton = document.getElementById('microphone')

    // Manejar audioContext para permitir la reproducción del audio del avatar
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    audioContext.resume().then(() => {
        console.log('AudioContext resumed after toggleMicrophone.');
    }).catch(error => {
        console.error('Error resuming audio context:', error);
    });
    // if (audioContext.state === 'suspended') {
    //     audioContext.resume().then(() => {
    //         console.log('AudioContext resumed after toggleMicrophone.');
    //     }).catch(error => {
    //         console.error('Error resuming audio context:', error);
    //     });
    // }

    if (statusWebRTC == 'disconnected') {
        sessionActive = true;
        // Mostrar la rueda de carga
        isReconnecting = true;
        showLoadingSpinner()
        //document.getElementById('microphone').disabled = true;
        speechRecognizer.stopContinuousRecognitionAsync()
        speechRecognizer.close()

        try {
            createSpeechRecognizer()
            connectAvatar() // Esperar a que termine la conexión con el avatar
            console.log("Avatar conectado correctamente.");
            // Ocultar la rueda de carga

            setTimeout(() => {
                // Habilitar elementos solo cuando el avatar esté listo
                document.getElementById('startSession').disabled = true;
                document.getElementById('stopSession').disabled = false;
                document.getElementById('stopButton').disabled = false;
                document.getElementById('clearChatHistory').disabled = false;
                document.getElementById('keyboardToggle').disabled = false;
                document.getElementById('chatHistory').hidden = false;
                //document.getElementById("localVideo").hidden = false;
                document.getElementById('videoContainer').hidden = false;
                document.getElementById('configuration').hidden = true
            }, 5000)

        } catch (error) {
            console.error("Error conectando al avatar:", error);
            hideLoadingSpinner();
            stopSession();
            return;  // Detener la ejecución si falla la conexión
        }
    }
    else if (speechRecognizer && isListening) {
        micButton.classList.remove("success")
        micButton.innerHTML = `
                                                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
														   
                                    <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path>
                                    <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                                    <line x1="12" y1="19" x2="12" y2="22"></line>
															
                                </svg>
                                `
        // Ocultar animación de ondas sonoras
        toggleSoundWave(false)
        speechRecognizer.stopContinuousRecognitionAsync(
            () => {
                // Callback de éxito
                isListening = false
                isSpeaking = false;
                isFirstRecognizingEvent = false;
            },
            (err) => {
                console.error("Error al detener reconocimiento:", err);
            }
        );
    }
    else {
        // Modo normal con backend
        if (!speechRecognizer) {
            createSpeechRecognizer()
        }
        // Abris Mic
        recognitionStartedTime = new Date()
        // Conexion a video avatar
        //if (document.getElementById('useLocalVideoForIdle').checked) {
        //    if (!sessionActive) {
        //        connectAvatar()
        //    }

        //    setTimeout(() => {
        //        document.getElementById('audioPlayer').play()
        //    }, 5000)
        //} else {
        //    document.getElementById('audioPlayer').play()
        //}
        speechRecognizer.startContinuousRecognitionAsync(
            () => {
                isListening = true
                isSpeaking = false

                micButton.classList.add("success")
                micButton.disabled = false
                // Añadir efectos visuales
                createSoundParticles(micButton)
                // Mostrar animación de ondas sonoras
                toggleSoundWave(true)
            },
            (err) => {
                console.error("Error al iniciar reconocimiento:", err)
                micButton.disabled = false
            }
        )
        micButton.disabled = false
        micButton.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="1.5rem" height="1.5rem"
                    viewBox="0 0 24 24" fill="none"
                    stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="6" y1="9" x2="6" y2="15"></line>
                <line x1="9" y1="5.5" x2="9" y2="18.5"></line>
                <line x1="12" y1="3" x2="12" y2="21"></line>
                <line x1="15" y1="5.5" x2="15" y2="18.5"></line>
                <line x1="18" y1="9" x2="18" y2="15"></line>
                </svg>
        `
        speechRecognizer.recognizing = (s, e) => {
            // Solo lógica de monitoreo si es necesario, sin llamar a toggleMicrophone()
            console.log("Reconociendo Voz...");
        };

        speechRecognizer.recognized = async (s, e) => {
            if (e.result.reason === SpeechSDK.ResultReason.RecognizedSpeech) {
                isListening = false;
                isSpeaking = true;
                let userQuery = e.result.text.trim()
                // Filtrar Ruido
                const greetingWords = ["hola", "chau"];
                const isNoiseInput = userQuery.trim().length <= 5 && /^[A-Za-zÁÉÍÓÚÜáéíóúüÑñ\s.?!]*$/.test(userQuery) && !greetingWords.some(word => userQuery.toLowerCase().includes(word));
                if (isNoiseInput || userQuery === ' ') {
                    return
                }

                //Reemplazar palabras clave
                userQuery = applyCorrections(userQuery)
                let chatHistoryTextArea = document.getElementById('chatHistory')
                const userBubble = document.createElement("div");
                userBubble.className = "chat-bubble user";
                userBubble.innerHTML = `
                <div class="bubble">${userQuery}</div>
                <div class="avatar-user">
                            <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="7" r="4" />
                            <path d="M5.5 21c0-3.59 3.14-6.5 6.5-6.5s6.5 2.91 6.5 6.5" />
                            </svg>
                </div>
                `

                chatHistoryTextArea.appendChild(userBubble);
                chatHistoryTextArea.scrollTop = chatHistoryTextArea.scrollHeight
                let mytext = "User:" + userQuery + '\n\n'

                // Envío del texto al Backend
                handleUserQuery(userQuery)

                isFirstRecognizingEvent = true

                // Lógica del avatar cuando está hablando
                if (isSpeaking) {
                    micButton.classList.remove("success")

                    micButton.innerHTML = `
                        <svg xmlns="http://www.w3.org/2000/svg" width="1rem" height="1rem" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="1" y1="1" x2="23" y2="23"></line>
                            <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"></path>
                            <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"></path>
                            <line x1="12" y1="19" x2="12" y2="23"></line>
                            <line x1="8" y1="23" x2="16" y2="23"></line>
                        </svg>
                    `

                    // Ocultar animación de ondas sonoras
                    toggleSoundWave(false)
                    if (!testModeActive && speechRecognizer) {
                        speechRecognizer.stopContinuousRecognitionAsync(
                            () => {
                                // Callback de éxito

                                isSpeaking = false;
                                isFirstRecognizingEvent = false;
                                toggleSoundWave(false);
                            },
                            (err) => {
                                console.error("Error al detener reconocimiento:", err);
                            }
                        );
                    }
                    return
                }
            }
        }
        return false;
    }


    // Elimina o modifica el manejador recognizing

}


// ================================
// 📹 SECCIÓN: WebRTC y Avatar
// ================================

// Setup WebRTC

function setupWebRTC(iceServerUrl, iceServerUsername, iceServerCredential) {
    // Create WebRTC peer connection
    peerConnection = new RTCPeerConnection({
        iceServers: [{
            urls: [iceServerUrl],
            username: iceServerUsername,
            credential: iceServerCredential
        }],
        iceTransportPolicy: 'relay'
    })

    // Fetch WebRTC video stream and mount it to an HTML video element
    peerConnection.ontrack = function (event) {
        if (event.track.kind === 'audio') {
            let audioElement = document.createElement('audio')
            audioElement.id = 'audioPlayer'
            audioElement.srcObject = event.streams[0]
            audioElement.muted = false
            audioElement.autoplay = false

            // Clean up existing audio element if there is any
            remoteVideoDiv = document.getElementById('remoteVideo')
            for (var i = 0; i < remoteVideoDiv.childNodes.length; i++) {
                if (remoteVideoDiv.childNodes[i].localName === event.track.kind) {
                    remoteVideoDiv.removeChild(remoteVideoDiv.childNodes[i])
                }
            }

            // Append the new audio element
            document.getElementById('remoteVideo').appendChild(audioElement)

            const audioTracks = audioElement.srcObject.getAudioTracks();
            // Comprobar que esté habilitado el audio track
            console.log("Audio habilitado:", audioTracks[0]?.enabled);
            event.track.enabled = true; // asegura que el audio esté activo
            console.log("Audio habilitado:", audioTracks[0]?.enabled);

            let audioContextSuccess = false;
            try {
                if (!audioContext) {
                    audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    audioContext.resume();
                }

                const source = audioContext.createMediaStreamSource(audioElement.srcObject);
                source.connect(audioContext.destination);
                console.log("Audio reproduciéndose a través de AudioContext.");
                audioContextSuccess = true;

            } catch (contextError) {
                console.error("Error al inicializar AudioContext:", contextError);
                console.warn("Intentando reproducción con audioElement.play()");
                if (!audioContextSuccess) {
                    audioElement.play().catch(playError => {
                        if (playError.name === 'NotAllowedError') {
                            console.warn('Reproducción de audio bloqueada: se requiere interacción del usuario.');
                        } else {
                            console.error('Error al reproducir audio:', playError);
                        }
                    });
                }
            }
        }

        if (event.track.kind === 'video') {
            const videoElement = document.createElement("video")
            videoElement.id = 'videoPlayer'
            videoElement.srcObject = event.streams[0]
            videoElement.muted = true
            videoElement.autoplay = true
            videoElement.playsInline = true

            // Primero limpia elementos de video existentes
            const remoteVideoDiv = document.getElementById("remoteVideo")
            for (var i = 0; i < remoteVideoDiv.childNodes.length; i++) {
                if (remoteVideoDiv.childNodes[i].localName === event.track.kind) {
                    remoteVideoDiv.removeChild(remoteVideoDiv.childNodes[i])

                }
            }
            // Luego añade el nuevo elemento de video al DOM ANTES de definir onplaying
            document.getElementById("remoteVideo").appendChild(videoElement)

            const videoTracks = videoElement.srcObject.getVideoTracks();
            // Comprobar que esté habilitado el audio track
            console.log("Video habilitado:", videoTracks[0]?.enabled);
            event.track.enabled = true; // asegura que el audio esté activo
            console.log("Video habilitado:", videoTracks[0]?.enabled);

            videoElement.onplaying = () => {
                document.getElementById('stopSession').disabled = false
                document.getElementById('remoteVideo').hidden = false
                document.getElementById('chatHistory').hidden = false
                document.getElementById('latencyLog').hidden = true

                if (document.getElementById('useLocalVideoForIdle').checked) {
                    document.getElementById('localVideo').hidden = true
                    if (lastSpeakTime === undefined) {
                        lastSpeakTime = new Date()
                    }
                }

                setTimeout(() => { sessionActive = true }, 5000) // Set session active after 5 seconds
            }

            //Forzar reproducción para disparar `onplaying` si no lo hace automáticamente
            videoElement.play()
                .then(() => {
                    console.log("✅ Video reproducido forzadamente con éxito.");
                })
                .catch(error => {
                    console.warn("⚠️ No se pudo reproducir el video automáticamente:", error);
                });
        }
    }

    // Listen to data channel, to get the event from the server
    peerConnection.addEventListener("datachannel", event => {
        const dataChannel = event.channel
        dataChannel.onmessage = e => {

            if (e.data.includes("EVENT_TYPE_SWITCH_TO_SPEAKING")) {
                if (chatResponseReceivedTime !== undefined) {
                    let speakStartTime = new Date()
                    let ttsLatency = speakStartTime - chatResponseReceivedTime
                    let latencyLogTextArea = document.getElementById('latencyLog')
                    latencyLogTextArea.innerHTML += `TTS latency: ${ttsLatency} ms\n\n`
                    latencyLogTextArea.scrollTop = latencyLogTextArea.scrollHeight
                    chatResponseReceivedTime = undefined
                }

                isSpeaking = true
                document.getElementById('microphone').disabled = false
            } else if (e.data.includes("EVENT_TYPE_SWITCH_TO_IDLE")) {
                isSpeaking = false
                lastSpeakTime = new Date()
            }
        }
    })

    // This is a workaround to make sure the data channel listening is working by creating a data channel from the client side
    c = peerConnection.createDataChannel("eventChannel")

    // Make necessary update to the web page when the connection state changes
    peerConnection.oniceconnectionstatechange = e => {
        console.log("WebRTC status: " + peerConnection.iceConnectionState)
        if (peerConnection.iceConnectionState === 'connected') {
            console.log('EL PEERCONECTION ESTA CONECTADO')
            statusWebRTC = 'connected'
            isReconnecting = false
            //document.getElementById('microphone').disabled = false;
            if (document.getElementById('useLocalVideoForIdle').checked) {
                document.getElementById('remoteVideo').hidden = false
                //document.getElementById('localVideo').hidden = true
            }
            hideLoadingSpinner()
        }
        if (peerConnection.iceConnectionState === 'disconnected') {
            console.log('EL PEERCONECTION ESTA DESCONECTADO')
            statusWebRTC = 'disconnected'

            if (document.getElementById('useLocalVideoForIdle').checked) {
                document.getElementById('localVideo').hidden = false
                document.getElementById('remoteVideo').hidden = true
            }
            showLoadingSpinner()
            setTimeout(() => {
                hideLoadingSpinner()
                isReconnecting = true
            }, 3000);
        }
        else {
            statusWebRTC = 'checking'
        }

    }

    // Offer to receive 1 audio, and 1 video track
    peerConnection.addTransceiver('video', { direction: 'sendrecv' })
    peerConnection.addTransceiver('audio', { direction: 'sendrecv' })

    // Connect to avatar service when ICE candidates gathering is done
    iceGatheringDone = false

    peerConnection.onicecandidate = e => {
        if (!e.candidate && !iceGatheringDone) {
            iceGatheringDone = true
            connectToAvatarService(peerConnection)
        }
    }

    peerConnection.createOffer().then(sdp => {
        peerConnection.setLocalDescription(sdp).then(() => {
            setTimeout(() => {
                if (!iceGatheringDone) {
                    iceGatheringDone = true
                    connectToAvatarService(peerConnection)
                }
            }, 2000)
        })
    })
}

// Connect to TTS Avatar Service
function connectToAvatarService(peerConnection) {
    let localSdp = btoa(JSON.stringify(peerConnection.localDescription))
    let headers = {
        'ClientId': clientId,
        'AvatarCharacter': document.getElementById('talkingAvatarCharacter').value,
        'AvatarStyle': document.getElementById('talkingAvatarStyle').value,
        'IsCustomAvatar': document.getElementById('customizedAvatar').checked,
        'AoaiDeploymentName': document.getElementById('azureOpenAIDeploymentName').value
    }

    if (document.getElementById('azureOpenAIDeploymentName').value !== '') {
        headers['AoaiDeploymentName'] = document.getElementById('azureOpenAIDeploymentName').value
    }

    if (document.getElementById('enableOyd').checked && document.getElementById('azureCogSearchIndexName').value !== '') {
        headers['CognitiveSearchIndexName'] = document.getElementById('azureCogSearchIndexName').value
    }

    if (document.getElementById('backgroundImageUrl').value !== '') {
        headers['BackgroundImageUrl'] = document.getElementById('backgroundImageUrl').value
    }

    if (document.getElementById('ttsVoice').value !== '') {
        headers['TtsVoice'] = document.getElementById('ttsVoice').value
    }

    if (document.getElementById('customVoiceEndpointId').value !== '') {
        headers['CustomVoiceEndpointId'] = document.getElementById('customVoiceEndpointId').value
    }

    if (document.getElementById('personalVoiceSpeakerProfileID').value !== '') {
        headers['PersonalVoiceSpeakerProfileId'] = document.getElementById('personalVoiceSpeakerProfileID').value
    }

    fetch('/api/connectAvatar', {
        method: 'POST',
        headers: headers,
        body: localSdp
    })
        .then(response => {
            if (response.ok) {
                response.text().then(text => {
                    const remoteSdp = text
                    peerConnection.setRemoteDescription(new RTCSessionDescription(JSON.parse(atob(remoteSdp))))
                })
            } else {
                document.getElementById('startSession').disabled = false;
                document.getElementById('configuration').hidden = false;
                throw new Error(`Failed connecting to the Avatar service: ${response.status} ${response.statusText}`)
            }
        })
}
// Connect to avatar service
async function connectAvatar() {
    document.getElementById('startSession').disabled = true
    fetch('/api/getIceToken', {
        method: 'GET',
    })
        .then(response => {
            if (response.ok) {
                response.json().then(data => {
                    const iceServerUrl = data.Urls[0]
                    const iceServerUsername = data.Username
                    const iceServerCredential = data.Password
                    if (peerConnection) {
                        peerConnection.close();
                        peerConnection = null;
                        statusWebRTC = 'firstConnection'
                    }
                    setupWebRTC(iceServerUrl, iceServerUsername, iceServerCredential)
                })
                // Seguir aca
            } else {
                throw new Error(`Failed fetching ICE token: ${response.status} ${response.statusText}`)
            }
        })
    document.getElementById('configuration').hidden = true
}


// Disconnect from avatar service
function disconnectAvatar(closeSpeechRecognizer = false) {
    fetch('/api/disconnectAvatar', {
        method: 'POST',
        headers: {
            'ClientId': clientId
        },
        body: ''
    })

    if (speechRecognizer !== undefined) {
        speechRecognizer.stopContinuousRecognitionAsync()
        if (closeSpeechRecognizer) {
            speechRecognizer.close()
        }
    }

    sessionActive = false
}

// ================================
// 🖥️ SECCIÓN: Funcionalidad Visual y Utilidades
// ================================

// Mostrar/ocultar animación de ondas sonoras
function toggleSoundWave(show) {
    const soundWaveContainer = document.getElementById("soundWaveContainer")
    const listeningIndicator = document.getElementById("listeningIndicator")

    if (show) {
        soundWaveContainer.classList.add("active")
        listeningIndicator.classList.add("active")
    } else {
        soundWaveContainer.classList.remove("active")
        listeningIndicator.classList.remove("active")
    }
}

window.toggleConfig = () => {
    const configPanel = document.getElementById("configuration");

    // Alternar la clase "active"
    configPanel.classList.toggle("active");

    // Mostrar u ocultar el panel según la clase "active"
    if (configPanel.classList.contains("active")) {
        configPanel.removeAttribute("hidden"); // Mostrar el panel
    } else {
        configPanel.setAttribute("hidden", ""); // Ocultar el panel
    }
};

// Toggle entrada por teclado
window.toggleKeyboard = () => {
    const keyboardButton = document.getElementById("keyboardToggle")
    const userMessageBox = document.getElementById("userMessageBox")
    //Manejar audioContext para permitir la reproducción del audio del avatar
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        audioContext.resume();
    }
    audioContext.resume().then(() => {
        console.log('AudioContext resumed after toggleMicrophone.');
    }).catch(error => {
        console.error('Error resuming audio context:', error);
    });
    // if (audioContext.state === 'suspended') {
    //     audioContext.resume().then(() => {
    //         console.log('AudioContext resumed after keyboard toggle.');
    //     }).catch(error => {
    //         console.error('Error resuming audio context:', error);
    //     });
    // }

    isKeyboardActive = !isKeyboardActive
    const sessionContainer = document.querySelector(".session-container");
    if (isKeyboardActive) {
        sessionContainer.classList.add("hidden");
        keyboardButton.classList.add("active")
        userMessageBox.hidden = false
    } else {
        sessionContainer.classList.remove("hidden");
        keyboardButton.classList.remove("active")
        userMessageBox.hidden = true
    }
}

// Manejar ocultamiento automático del header
// function setupHeaderAutoHide() {
//     // Configuración inicial
//     resetHeaderTimeout()

//     // Escuchar movimiento del ratón
//     document.addEventListener("mousemove", (e) => {
//         const header = document.getElementById("header")
//         const currentTime = new Date()

//         // Si el ratón está en los 50px superiores, mostrar header
//         if (e.clientY < 50) {
//             header.classList.remove("hidden")
//             resetHeaderTimeout()
//         } else if (currentTime - lastMouseMoveTime > 100) {
//             // Limitar para evitar llamadas excesivas
//             lastMouseMoveTime = currentTime
//             resetHeaderTimeout()
//         }
//     })
// }

// Reiniciar timeout del header
// function resetHeaderTimeout() {
//     const header = document.getElementById("header")
//     header.classList.remove("hidden")

//     clearTimeout(headerTimeout)
//     headerTimeout = setTimeout(() => {
//         header.classList.add("hidden")
//     }, 5000) // Ocultar después de 5 segundos de inactividad
// }

// Configuración de entrada de mensajes
function setupMessageInput() {
    const userMessageBox = document.getElementById("userMessageBox")

    userMessageBox.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            if (e.shiftKey) {
                // Permitir salto de línea
                return;
            }
            // Prevenir salto de línea por defecto
            e.preventDefault();
            const userQuery = userMessageBox.value.trim()
            if (userQuery !== "") {
                let chatHistoryTextArea = document.getElementById("chatHistory")
                const userBubble = document.createElement("div");
                userBubble.className = "chat-bubble user";
                userBubble.innerHTML = `
                <div class="bubble">${userQuery}</div>
                <div class="avatar-user">
                            <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="7" r="4" />
                            <path d="M5.5 21c0-3.59 3.14-6.5 6.5-6.5s6.5 2.91 6.5 6.5" />
                            </svg>
                </div>
                `

                chatHistoryTextArea.appendChild(userBubble);
                //chatHistoryTextArea.innerHTML += "User: " + userQuery + "\n\n"
                chatHistoryTextArea.scrollTop = chatHistoryTextArea.scrollHeight

                // Enviar la consulta al backend o simular en modo prueba
                handleUserQuery(userQuery)

                userMessageBox.value = ""
            }
        }
    })
}

window.clearChatHistory = () => {
    if (testModeActive) {
        document.getElementById("chatHistory").innerHTML = "Historial de chat limpiado.\n\n"
        return;
    }

    fetch('/api/chat/clearHistory', { method: 'POST', headers: { 'ClientId': clientId } })
        .then(() => document.getElementById('chatHistory').innerHTML = '')
}

window.updataEnableOyd = () => {
    document.getElementById('cogSearchConfig').hidden = !document.getElementById('enableOyd').checked
}

// window.updateTypeMessageBox = () => {
//     const showBox = document.getElementById('showTypeMessage').checked
//     document.getElementById('userMessageBox').hidden = !showBox
// }
window.updateTypeMessageBox = () => {
    if (document.getElementById('showTypeMessage').checked) {
        document.getElementById('userMessageBox').hidden = false
        document.getElementById('userMessageBox').addEventListener('keyup', (e) => {
            if (e.key === 'Enter') {
                audioContext.resume().then(() => {
                    console.log('AudioContext resumed after toggleMicrophone.');
                }).catch(error => {
                    console.error('Error resuming audio context:', error);
                });
                const userQuery = document.getElementById('userMessageBox').value
                if (userQuery !== '') {
                    let chatHistoryTextArea = document.getElementById('chatHistory')
                    if (chatHistoryTextArea.innerHTML !== '' && !chatHistoryTextArea.innerHTML.endsWith('\n\n')) {
                        chatHistoryTextArea.innerHTML += '\n\n'
                    }

                    chatHistoryTextArea.innerHTML += "User: " + userQuery.trim('\n') + '\n\n'
                    chatHistoryTextArea.scrollTop = chatHistoryTextArea.scrollHeight

                    if (isSpeaking) {
                        window.toggleMicrophone()
                    }

                    handleUserQuery(userQuery.trim('\n'))
                    document.getElementById('userMessageBox').value = ''
                }
            }
        })
    } else {
        document.getElementById('userMessageBox').hidden = true
    }
}

// Handle local video. If the user is not speaking for 15 seconds, switch to local video.
function handleLocalVideo() {
    if (lastSpeakTime === undefined) {
        return
    }
    let currentTime = new Date()
    if (currentTime - lastSpeakTime > 30000) {
        if (document.getElementById('useLocalVideoForIdle').checked && sessionActive && !isSpeaking) {
            disconnectAvatar()
            console.log('DESCONECTO EL AVATAR. PASO A LOCAL VIDEO')
            document.getElementById('localVideo').hidden = false
            document.getElementById('remoteVideo').hidden = true
            sessionActive = false
        }
    }
}
// Check whether the avatar video stream is hung
function checkHung() {
    // Check whether the avatar video stream is hung, by checking whether the video time is advancing
    let videoElement = document.getElementById('videoPlayer')
    if (videoElement !== null && videoElement !== undefined && sessionActive) {
        let videoTime = videoElement.currentTime
        setTimeout(() => {
            // Check whether the video time is advancing
            if (videoElement.currentTime === videoTime) {
                // Check whether the session is active to avoid duplicatedly triggering reconnect
                if (sessionActive) {
                    //sessionActive = false
                    if (document.getElementById('autoReconnectAvatar').checked) {
                        isReconnecting = true
                        document.getElementById('localVideo').hidden = false
                        document.getElementById('remoteVideo').hidden = true
                        showLoadingSpinner()
                        speechRecognizer.stopContinuousRecognitionAsync()
                        speechRecognizer.close()
                        createSpeechRecognizer()
                        if (peerConnection) {
                            peerConnection.close();
                            peerConnection = null;
                            statusWebRTC = 'firstConnection'
                            setupWebRTC(iceServerUrl, iceServerUsername, iceServerCredential)
                        }
                        //connectAvatar()
                    }
                }
            }
        }, 1000)
    }
}

window.updateLocalVideoForIdle = () => {
    if (document.getElementById("useLocalVideoForIdle").checked) {
        document.getElementById("showTypeMessageCheckbox").hidden = true
    } else {
        document.getElementById("showTypeMessageCheckbox").hidden = false
    }
}

// ================================
// 🚀 SECCIÓN: Control de Sesión
// ================================

window.startSession = async () => {

    sessionActive = true;
    document.getElementById("localVideo").hidden = false;
    // Mostrar la rueda de carga
    showLoadingSpinner();

    createSpeechRecognizer();
    document.getElementById('startSession').style.display = 'none';
    document.getElementById('stopSession').style.display = 'flex';
    try {
        await connectAvatar()  // Esperar a que termine la conexión con el avatar
        // Ocultar la rueda de carga
        setTimeout(() => {
            // Habilitar elementos solo cuando el avatar esté listo
            document.getElementById('startSession').disabled = true;
            document.getElementById('stopSession').disabled = false;
            document.getElementById('microphone').disabled = false;
            document.getElementById('stopButton').disabled = false;
            document.getElementById('clearChatHistory').disabled = false;
            document.getElementById('keyboardToggle').disabled = false;
            document.getElementById('chatHistory').hidden = false;
            document.getElementById('videoContainer').hidden = false;
            document.getElementById('configuration').hidden = true
            //hideLoadingSpinner();
        }, 8000)

    } catch (error) {
        console.error("Error conectando al avatar:", error);
        hideLoadingSpinner();
        stopSession();
        return;  // Detener la ejecución si falla la conexión
    }


    if (testModeActive) {
        document.getElementById("localVideo").hidden = false;
        const chatHistoryTextArea = document.getElementById("chatHistory");
        chatHistoryTextArea.innerHTML += "Sesión iniciada" + (testModeActive ? " en modo de prueba" : "") + ".\n\n";
        chatHistoryTextArea.scrollTop = chatHistoryTextArea.scrollHeight;
    }
};

// Función para mostrar la rueda de carga
function showLoadingSpinner() {
    // Fondo con blur
    const blurOverlay = document.createElement("div");
    blurOverlay.id = "overlayBlur";
    document.body.appendChild(blurOverlay);

    // Caja del spinner
    const loadingDiv = document.createElement("div");
    loadingDiv.id = "loadingSpinner";

    let message = "";
    if (isReconnecting && (statusWebRTC === 'disconnected' || statusWebRTC === 'checking')) {
        message = "Aguarde unos instantes. Reconectando a Neuro...";
    } else if (sessionActive && (statusWebRTC === 'disconnected' || statusWebRTC === 'checking')) {
        message = "Desconectando a Neuro...";
    } else if (sessionActive && statusWebRTC === 'firstConnection') {
        message = "Conectando con Neuro...";
    } else {
        message = "Desconectando a Neuro... Se perderá la memoria";
    }

    loadingDiv.innerHTML = `
        <div class="circular-loader"></div>
        <p>${message}</p>
    `;

    document.body.appendChild(loadingDiv);
}

// Función para ocultar la rueda de carga
function hideLoadingSpinner() {
    const spinner = document.getElementById('loadingSpinner');
    const overlay = document.getElementById('overlayBlur');
    if (spinner) spinner.remove();
    if (overlay) overlay.remove();
}

window.stopSession = () => {

    sessionActive = false
    statusWebRTC = 'firstConnection'
    disconnectAvatar(true)

    // Desactivar el micrófono si está activo
    if (isSpeaking) {
        window.toggleMicrophone(); // Esto desactivará el micrófono y cambiará el ícono a "muteado"
    }

    if (!testModeActive && peerConnection) {
        peerConnection.close()
        peerConnection = null
    }

    // Limpieza visual al finalizar la sesión
    document.getElementById('remoteVideo').innerHTML = ''
    document.getElementById('chatHistory').innerHTML = ''

    //Muestro sppiner
    showLoadingSpinner();
    setTimeout(() => {
        document.getElementById('microphone').disabled = true;
        document.getElementById('stopButton').disabled = true;
        document.getElementById('clearChatHistory').disabled = true;
        document.getElementById('keyboardToggle').disabled = true;
        hideLoadingSpinner();
        document.getElementById('videoContainer').hidden = true
        document.getElementById('startSession').disabled = false;
        document.getElementById('startSession').style.display = 'flex';
        document.getElementById('stopSession').style.display = 'none';
    }, 5000)


    document.getElementById('startSession').disabled = false
    document.getElementById('stopSession').disabled = true
    if (document.getElementById('useLocalVideoForIdle').checked) {
        document.getElementById('localVideo').hidden = true
    }
    // Ocultar animación de ondas sonoras si está activa
    if (isSpeaking) {
        toggleSoundWave(false)
        isSpeaking = false
    }

    if (testModeActive) {
        // Añadir mensaje al historial de chat
        const chatHistoryTextArea = document.getElementById("chatHistory")
        chatHistoryTextArea.innerHTML += "Sesión finalizada.\n\n"
        chatHistoryTextArea.scrollTop = chatHistoryTextArea.scrollHeight
    }

}


//PARTICLES
// Función para animar las partículas de sonido
function animateSoundParticles() {
    const micButton = document.getElementById("microphone")

    // Solo animar si el micrófono está activo
    if (micButton.classList.contains("success")) {
        const particlesContainer = micButton.querySelector(".sound-particles")

        // Si no hay contenedor de partículas, crearlo
        if (!particlesContainer) {
            createSoundParticles(micButton)
        } else {
            // Actualizar posiciones aleatorias de las partículas
            const particles = particlesContainer.querySelectorAll(".particle")
            particles.forEach((particle) => {
                // Nuevas direcciones aleatorias
                const x = Math.random() * 2 - 1
                const y = Math.random() * 2 - 1

                particle.style.setProperty("--x", x)
                particle.style.setProperty("--y", y)

                // Reiniciar animación
                particle.style.animation = "none"
                particle.offsetHeight // Forzar reflow
                particle.style.animation = "particleAnimation 2s ease-out infinite"
                particle.style.animationDelay = `${Math.random() * 2}s`
            })
        }
    }

    // Continuar la animación
    requestAnimationFrame(animateSoundParticles)
}

// Función para crear el efecto de partículas para el botón de micrófono
function createSoundParticles(button) {
    // Eliminar contenedor de partículas existente si hay uno
    const existingContainer = document.querySelector(".sound-particles")
    if (existingContainer) {
        existingContainer.remove()
    }

    // Crear nuevo contenedor de partículas
    const particlesContainer = document.createElement("div")
    particlesContainer.className = "sound-particles"
    button.appendChild(particlesContainer)

    // Crear partículas
    for (let i = 0; i < 20; i++) {
        const particle = document.createElement("div")
        particle.className = "particle"

        // Posición aleatoria
        const x = Math.random() * 2 - 1 // -1 a 1
        const y = Math.random() * 2 - 1 // -1 a 1

        // Establecer variables CSS personalizadas para la animación
        particle.style.setProperty("--x", x)
        particle.style.setProperty("--y", y)

        // Retraso aleatorio para la animación
        particle.style.animationDelay = `${Math.random() * 2}s`

        particlesContainer.appendChild(particle)
    }

    return particlesContainer
}

// Autoresize del Text Input
const textarea = document.getElementById('userMessageBox');
textarea.addEventListener('input', () => {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
});