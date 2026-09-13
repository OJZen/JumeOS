import Darwin
import Foundation
import R46HCardCore

signal(SIGPIPE, SIG_IGN)

do {
    let arguments = try AgentArguments.parse(
        Array(CommandLine.arguments.dropFirst()),
        environment: ProcessInfo.processInfo.environment
    )
    let configuration = arguments.configuration
    _ = try Validation.canonicalDirectory(configuration.inputRoot)
    _ = try Validation.canonicalDirectory(configuration.outputRoot)
    let profile = try Validation.loadProfile(
        path: configuration.profilePath,
        expectedSHA256: configuration.profileSHA256
    )
    let writePlan: WritePlan?
    if configuration.mode == .deploy {
        writePlan = try Validation.loadWritePlan(
            path: configuration.writePlanPath!,
            expectedSHA256: configuration.writePlanSHA256!,
            profile: profile,
            device: configuration.device,
            inputRoot: configuration.inputRoot
        )
    } else {
        writePlan = nil
    }

    let state = try SessionState(
        outputRoot: configuration.outputRoot,
        mode: configuration.mode,
        ownerUID: configuration.ownerUID,
        ownerGID: configuration.ownerGID,
        useTUI: configuration.useTUI
    )
    defer { state.seal() }
    state.record(
        level: "info",
        message: "configuration accepted: mode=\(configuration.mode.rawValue) device=\(configuration.device) profile=\(profile.profileID)"
    )
    let card = try CardDevice(
        device: configuration.device,
        profile: profile,
        ownerUID: configuration.ownerUID,
        ownerGID: configuration.ownerGID,
        sessionDirectory: state.sessionDirectory,
        sessionDirectoryDescriptor: try state.duplicateDirectoryDescriptor()
    )
    let server = UnixServer(
        configuration: configuration,
        state: state,
        card: card,
        writePlan: writePlan
    )
    try server.run()
    exit(EXIT_SUCCESS)
} catch {
    fputs("ERROR: \(error)\n", stderr)
    fputs(AgentArguments.usage + "\n", stderr)
    exit(EX_CONFIG)
}
