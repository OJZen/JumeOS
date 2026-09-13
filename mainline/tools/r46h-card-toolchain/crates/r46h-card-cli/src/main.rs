use std::io::Read;
use std::path::{Path, PathBuf};

use r46h_card_core::backend::PlatformBackend;
use r46h_card_core::digest::hash_reader;
use r46h_card_core::file_backend::FileBackend;
use r46h_card_core::file_identity;
use r46h_card_core::journal::{AppendOnlyJournal, EvidenceStore};
use r46h_card_core::model::{CardProfile, WritePlan};
use r46h_card_core::platform::NativeBackend;
use r46h_card_core::readonly::{
    ReadOnlyAuditReceipt, ReadOnlyPlatformBackend, audit_and_eject, validate_macos_readonly_profile,
};
use r46h_card_core::receipt::EvidenceBindings;
use r46h_card_core::source::SourceRoot;
use r46h_card_core::transaction::{Transaction, receipt_json};
use r46h_card_core::{Error, Result};
use serde::de::DeserializeOwned;
use serde_json::Value;

fn main() {
    if let Err(error) = run() {
        eprintln!("ERROR: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    let arguments: Vec<String> = std::env::args().collect();
    match arguments.get(1).map(String::as_str) {
        Some("schema-check") => schema_check(&arguments[2..]),
        Some("schema-check-readonly") => schema_check_readonly(&arguments[2..]),
        Some("inspect-legacy") => inspect_legacy(&arguments[2..]),
        Some("simulate") => simulate(&arguments[2..]),
        Some("discover") => discover(&arguments[2..]),
        Some("audit-readonly") => audit_readonly(&arguments[2..]),
        Some("verify-readonly-receipt") => verify_readonly_receipt(&arguments[2..]),
        Some("version") | Some("--version") | Some("-V") => {
            require_exact_command(&arguments, "version")?;
            println!("r46h-card {}", env!("CARGO_PKG_VERSION"));
            Ok(())
        }
        Some("help") | Some("--help") | Some("-h") => {
            require_exact_command(&arguments, "help")?;
            print_help();
            Ok(())
        }
        None => {
            print_help();
            Ok(())
        }
        Some(command) => Err(Error::InvalidArgument(format!(
            "unknown command: {command}"
        ))),
    }
}

fn print_help() {
    println!(
        "r46h-card cross-platform toolchain\n\n\
         Usage:\n\
           r46h-card schema-check --profile PROFILE [--plan PLAN]\n\
           r46h-card schema-check-readonly --profile PROFILE\n\
           r46h-card inspect-legacy --input FILE\n\
           r46h-card simulate --profile PROFILE --plan PLAN --input-root DIR --media FILE\n\
             --evidence-dir NEW_DIR --transaction-id ID\n\
           r46h-card discover\n\
           r46h-card audit-readonly --profile PROFILE --attachment-id ID\n\
             --evidence-dir NEW_DIR --audit-id ID\n\
           r46h-card verify-readonly-receipt --profile PROFILE --receipt RECEIPT\n\
             --complete AUDIT-COMPLETE --tool-version VERSION --tool-sha256 SHA256\n\n\
         Safety:\n\
           v0.2 enables only profile-bound read-only audit and eject on macOS.\n\
           Native writes and all Linux/Windows physical-media access remain fail-closed."
    );
}

fn require_exact_command(arguments: &[String], command: &str) -> Result<()> {
    if arguments.len() == 2 {
        Ok(())
    } else {
        Err(Error::InvalidArgument(format!(
            "{command} accepts no additional arguments"
        )))
    }
}

fn schema_check(arguments: &[String]) -> Result<()> {
    validate_options(arguments, &["--profile", "--plan"])?;
    let profile_path = required_path(arguments, "--profile")?;
    let (profile, _) = load_json_with_digest::<CardProfile>(&profile_path, "v2 profile")?;
    profile.validate()?;
    if let Some(plan_path) = optional_path(arguments, "--plan")? {
        let (plan, _) = load_json_with_digest::<WritePlan>(&plan_path, "v2 write plan")?;
        plan.validate(&profile)?;
    }
    println!("R46H_CARD_SCHEMA result=pass format_version=2");
    Ok(())
}

fn schema_check_readonly(arguments: &[String]) -> Result<()> {
    validate_options(arguments, &["--profile"])?;
    let profile_path = required_path(arguments, "--profile")?;
    let (profile, profile_sha256) =
        load_json_with_digest::<CardProfile>(&profile_path, "macOS read-only profile")?;
    validate_macos_readonly_profile(&profile)?;
    println!(
        "R46H_CARD_READONLY_SCHEMA result=pass format_version=2 profile_sha256={profile_sha256}"
    );
    Ok(())
}

fn inspect_legacy(arguments: &[String]) -> Result<()> {
    validate_options(arguments, &["--input"])?;
    let input = required_path(arguments, "--input")?;
    let (contents, sha256) = load_bytes_with_digest(&input, "legacy JSON")?;
    let bytes = contents.len() as u64;
    let value: Value = serde_json::from_slice(&contents)?;
    let format_version = value
        .get("format_version")
        .and_then(Value::as_u64)
        .ok_or_else(|| Error::InvalidData("legacy JSON has no numeric format_version".into()))?;
    if format_version != 1 {
        return Err(Error::InvalidData(
            "inspect-legacy accepts only format_version 1".into(),
        ));
    }
    let kind = if value.get("profile_id").is_some() && value.get("card").is_some() {
        "profile"
    } else if value.get("operations").is_some() {
        "write_plan"
    } else if value.get("safe_to_boot").is_some() || value.get("state").is_some() {
        "receipt_or_status"
    } else {
        "unknown"
    };
    println!(
        "R46H_CARD_LEGACY result=inspect_only executable=no kind={kind} bytes={bytes} sha256={sha256}"
    );
    Ok(())
}

fn simulate(arguments: &[String]) -> Result<()> {
    validate_options(
        arguments,
        &[
            "--profile",
            "--plan",
            "--input-root",
            "--media",
            "--evidence-dir",
            "--transaction-id",
        ],
    )?;
    let profile_path = required_path(arguments, "--profile")?;
    let plan_path = required_path(arguments, "--plan")?;
    let input_root_path = required_path(arguments, "--input-root")?;
    let media_path = required_path(arguments, "--media")?;
    let evidence_path = required_path(arguments, "--evidence-dir")?;
    let transaction_id = required_value(arguments, "--transaction-id")?;
    let (profile, profile_sha256) =
        load_json_with_digest::<CardProfile>(&profile_path, "v2 profile")?;
    profile.validate()?;
    let (plan, plan_sha256) = load_json_with_digest::<WritePlan>(&plan_path, "v2 write plan")?;
    plan.validate(&profile)?;
    if plan.operations.iter().any(|operation| {
        matches!(
            operation.target_before,
            r46h_card_core::model::TargetPrecondition::Disposable { .. }
        )
    }) {
        return Err(Error::Unsupported(
            "the simulator CLI intentionally does not issue destructive authorizations".into(),
        ));
    }
    let input_root = SourceRoot::open(&input_root_path)?;
    let bindings = EvidenceBindings {
        profile_sha256,
        plan_sha256,
        tool_version: env!("CARGO_PKG_VERSION").into(),
        tool_sha256: current_executable_sha256()?,
    };
    let backend = FileBackend::new(&media_path).with_hardware_target(profile.target.clone());
    let identities = backend.discover()?;
    let identity = identities
        .first()
        .ok_or_else(|| Error::InvalidData("simulated media was not discovered".into()))?;
    let session = backend.claim(&identity.stable_id, profile, true)?;
    let transaction = Transaction::new(
        session,
        &plan,
        &input_root,
        &evidence_path,
        transaction_id,
        bindings,
    )?;
    let evidence = EvidenceStore::create(&evidence_path)?;
    let mut journal = AppendOnlyJournal::create(&evidence.journal_path())?;
    let (result, receipt) = transaction.execute_with_journal(&mut journal);
    let receipt_sha256 = evidence.finalize(&receipt_json(&receipt)?)?;
    match result {
        Ok(_) => {
            println!(
                "R46H_CARD_TRANSACTION result=pass safe_to_boot=true evidence={} receipt_sha256={} journal={}",
                evidence.path().display(),
                receipt_sha256,
                journal.path().display()
            );
            Ok(())
        }
        Err(error) => Err(Error::InvalidData(format!(
            "transaction failed; final unsafe receipt is at {}: {error}",
            evidence.path().display()
        ))),
    }
}

fn discover(arguments: &[String]) -> Result<()> {
    if !arguments.is_empty() {
        return Err(Error::InvalidArgument("discover takes no arguments".into()));
    }
    let backend = NativeBackend;
    let candidates = backend.discover_readonly()?;
    if candidates.is_empty() {
        return Err(Error::InvalidData(
            "no whole IOMedia candidates were discovered".into(),
        ));
    }
    for candidate in candidates {
        println!("{}", serde_json::to_string(&candidate)?);
    }
    Ok(())
}

fn audit_readonly(arguments: &[String]) -> Result<()> {
    validate_options(
        arguments,
        &[
            "--profile",
            "--attachment-id",
            "--evidence-dir",
            "--audit-id",
        ],
    )?;
    let profile_path = required_path(arguments, "--profile")?;
    let evidence_path = required_path(arguments, "--evidence-dir")?;
    let attachment_id = required_value(arguments, "--attachment-id")?;
    let audit_id = required_value(arguments, "--audit-id")?;
    require_macos_readonly_privilege()?;
    let (profile, profile_sha256) =
        load_json_with_digest::<CardProfile>(&profile_path, "v2 profile")?;
    validate_macos_readonly_profile(&profile)?;
    r46h_card_core::model::validate_id(&audit_id, "audit_id")?;
    let tool_sha256 = current_executable_sha256()?;
    let evidence_parent = evidence_path
        .parent()
        .ok_or_else(|| Error::UnsafePath(evidence_path.clone()))?;
    let backend = NativeBackend;
    let candidates = backend.discover_readonly()?;
    let selected: Vec<_> = candidates
        .iter()
        .filter(|candidate| candidate.attachment_id == attachment_id)
        .collect();
    if selected.len() != 1 {
        return Err(Error::InvalidData(format!(
            "read-only attachment selector matched {} candidates",
            selected.len()
        )));
    }
    let selected = selected[0];
    selected.validate_for_profile(&profile)?;
    if !selected.transport.eq_ignore_ascii_case("usb") {
        return Err(Error::InvalidData(
            "read-only audit requires a USB-attached candidate".into(),
        ));
    }
    backend.validate_external_path(&attachment_id, evidence_parent)?;
    reserve_readonly_evidence(&evidence_path)?;

    let mut session = match backend.claim_readonly(&attachment_id) {
        Ok(session) => session,
        Err(error) => {
            let _ = publish_readonly_failure(&evidence_path, &profile_sha256, &tool_sha256, &error);
            return Err(error);
        }
    };
    let receipt = match audit_and_eject(
        &mut session,
        &profile,
        &audit_id,
        &profile_sha256,
        env!("CARGO_PKG_VERSION"),
        &tool_sha256,
    ) {
        Ok(receipt) => receipt,
        Err(error) => {
            let _ = publish_readonly_failure(&evidence_path, &profile_sha256, &tool_sha256, &error);
            return Err(error);
        }
    };
    publish_readonly_receipt(&evidence_path, &receipt)?;
    println!(
        "R46H_CARD_READONLY_AUDIT result=pass media_access=read_only ejected=true layout_id={} evidence={}",
        receipt.layout_id,
        evidence_path.display()
    );
    Ok(())
}

fn verify_readonly_receipt(arguments: &[String]) -> Result<()> {
    validate_options(
        arguments,
        &[
            "--profile",
            "--receipt",
            "--complete",
            "--tool-version",
            "--tool-sha256",
        ],
    )?;
    let profile_path = required_path(arguments, "--profile")?;
    let receipt_path = required_path(arguments, "--receipt")?;
    let complete_path = required_path(arguments, "--complete")?;
    let tool_version = required_value(arguments, "--tool-version")?;
    let tool_sha256 = required_value(arguments, "--tool-sha256")?;
    let (profile, profile_sha256) =
        load_json_with_digest::<CardProfile>(&profile_path, "v2 profile")?;
    validate_macos_readonly_profile(&profile)?;
    let (receipt_bytes, receipt_sha256) =
        load_bytes_with_digest(&receipt_path, "read-only audit receipt")?;
    let receipt: ReadOnlyAuditReceipt = serde_json::from_slice(&receipt_bytes)?;
    let (complete, _) = load_bytes_with_digest(&complete_path, "read-only completion marker")?;
    let expected_complete = format!("receipt_sha256={receipt_sha256}\n");
    if complete != expected_complete.as_bytes() {
        return Err(Error::InvalidData(
            "AUDIT-COMPLETE does not bind the read-only receipt".into(),
        ));
    }
    receipt.validate_against(&profile, &profile_sha256, &tool_version, &tool_sha256)?;
    println!(
        "R46H_CARD_READONLY_VERIFY result=pass layout_id={} receipt_sha256={receipt_sha256}",
        receipt.layout_id
    );
    Ok(())
}

fn reserve_readonly_evidence(path: &Path) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| Error::UnsafePath(path.to_path_buf()))?;
    let parent_metadata = std::fs::symlink_metadata(parent)
        .map_err(|source| Error::io("inspect read-only evidence parent", source))?;
    let canonical_parent = parent
        .canonicalize()
        .map_err(|source| Error::io("canonicalize read-only evidence parent", source))?;
    if !path.is_absolute()
        || path.file_name().is_none()
        || !parent_metadata.is_dir()
        || parent_metadata.file_type().is_symlink()
        || canonical_parent != parent
    {
        return Err(Error::UnsafePath(path.to_path_buf()));
    }
    #[cfg(target_os = "macos")]
    {
        use std::os::unix::fs::MetadataExt;

        if canonical_parent != Path::new("/private/tmp")
            || parent_metadata.uid() != 0
            || parent_metadata.gid() != 0
            || parent_metadata.mode() & 0o7777 != 0o1777
        {
            return Err(Error::InvalidArgument(
                "macOS read-only evidence must be a new direct child of root-owned sticky /private/tmp"
                    .into(),
            ));
        }
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        let mut builder = std::fs::DirBuilder::new();
        builder.mode(0o700);
        builder
            .create(path)
            .map_err(|source| Error::io("reserve read-only evidence directory", source))?;
    }
    #[cfg(windows)]
    std::fs::create_dir(path)
        .map_err(|source| Error::io("reserve read-only evidence directory", source))?;
    std::fs::File::open(parent)
        .and_then(|directory| directory.sync_all())
        .map_err(|source| Error::io("flush read-only evidence parent", source))?;
    Ok(())
}

#[cfg(target_os = "macos")]
fn require_macos_readonly_privilege() -> Result<()> {
    if unsafe { libc::geteuid() } != 0 {
        return Err(Error::InvalidArgument(
            "audit-readonly must run as root from a hash-pinned private staging launcher".into(),
        ));
    }
    Ok(())
}

#[cfg(not(target_os = "macos"))]
fn require_macos_readonly_privilege() -> Result<()> {
    Err(Error::Unsupported(
        "read-only physical-media audit is enabled only on macOS".into(),
    ))
}

fn publish_readonly_receipt(path: &Path, receipt: &ReadOnlyAuditReceipt) -> Result<()> {
    receipt.validate()?;
    let mut bytes = serde_json::to_vec_pretty(receipt)?;
    bytes.push(b'\n');
    let digest =
        r46h_card_core::journal::publish_no_replace(&path.join("READONLY-AUDIT.json"), &bytes)?;
    let complete = format!("receipt_sha256={digest}\n");
    r46h_card_core::journal::publish_no_replace(&path.join("AUDIT-COMPLETE"), complete.as_bytes())?;
    std::fs::File::open(path)
        .and_then(|directory| directory.sync_all())
        .map_err(|source| Error::io("flush read-only evidence directory", source))?;
    Ok(())
}

fn publish_readonly_failure(
    path: &Path,
    profile_sha256: &str,
    tool_sha256: &str,
    error: &Error,
) -> Result<()> {
    let failure = format!(
        "R46H_CARD_READONLY_AUDIT result=fail profile_sha256={profile_sha256} tool_sha256={tool_sha256} error={}\n",
        sanitize_marker_field(&error.to_string())
    );
    r46h_card_core::journal::publish_no_replace(&path.join("AUDIT-FAILED"), failure.as_bytes())?;
    Ok(())
}

fn sanitize_marker_field(value: &str) -> String {
    value
        .bytes()
        .map(|byte| {
            if byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-' | b':') {
                byte as char
            } else {
                '_'
            }
        })
        .collect()
}

fn load_json_with_digest<T: DeserializeOwned>(
    path: &Path,
    kind: &'static str,
) -> Result<(T, String)> {
    let (bytes, digest) = load_bytes_with_digest(path, kind)?;
    let value = serde_json::from_slice(&bytes)?;
    Ok((value, digest))
}

fn load_bytes_with_digest(path: &Path, kind: &'static str) -> Result<(Vec<u8>, String)> {
    let metadata = std::fs::symlink_metadata(path)
        .map_err(|source| Error::io("inspect JSON input", source))?;
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err(Error::UnsafePath(path.to_path_buf()));
    }
    let mut file = file_identity::open_existing(path, false)?;
    let opened = file_identity::identity(&file)?;
    if opened.size() != metadata.len() || opened.links() != 1 || opened.is_reparse_point() {
        return Err(Error::UnsafePath(path.to_path_buf()));
    }
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes)
        .map_err(|source| Error::io("read JSON input", source))?;
    let digest = hash_reader(&mut bytes.as_slice())?.0;
    let after = file_identity::identity(&file)?;
    if metadata.len() != bytes.len() as u64 || opened != after {
        return Err(Error::InvalidData(format!("{kind} changed while reading")));
    }
    Ok((bytes, digest))
}

fn current_executable_sha256() -> Result<String> {
    let path =
        std::env::current_exe().map_err(|source| Error::io("locate current tool", source))?;
    Ok(load_bytes_with_digest(&path, "current tool")?.1)
}

fn required_path(arguments: &[String], name: &str) -> Result<PathBuf> {
    let path = PathBuf::from(required_value(arguments, name)?);
    if !path.is_absolute() {
        return Err(Error::InvalidArgument(format!("{name} must be absolute")));
    }
    Ok(path)
}

fn optional_path(arguments: &[String], name: &str) -> Result<Option<PathBuf>> {
    option_value(arguments, name)?
        .map(PathBuf::from)
        .map(|path| {
            if path.is_absolute() {
                Ok(path)
            } else {
                Err(Error::InvalidArgument(format!("{name} must be absolute")))
            }
        })
        .transpose()
}

fn required_value(arguments: &[String], name: &str) -> Result<String> {
    option_value(arguments, name)?.ok_or_else(|| Error::InvalidArgument(format!("missing {name}")))
}

fn option_value(arguments: &[String], name: &str) -> Result<Option<String>> {
    let mut result = None;
    let mut index = 0;
    while index < arguments.len() {
        let option = &arguments[index];
        let value = arguments
            .get(index + 1)
            .ok_or_else(|| Error::InvalidArgument(format!("missing value for option {option}")))?;
        if !option.starts_with("--") {
            return Err(Error::InvalidArgument(format!(
                "unexpected argument: {option}"
            )));
        }
        if option == name && result.replace(value.clone()).is_some() {
            return Err(Error::InvalidArgument(format!("duplicate {name}")));
        }
        index += 2;
    }
    Ok(result)
}

fn validate_options(arguments: &[String], allowed: &[&str]) -> Result<()> {
    if arguments.len() % 2 != 0 {
        return Err(Error::InvalidArgument(
            "every option must have exactly one value".into(),
        ));
    }
    let mut seen = std::collections::BTreeSet::new();
    for pair in arguments.chunks_exact(2) {
        let option = pair[0].as_str();
        if !allowed.contains(&option) {
            return Err(Error::InvalidArgument(format!("unknown option: {option}")));
        }
        if !seen.insert(option) {
            return Err(Error::InvalidArgument(format!("duplicate {option}")));
        }
    }
    Ok(())
}
