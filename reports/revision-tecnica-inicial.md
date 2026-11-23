# Revisión técnica inicial — Lethal Offline

Fecha de revisión: 2026-11-23  
APK de referencia: artefacto original, Unity 2022.3.62f2  
Paquete: `com.local.lethaloffline.fullgame`

## Base y reglas de la siguiente revisión

- La siguiente compilación debe partir del APK original, no de la variante Mobile Low Build #17.
- No reducir ni recomprimir texturas, mallas, audio ni animaciones.
- No desactivar globalmente los componentes HDRP de niebla. La compilación #17 desactivó 13 componentes `Fog`, 40 `LocalVolumetricFog` y 11 `LensDistortion`; ese cambio global no está demostrado como correcto y no se debe usar como base de una reparación visual.
- No forzar un perfil gráfico que apague sombras, luces por píxel o reflection probes.
- Mantener intactos los recursos multijugador, micrófono y chat mientras no exista una prueba específica que justifique cambiarlos.

## Inspección estática completada

La auditoría serializada del APK original encontró:

- 19 escenas Unity (`level0` a `level18`).
- 31 componentes Camera.
- 231 componentes Light.
- La escena `level3` contiene la cámara de espectador, cámaras principales de los jugadores, cámaras de visor, cámara del mapa y cámaras de seguridad/nave.
- Las cámaras principales de los jugadores aparecen deshabilitadas en el estado serializado; la activación y el cambio entre cámaras dependen de lógica de ejecución. Esto debe probarse en el juego, no corregirse editando únicamente el valor serializado.
- `MapCamera` tiene un plano cercano negativo; es una cámara auxiliar de mapa y no debe alterarse sin comprobar su uso real.
- La auditoría no ejecutó el juego en tiempo real y no demuestra que las escenas funcionen correctamente.

## Inicio y logos

En `PlayerSettings` del APK original se observan:

- `m_ShowUnitySplashScreen = true`
- `m_ShowUnitySplashLogo = true`
- Tres entradas configuradas en `m_SplashScreenLogos`, de dos segundos cada una.

La extracción visual identificó las tres imágenes configuradas: la primera es el logotipo/título del juego (Sprite pathID 1198), la segunda es el emblema del perro de `@ZeekerssRBLX` (pathID 1199) y la tercera es el aviso `WARNING: FLASHING LIGHTS` (pathID 1200). El logo de Unity es una referencia separada (pathID 1197). Por tanto, los tres logos propios no son duplicados del logo de Unity; apagar `m_ShowUnitySplashLogo` eliminaría el único logo de Unity configurado, no una copia demostrada. Hay que confirmar si la segunda aparición que ve el usuario procede de otra pantalla de arranque antes de alterar estos ajustes.

## Controles móviles

El APK genera los controles en tiempo de ejecución desde `LethalOffline.MobileControls.MobileTouchControls`. El código IL2CPP expone los puntos funcionales:

- `BuildGameplayControls`
- `MakeActionButton` y `MakeButton`
- `UpdateActionButtons` y `UpdateExtraButtons`
- `IsLookingAtPlaceableShipObject`
- `BuildTerminalControls`

También existen componentes de joystick, botones contextuales e integración con terminal táctil. Por eso, cambiar únicamente las imágenes no conecta los iconos con las acciones. El conjunto SVG de `assets/mobile-controls/svg` y su vista estática son recursos de diseño; aún no están conectados al runtime de la APK.

## Pendientes que requieren prueba de ejecución

- Polígonos negros que aparecen al caminar: investigar cámara, clipping, culling, geometría y renderizado en movimiento.
- Iluminación interior y niebla azul: comprobar volúmenes, luces y el puente de atmósfera en tiempo real.
- Cámara de espectador al morir.
- Audio/micrófono: revisar cortes y continuidad de audio durante una partida.
- PC/terminal táctil, chat y contexto de mover/colocar mobiliario de la nave.
- Aviso de actualización: no se encontró una cadena inequívoca de diálogo de actualización en el catálogo de cadenas IL2CPP inspeccionado; localizar quién lo muestra antes de modificarlo.
- Pantalla de inicio: verificar la secuencia real de logos después de resolver los tres recursos configurados.

## Límite de reconstrucción actual

El repositorio contiene el APK, informes, herramientas de inspección y scripts de empaquetado; no contiene el proyecto Unity editable (`Assets/`, `Packages/`, `ProjectSettings/`) ni el código fuente C# del runtime móvil. La aplicación está compilada con IL2CPP: el volcado disponible describe tipos, campos y firmas, pero no recupera los cuerpos fuente de los métodos. Por tanto, no se puede afirmar que el juego haya sido reconstruido desde cero, que se haya ejecutado dentro del repositorio ni que los controles SVG estén integrados.

Para reescribir y compilar de forma verificable el runtime de cámara, controles, chat, terminal y audio hace falta el proyecto Unity editable original o sus fuentes C# y dependencias compatibles.
