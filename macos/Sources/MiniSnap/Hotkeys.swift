import AppKit
import Carbon

enum HotkeyAction: Int, CaseIterable {
    case captureRegion = 0
    case captureFullScreen
    case captureDelayed
    case scrollCapture
    case recordVideo
    case ocr
    case library

    var key: String {
        switch self {
        case .captureRegion: return "CaptureRegion"
        case .captureFullScreen: return "CaptureFullScreen"
        case .captureDelayed: return "CaptureDelayed"
        case .scrollCapture: return "ScrollCapture"
        case .recordVideo: return "RecordVideo"
        case .ocr: return "Ocr"
        case .library: return "Library"
        }
    }

    var label: String {
        switch self {
        case .captureRegion: return L.t("Chụp vùng / cửa sổ")
        case .captureFullScreen: return L.t("Chụp toàn màn hình")
        case .captureDelayed: return L.t("Chụp vùng sau 3 giây")
        case .scrollCapture: return L.t("Chụp cuộn trang dài")
        case .recordVideo: return L.t("Quay video (bắt đầu / dừng)")
        case .ocr: return L.t("Chụp và trích chữ (OCR)")
        case .library: return L.t("Mở thư viện ảnh & video")
        }
    }

    var symbolName: String {
        switch self {
        case .captureRegion: return "camera.viewfinder"
        case .captureFullScreen: return "macwindow"
        case .captureDelayed: return "timer"
        case .scrollCapture: return "arrow.down.doc"
        case .recordVideo: return "record.circle"
        case .ocr: return "text.viewfinder"
        case .library: return "photo.on.rectangle"
        }
    }
}

/// A global shortcut: Carbon modifier mask (cmdKey/optionKey/controlKey/shiftKey) plus a virtual key code.
struct Hotkey: Equatable {
    static let noKey: UInt32 = 0xFFFF
    static let empty = Hotkey(mods: 0, keyCode: Hotkey.noKey)

    static let carbonMask: UInt32 = UInt32(cmdKey) | UInt32(optionKey) | UInt32(controlKey) | UInt32(shiftKey)

    let mods: UInt32
    let keyCode: UInt32

    init(mods: UInt32, keyCode: UInt32) {
        self.mods = mods & Hotkey.carbonMask
        self.keyCode = keyCode
    }

    var isNone: Bool { keyCode == Hotkey.noKey }

    var hasCommandLikeModifier: Bool {
        mods & (UInt32(cmdKey) | UInt32(optionKey) | UInt32(controlKey)) != 0
    }

    static func carbonMods(from flags: NSEvent.ModifierFlags) -> UInt32 {
        var m: UInt32 = 0
        if flags.contains(.command) { m |= UInt32(cmdKey) }
        if flags.contains(.option) { m |= UInt32(optionKey) }
        if flags.contains(.control) { m |= UInt32(controlKey) }
        if flags.contains(.shift) { m |= UInt32(shiftKey) }
        return m
    }

    static func cocoaFlags(from mods: UInt32) -> NSEvent.ModifierFlags {
        var f: NSEvent.ModifierFlags = []
        if mods & UInt32(cmdKey) != 0 { f.insert(.command) }
        if mods & UInt32(optionKey) != 0 { f.insert(.option) }
        if mods & UInt32(controlKey) != 0 { f.insert(.control) }
        if mods & UInt32(shiftKey) != 0 { f.insert(.shift) }
        return f
    }

    static func modifierSymbols(_ mods: UInt32) -> String {
        var s = ""
        if mods & UInt32(controlKey) != 0 { s += "⌃" }
        if mods & UInt32(optionKey) != 0 { s += "⌥" }
        if mods & UInt32(shiftKey) != 0 { s += "⇧" }
        if mods & UInt32(cmdKey) != 0 { s += "⌘" }
        return s
    }

    /// e.g. "⌥⇧2"; "(none)" when unassigned.
    var displayText: String {
        if isNone { return L.t("(không dùng)") }
        return Hotkey.modifierSymbols(mods) + KeyNames.name(for: keyCode)
    }

    /// nil when unassigned (used next to menu items and in tooltips).
    var shortText: String? { isNone ? nil : displayText }

    func serialize() -> String { String(mods) + ":" + String(keyCode) }

    static func parse(_ s: String?) -> Hotkey? {
        guard let s = s else { return nil }
        let p = s.split(separator: ":")
        guard p.count == 2, let m = UInt32(p[0]), let k = UInt32(p[1]) else { return nil }
        return Hotkey(mods: m, keyCode: k)
    }

    /// Function keys are fine without modifiers (they don't type text).
    static func allowedAlone(_ keyCode: UInt32) -> Bool {
        KeyNames.functionKeyIndex(keyCode) != nil
    }
}

enum KeyNames {
    private static let table: [UInt32: String] = {
        var t: [UInt32: String] = [:]
        let letters: [(Int, String)] = [
            (kVK_ANSI_A, "A"), (kVK_ANSI_B, "B"), (kVK_ANSI_C, "C"), (kVK_ANSI_D, "D"), (kVK_ANSI_E, "E"),
            (kVK_ANSI_F, "F"), (kVK_ANSI_G, "G"), (kVK_ANSI_H, "H"), (kVK_ANSI_I, "I"), (kVK_ANSI_J, "J"),
            (kVK_ANSI_K, "K"), (kVK_ANSI_L, "L"), (kVK_ANSI_M, "M"), (kVK_ANSI_N, "N"), (kVK_ANSI_O, "O"),
            (kVK_ANSI_P, "P"), (kVK_ANSI_Q, "Q"), (kVK_ANSI_R, "R"), (kVK_ANSI_S, "S"), (kVK_ANSI_T, "T"),
            (kVK_ANSI_U, "U"), (kVK_ANSI_V, "V"), (kVK_ANSI_W, "W"), (kVK_ANSI_X, "X"), (kVK_ANSI_Y, "Y"),
            (kVK_ANSI_Z, "Z"),
            (kVK_ANSI_0, "0"), (kVK_ANSI_1, "1"), (kVK_ANSI_2, "2"), (kVK_ANSI_3, "3"), (kVK_ANSI_4, "4"),
            (kVK_ANSI_5, "5"), (kVK_ANSI_6, "6"), (kVK_ANSI_7, "7"), (kVK_ANSI_8, "8"), (kVK_ANSI_9, "9"),
            (kVK_ANSI_Minus, "-"), (kVK_ANSI_Equal, "="), (kVK_ANSI_LeftBracket, "["), (kVK_ANSI_RightBracket, "]"),
            (kVK_ANSI_Semicolon, ";"), (kVK_ANSI_Quote, "'"), (kVK_ANSI_Comma, ","), (kVK_ANSI_Period, "."),
            (kVK_ANSI_Slash, "/"), (kVK_ANSI_Backslash, "\\"), (kVK_ANSI_Grave, "`"),
            (kVK_Return, "↩"), (kVK_Tab, "⇥"), (kVK_Space, "Space"), (kVK_Delete, "⌫"), (kVK_ForwardDelete, "⌦"),
            (kVK_Escape, "Esc"), (kVK_Home, "↖"), (kVK_End, "↘"), (kVK_PageUp, "⇞"), (kVK_PageDown, "⇟"),
            (kVK_LeftArrow, "←"), (kVK_RightArrow, "→"), (kVK_UpArrow, "↑"), (kVK_DownArrow, "↓"),
            (kVK_ANSI_Keypad0, "Num 0"), (kVK_ANSI_Keypad1, "Num 1"), (kVK_ANSI_Keypad2, "Num 2"),
            (kVK_ANSI_Keypad3, "Num 3"), (kVK_ANSI_Keypad4, "Num 4"), (kVK_ANSI_Keypad5, "Num 5"),
            (kVK_ANSI_Keypad6, "Num 6"), (kVK_ANSI_Keypad7, "Num 7"), (kVK_ANSI_Keypad8, "Num 8"),
            (kVK_ANSI_Keypad9, "Num 9"), (kVK_ANSI_KeypadPlus, "Num +"), (kVK_ANSI_KeypadMinus, "Num -"),
            (kVK_ANSI_KeypadMultiply, "Num *"), (kVK_ANSI_KeypadDivide, "Num /"), (kVK_ANSI_KeypadEnter, "⌤")
        ]
        for (code, name) in letters { t[UInt32(code)] = name }
        for (i, code) in functionKeys.enumerated() { t[UInt32(code)] = "F" + String(i + 1) }
        return t
    }()

    static let functionKeys: [Int] = [
        kVK_F1, kVK_F2, kVK_F3, kVK_F4, kVK_F5, kVK_F6, kVK_F7, kVK_F8, kVK_F9, kVK_F10,
        kVK_F11, kVK_F12, kVK_F13, kVK_F14, kVK_F15, kVK_F16, kVK_F17, kVK_F18, kVK_F19, kVK_F20
    ]

    static func functionKeyIndex(_ code: UInt32) -> Int? {
        functionKeys.firstIndex(of: Int(code))
    }

    static func name(for code: UInt32) -> String {
        table[code] ?? ("#" + String(code))
    }

    static func isModifierKey(_ code: UInt16) -> Bool {
        let mods: [Int] = [kVK_Command, kVK_Shift, kVK_Option, kVK_Control, kVK_RightShift, kVK_RightOption,
                           kVK_RightControl, kVK_CapsLock, kVK_Function, 0x36 /* right command */]
        return mods.contains(Int(code))
    }

    /// Menu key equivalent (character) for a key code, or nil when NSMenuItem cannot show it.
    static func menuKeyEquivalent(for code: UInt32) -> String? {
        if let i = functionKeyIndex(code) {
            if let scalar = UnicodeScalar(UInt32(NSF1FunctionKey + i)) { return String(Character(scalar)) }
            return nil
        }
        guard let n = table[code] else { return nil }
        if n.count == 1 { return n.lowercased() }
        return nil
    }
}

enum HotkeySettings {
    private static func defaultsKey(_ a: HotkeyAction) -> String { "MiniSnap.Hotkey." + a.key }

    static func defaults() -> [HotkeyAction: Hotkey] {
        let opt = UInt32(optionKey), shift = UInt32(shiftKey)
        return [
            .captureRegion: Hotkey(mods: opt | shift, keyCode: UInt32(kVK_ANSI_2)),
            .captureFullScreen: Hotkey(mods: opt | shift, keyCode: UInt32(kVK_ANSI_1)),
            .captureDelayed: Hotkey(mods: opt | shift, keyCode: UInt32(kVK_ANSI_3)),
            .scrollCapture: Hotkey(mods: opt | shift, keyCode: UInt32(kVK_ANSI_S)),
            .recordVideo: Hotkey(mods: opt | shift, keyCode: UInt32(kVK_ANSI_R)),
            .ocr: Hotkey(mods: opt | shift, keyCode: UInt32(kVK_ANSI_O)),
            .library: Hotkey(mods: opt | shift, keyCode: UInt32(kVK_ANSI_L))
        ]
    }

    static func load() -> [HotkeyAction: Hotkey] {
        var result = defaults()
        for a in HotkeyAction.allCases {
            if let h = Hotkey.parse(UserDefaults.standard.string(forKey: defaultsKey(a))) { result[a] = h }
        }
        return result
    }

    static func save(_ map: [HotkeyAction: Hotkey]) {
        for (a, h) in map { UserDefaults.standard.set(h.serialize(), forKey: defaultsKey(a)) }
    }
}

/// Global hotkeys through Carbon RegisterEventHotKey (no Accessibility permission needed).
/// Carbon delivers hotkey events on the main thread.
final class HotkeyManager {
    private static let signature: OSType = 0x4D53_4E50 // 'MSNP'
    private var refs: [EventHotKeyRef] = []
    private var handlerRef: EventHandlerRef?
    var onPress: ((HotkeyAction) -> Void)?

    init() {
        installHandler()
    }

    deinit {
        for r in refs { UnregisterEventHotKey(r) }
        if let h = handlerRef { RemoveEventHandler(h) }
    }

    private func installHandler() {
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        // The manager lives for the whole app run, so an unretained pointer is safe here.
        let selfPtr = Unmanaged.passUnretained(self).toOpaque()
        let status = InstallEventHandler(GetApplicationEventTarget(), { (_, event, userData) -> OSStatus in
            guard let event = event, let userData = userData else { return OSStatus(eventNotHandledErr) }
            var hk = EventHotKeyID()
            let err = GetEventParameter(event,
                                        EventParamName(kEventParamDirectObject),
                                        EventParamType(typeEventHotKeyID),
                                        nil,
                                        MemoryLayout<EventHotKeyID>.size,
                                        nil,
                                        &hk)
            if err != noErr { return err }
            let manager = Unmanaged<HotkeyManager>.fromOpaque(userData).takeUnretainedValue()
            manager.fire(Int(hk.id))
            return noErr
        }, 1, &spec, selfPtr, &handlerRef)
        if status != noErr {
            NSLog("MiniSnap: InstallEventHandler failed: %d", Int(status))
        }
    }

    fileprivate func fire(_ id: Int) {
        guard let action = HotkeyAction(rawValue: id - 1) else { return }
        onPress?(action)
    }

    /// Registers every configured shortcut; returns the ones that could not be registered.
    func register(_ map: [HotkeyAction: Hotkey]) -> [HotkeyAction] {
        unregisterAll()
        var failed: [HotkeyAction] = []
        for a in HotkeyAction.allCases {
            guard let h = map[a], !h.isNone else { continue }
            var ref: EventHotKeyRef?
            let hkID = EventHotKeyID(signature: HotkeyManager.signature, id: UInt32(a.rawValue + 1))
            let st = RegisterEventHotKey(h.keyCode, h.mods, hkID, GetApplicationEventTarget(), 0, &ref)
            if st == noErr, let r = ref {
                refs.append(r)
            } else {
                failed.append(a)
            }
        }
        return failed
    }

    func unregisterAll() {
        for r in refs { UnregisterEventHotKey(r) }
        refs.removeAll()
    }
}
