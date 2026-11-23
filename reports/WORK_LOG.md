# Lethal Company Mobile — Engineering work log

Fecha de checkpoint: 2026-11-22 (America/New_York)
Repositorio: https://github.com/gerardodelatorredjg2-bit/telegram-apk-analysis-
Rama de trabajo principal: main
Commit main al crear este checkpoint: c45283072395b4bf1d0c4840807dc8bb5547f7bc

## Estado ejecutivo

La auditoría confirma que el repositorio contiene una APK Unity IL2CPP original preservada, datos de análisis IL2CPP/Ghidra, inventarios Unity, scripts de empaquetado y recursos SVG para controles móviles. No contiene el proyecto Unity editable completo (Assets/Packages/ProjectSettings) ni el código fuente C# del runtime móvil propio. Por tanto, los recursos SVG aún no están conectados a los botones del juego y las reparaciones de lógica de cámara, HUD, chat, terminal y audio no pueden declararse resueltas por esta auditoría estática.

La build #17 (workflow run 45075247285) NO se selecciona como base para reparaciones visuales. El trabajo siguiente debe partir de la APK original preservada.

## Base preservada y procedencia

- Artefacto original: `original-apk`, Actions run 45057515185, artifact 14767109709.
- Tamaño del APK extraído: 537,154,325 bytes.
- SHA-256 calculado localmente y coincidente con `original.apk.sha256`: `89aee1fb35b8367c79b5c49e878ce9aff2247f7a747f0942ea9a38fb87e7df28`.
- Package ID: `com.local.lethaloffline.fullgame`.
- Versión observada por AAPT en la prueba de cámara: versionCode 5, versionName `1.3-unlimited-stamina`.
- Label observado: `Lethal Offline Experimentation`.
- SDK observado: min 29, target 35, compile 35.
- ABIs: `arm64-v8a` y `armeabi-v7a`.
- Actividad lanzadora: `com.unity3d.player.UnityPlayerActivity`.
- La APK original se conserva sin modificar en el entorno de auditoría. Nunca se sobrescribe con una salida.

## Inventario y análisis recuperado

- Rama auditada inicialmente: `main`, commit `8891f5b8abfd98b0b40b1bf98e5ba3a602055d99`. La actualización posterior del workflow de descarga quedó en el commit `c45283072395b4bf1d0c4840807dc8bb5547f7bc`.
- Releases publicados: no había releases al auditar.
- Unity: informe técnico registra Unity 2022.3.62f2. El encabezado del dump IL2CPP de Il2CppDumper declara 2022.3.62a0; discrepancia pendiente de aclarar.
- IL2CPP: workflow run 45095321554, concluido correctamente; Dumper exit code 0. Dump ARM64/metadata v31.1, 113 assemblies, 15,377 tipos, 118,523 métodos, 73,700 campos y 23,328 literales de cadena.
- Ghidra: workflow run 45098104756, concluido correctamente. Decompiló 70 métodos seleccionados, 0 fallos de decompilación. El log reporta 296 símbolos importados no resueltos y una advertencia de creación de función thunk; el resultado no equivale a reconstruir el código fuente.
- Escenas Unity: 19 escenas (level0–level18); inventario técnico indica 31 Camera y 231 Light.
- Runtime móvil: existen métodos IL2CPP para construir controles de gameplay y terminal, actualizar acciones/teclado/chat, ajustar safe area, y un layout editable persistido mediante PlayerPrefs. La existencia de estos métodos no prueba que cada interacción táctil funcione.
- Recursos HUD: los SVG existen como fuentes vectoriales, pero README declara expresamente que todavía no están conectados al runtime APK. Chat/settings en el diseño documentado aparecen en columna superior derecha; mover chat a izquierda requeriría cambio de runtime/layout, no solo sustituir icono.
- Splash: configuración serializada registra Unity splash habilitado y tres entradas propias (título, emblema, aviso de luces). No se ha demostrado que sean logos duplicados.
- Fog: el informe de volumen encontró clases Fog (13), LocalVolumetricFog (47), Volume (75), LensDistortion (11), entre otros. Muchas instancias pertenecen a escenas/volúmenes concretos. El inventario de RenderSettings informa m_Fog=false en las escenas de muestra; el sistema relevante es HDRP/Volumes, cuyos campos aún no están tipados en el informe. No se debe cambiar el RenderSettings clásico ni apagar todos los volúmenes a ciegas.
- Cámara: level3 contiene cámaras de jugadores, spectator, visor, mapa y cámaras auxiliares. La cámara de mapa no se debe tocar como si fuese una cámara de jugador. La auditoría serializada no muestra por sí sola el comportamiento runtime.
- Scripts en `patches/`: fog/lens/spectator/audio/geometry/bug-triage son preparatorios o de lectura; no son parches de juego aplicados. No deben presentarse como correcciones terminadas.

## Build #17 — no usar como base visual

Workflow run 45075247285, build móvil LOW:
- 143 texturas redimensionadas a máximo 1024 px por lado (con exclusiones UI); 12 texturas omitidas.
- Bytes codificados antes/después estimados por el informe: 566,800,617 / 145,869,248; ahorro estimado 420,931,369 bytes.
- Se deshabilitaron globalmente 13 componentes Fog, 40 LocalVolumetricFog y 11 LensDistortion (64 en total).
- El round-trip estático verifica que se releen las 143 texturas y que los componentes seleccionados quedan desactivados. Esto NO demuestra calidad visual ni corrección de fog/distorsión en juego.
- Esa desactivación general puede eliminar volúmenes ambientales que tienen función específica por escena. Se rechaza como base de la reparación visual.

## Candidato A/B de cámara generado desde la original

Workflow: [Build original-fidelity camera probe](https://github.com/gerardodelatorredjg2-bit/telegram-apk-analysis-/actions/runs/45090036861).
Artifact: `lethal-offline-original-fidelity-camera-probe` (ID 14780562572).

Cambio único:
- Cuatro objetos `MainCamera` de la escena `level3`.
- `m_NearClipPlane`: 0.05 → 0.10.
- Archivo Unity serializado modificado: `level3`.
- SHA-256 del `level3` modificado: `435442206505dffd1f94d763e61f687bd3c33161802c22c3d2ca033dd6d8da12`.
- SHA-256 del APK unsigned: `956318e38c4e069f3d813ec6b0a552839994b8f7741b659cece7912e357b34dc`.
- El informe declara preservados texturas/mipmaps, mallas, materiales, shaders, luces, sombras, fog, audio, networking y gameplay binaries; solo se reemplazó el asset serializado `level3` y se retiró la firma JAR antigua para poder volver a firmar.
- CI: UnityPy patch, zipalign, apksigner y `unzip -t` terminaron correctamente. AAPT validó package/version/ABIs. Firma v3 verificada.
- SHA-256 del certificado de firma de prueba: `56e37e6879e39278c2d93c59bd46f148c88458e8ad2533d3b362c32b9cbc22db`.
- El candidato requiere desinstalar antes una APK firmada con otra clave.
- LIMITACIÓN: no se ha instalado ni probado en un dispositivo. No se declara arreglado el artefacto negro; este es un A/B aislado para comprobar clipping. No cambia fog, spectator, chat, terminal, HUD, audio, micrófono ni multijugador.

## Entrega del candidato

- El artefacto original de cámara excede ligeramente el máximo del conector de descarga (537,159,349 bytes frente al límite 536,870,912).
- Se añadieron workflows de empaquetado multipartes para dividir el paquete 7z en dos volúmenes de 350 MiB, sin modificar el juego.
- Commit de empaquetado en main: `c45283072395b4bf1d0c4840807dc8bb5547f7bc`.
- CI principal de empaquetado: run 45102170227; rama de empaquetado alternativa: `work/camera-probe-download-split`, run 45102143614. En este checkpoint la creación de volúmenes estaba en curso; no se deben marcar como entregados hasta verificar ambos artifacts y sus checksums.

## Matriz de pruebas

| Área | Estado | Evidencia / límite |
|---|---|---|
| APK original + SHA-256 | PASS | Hash coincide con checksum adjunto |
| IL2CPP dump | PASS | workflow 45095321554; exit code 0 |
| Ghidra métodos seleccionados | PASS | workflow 45098104756; 70/70 decompilados |
| Cambio serializado de cámara | PASS estático | 4 cámaras cambiadas; round-trip 4/4 |
| ZIP alignment + firma de prueba | PASS | workflow 45090036861; apksigner v3 |
| Integridad ZIP APK candidata | PASS | `unzip -t`: sin errores |
| Instalación/arranque Android | NOT TESTED | No dispositivo/ADB disponible en el entorno |
| Caminar y reproducir artefacto negro | NOT TESTED | Requiere A/B físico |
| Fog/iluminación/fisheye en runtime | NOT TESTED | Requiere ejecución y captura comparativa |
| Muerte/espectador | NOT TESTED | Método IL2CPP identificado; lógica no parcheada |
| HUD/joystick/sprint/crouch/jump/flashlight/scan | NOT TESTED | Runtime existe; SVG no integrados |
| Chat/teclado | NOT TESTED | Se localizó lógica de teclado; ubicación/UX no modificada |
| Terminal táctil | NOT TESTED | BuildTerminalControls existe; no validación interactiva |
| Muebles/prompts | NOT TESTED | Métodos contextuales existen; sin test |
| Audio/micrófono/voz | NOT TESTED | Inventario estático solamente |
| Multijugador/voice chat | NOT TESTED | No se ejecutó con dos clientes |
| Seguridad dinámica/antimalware | NOT TESTED | Solo revisión estática parcial |

## Bloqueos y próximos pasos

1. Completar y verificar los artifacts multipartes, descargar el candidato y extraer sus checksums.
2. Pedir prueba física A/B de la cámara (mismo teléfono, misma escena y ruta, caminando hacia/contra geometría) antes de aceptar/rechazar el cambio near-clip.
3. Seguir con investigación de spectator en PlayerControllerB/SpectateNextPlayer; la función tiene muchas ramas e indirect calls, por lo que no debe parchearse con offsets supuestos.
4. Recuperar el proyecto Unity editable o fuentes C# y dependencias del runtime personalizado para conectar los SVG V4 y cambiar el layout de chat con eventos reales. Sin eso, no se puede recompilar de forma fiable los assemblies administrados propios.
5. Resolver la discrepancia de versión Unity 2022.3.62f2 vs 2022.3.62a0.
6. Construir una herramienta de tipetree para leer los HDRP VolumeProfiles por escena y probar cambios pequeños sobre una copia de la original; no modificar fog por RenderSettings si m_Fog está desactivado.
7. Hacer pruebas físicas de terminal/chat/audio/mic/multiplayer y rotación/safe area.
8. Entregar un APK final solo cuando los cambios sean reales, firmados, comprobados y acompañados por resultados de prueba reproducibles.

## Regla de aceptación

Este checkpoint es una auditoría con un candidato de cámara para prueba A/B. No es una release final y no marca como corregidos los bugs reportados. Mantener intacta la APK original y usarla como única base fiable hasta que pruebas comparativas justifiquen otra cosa.
