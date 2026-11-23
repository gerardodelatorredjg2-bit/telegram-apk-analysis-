# Camera probe A/B test plan

## Purpose
Compare the reported black-geometry symptom while walking between the preserved original APK and the original-fidelity camera candidate. The candidate changes only four player MainCamera near clip values in `level3` from 0.05 to 0.10.

## Before installing
1. Back up any important local progress/data. The candidate is signed with a new test key; Android will not accept it as an update over an APK signed by a different certificate.
2. Record device model, Android version, resolution, graphics setting and look sensitivity.
3. With the original APK, reproduce the symptom in the same scene and route. Record a short video if possible: walk slowly, turn the view, approach walls/objects/players.

## Candidate test
1. Uninstall the old package only after backing up local data.
2. Extract both 7z volumes together and install `LethalOffline-OriginalFidelity-CameraProbe.apk`.
3. Repeat the same scene, route, settings and movements.
4. Compare whether the black geometry disappears or decreases, and check for new clipping of nearby objects. Do not change other settings between runs.
5. Record crashes, FOV changes, missing close geometry or performance differences.

## Interpretation
- Repeatable improvement without new defects: retain this candidate as a hypothesis validated on that device; it does not prove all scenes/cameras are fixed.
- No change or worse: reject the 0.10 adjustment and revert to the original APK.
- This is not a test of fog, spectator, HUD, chat, terminal, audio, microphone or multiplayer; this candidate does not modify those systems.

## Revert
Uninstall the candidate and reinstall the preserved original APK. Do not attempt an in-place update when the signing certificate differs.
