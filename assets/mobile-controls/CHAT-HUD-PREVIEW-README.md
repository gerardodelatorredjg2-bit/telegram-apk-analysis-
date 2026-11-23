# Chat HUD preview — test guide

This is a browser-only prototype for layout and interaction. It is **not wired into Unity or the APK**.

## Available interactions
- Open/close the chat using the chat icon.
- Close using the panel's × button.
- Type a message and tap Send; it is appended as a local mock message.
- The message list scrolls as new messages appear.

## Quick test
1. Open [preview.html](./preview.html) in a browser.
2. Open chat; confirm it appears at the left and the settings icon stays top-right.
3. Close chat using × and reopen using the chat icon.
4. Send a short message and a long message; verify wrapping and scroll.
5. Test landscape and a narrow viewport. Confirm panel doesn't obscure the action stack or inventory.
6. If testing on Android, open the keyboard and verify the input stays visible. This browser test does not establish in-game keyboard behavior.

## Acceptance status
- [x] Toggle open/close
- [x] Local message input and append
- [x] Basic responsive sizing
- [ ] Android keyboard behavior on target device
- [ ] Unity safe-area/RectTransform integration
- [ ] Verify gameplay controls remain active
- [ ] APK build and in-game validation

## Blocker for APK integration
The repository currently contains APK analysis/asset material and visual HUD assets, but not the editable Unity project or custom-controls source needed to safely modify the runtime chat. Do not mark runtime items complete without that source and a device/build test.
