import Darwin
import Foundation
import R46HCardCore

struct AgentArguments {
    let configuration: AgentConfiguration

    static func parse(_ arguments: [String], environment: [String: String]) throws -> AgentArguments {
        guard geteuid() == 0 else {
            throw R46HError.unauthorized("agent must be launched through sudo")
        }
        guard arguments.first == "serve" else {
            throw R46HError.invalidArgument(usage)
        }

        var values: [String: String] = [:]
        var useTUI = true
        var index = 1
        while index < arguments.count {
            let key = arguments[index]
            if key == "--no-tui" {
                guard useTUI else { throw R46HError.invalidArgument("duplicate --no-tui") }
                useTUI = false
                index += 1
                continue
            }
            let allowed: Set<String> = [
                "--mode", "--device", "--profile", "--profile-sha256",
                "--output-root", "--input-root", "--write-plan", "--write-plan-sha256",
            ]
            guard allowed.contains(key), index + 1 < arguments.count, values[key] == nil else {
                throw R46HError.invalidArgument("unknown, duplicate, or valueless option: \(key)")
            }
            values[key] = arguments[index + 1]
            index += 2
        }

        func required(_ key: String) throws -> String {
            guard let value = values[key], !value.isEmpty else {
                throw R46HError.invalidArgument("missing \(key)")
            }
            return value
        }

        guard let ownerUID = environment["SUDO_UID"].flatMap(UInt32.init),
              let ownerGID = environment["SUDO_GID"].flatMap(UInt32.init),
              ownerUID > 0 else {
            throw R46HError.unauthorized("SUDO_UID/SUDO_GID are missing or unsafe")
        }
        guard let mode = AgentMode(rawValue: try required("--mode")) else {
            throw R46HError.invalidArgument("--mode must be audit or deploy")
        }

        let writePlanPath = values["--write-plan"]
        let writePlanSHA256 = values["--write-plan-sha256"]
        switch mode {
        case .audit:
            guard writePlanPath == nil, writePlanSHA256 == nil else {
                throw R46HError.invalidArgument("audit mode rejects write-plan arguments")
            }
        case .deploy:
            guard writePlanPath != nil, writePlanSHA256 != nil else {
                throw R46HError.invalidArgument("deploy mode requires a pinned write plan")
            }
        }

        let device = try required("--device")
        try Validation.validateDevicePath(device)
        return AgentArguments(configuration: AgentConfiguration(
            mode: mode,
            ownerUID: uid_t(ownerUID),
            ownerGID: gid_t(ownerGID),
            device: device,
            profilePath: try required("--profile"),
            profileSHA256: try required("--profile-sha256"),
            outputRoot: try required("--output-root"),
            inputRoot: try required("--input-root"),
            writePlanPath: writePlanPath,
            writePlanSHA256: writePlanSHA256,
            useTUI: useTUI
        ))
    }

    static let usage = """
    usage: r46h-card-agent serve \\
      --mode audit|deploy \\
      --device /dev/diskN \\
      --profile /absolute/profile.json \\
      --profile-sha256 <sha256> \\
      --output-root /absolute/external/path \\
      --input-root /absolute/trusted/path \\
      [--write-plan /absolute/plan.json --write-plan-sha256 <sha256>] \\
      [--no-tui]
    """
}
