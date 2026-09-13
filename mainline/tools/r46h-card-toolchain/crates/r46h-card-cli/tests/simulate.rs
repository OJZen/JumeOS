use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use std::{collections::BTreeMap, fs};

use r46h_card_core::backend::PlatformBackend;
use r46h_card_core::digest::hash_reader;
use r46h_card_core::file_backend::FileBackend;
use r46h_card_core::model::{CardProfile, PartitionRole, PartitionScheme};
use r46h_card_core::readonly::{
    DiscoveryCandidate, MediaAccess, ReadOnlyAuditReceipt, VerifiedPartition,
};
use serde_json::{Value, json};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct Fixture {
    root: PathBuf,
    media: PathBuf,
    input: PathBuf,
    profile: PathBuf,
    plan: PathBuf,
    evidence: PathBuf,
}

impl Fixture {
    fn new() -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let sequence = SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let external_test_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../../out/.cache/r46h-card-cli-tests")
            .canonicalize()
            .unwrap_or_else(|_| {
                let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("../../../../out/.cache/r46h-card-cli-tests");
                std::fs::create_dir_all(&root).unwrap();
                root.canonicalize().unwrap()
            });
        std::fs::create_dir_all(&external_test_root).unwrap();
        let root = external_test_root.join(format!(
            "r46h-card-cli-test-{}-{nonce}-{sequence}",
            std::process::id()
        ));
        std::fs::create_dir(&root).unwrap();
        let media = root.join("media.bin");
        let input = root.join("input");
        std::fs::create_dir(&input).unwrap();
        write_bytes(&media, 0, 4096);
        write_bytes(&input.join("boot.img"), 0xa5, 1024);
        let profile = root.join("profile.json");
        let plan = root.join("plan.json");
        let evidence = root.join("evidence");
        write_json(
            &profile,
            &json!({
                "format_version": 2,
                "profile_id": "cli-test-profile-v2",
                "target": "R46H-TEST",
                "whole_size": 4096,
                "sector_size": 512,
                "partition_scheme": "mbr",
                "prefix": { "size": 512, "sha256": digest(&vec![0; 512]) },
                "partitions": [
                    { "role": "boot", "number": 1, "offset": 512, "size": 1024,
                      "mbr": { "bootable": false, "type_code": 12 },
                      "filesystem": null, "identifiers": {} },
                    { "role": "root", "number": 2, "offset": 1536, "size": 1024,
                      "mbr": { "bootable": false, "type_code": 131 },
                      "filesystem": null, "identifiers": {} },
                    { "role": "easyroms", "number": 3, "offset": 2560, "size": 1024,
                      "mbr": { "bootable": false, "type_code": 7 },
                      "filesystem": null, "identifiers": {} }
                ]
            }),
        );
        let stable_id = FileBackend::new(&media)
            .discover()
            .unwrap()
            .remove(0)
            .stable_id;
        write_json(
            &plan,
            &json!({
                "format_version": 2,
                "plan_id": "cli-test-plan-v2",
                "profile_id": "cli-test-profile-v2",
                "target_stable_id": stable_id,
                "verification": "full",
                "operations": [{
                    "id": "write-boot",
                    "partition": "boot",
                    "source": { "relative_path": "boot.img", "size": 1024,
                                "sha256": digest(&vec![0xa5; 1024]) },
                    "target_before": { "kind": "exact_sha256",
                                       "sha256": digest(&vec![0; 1024]) }
                }],
                "unchanged_ranges": [
                    { "id": "prefix", "offset": 0, "length": 512,
                      "sha256_before": digest(&vec![0; 512]) },
                    { "id": "remainder", "offset": 1536, "length": 2560,
                      "sha256_before": digest(&vec![0; 2560]) }
                ]
            }),
        );
        Self {
            root,
            media,
            input,
            profile,
            plan,
            evidence,
        }
    }

    fn command(&self) -> Command {
        let mut command = Command::new(env!("CARGO_BIN_EXE_r46h-card"));
        command.args([
            "simulate",
            "--profile",
            self.profile.to_str().unwrap(),
            "--plan",
            self.plan.to_str().unwrap(),
            "--input-root",
            self.input.to_str().unwrap(),
            "--media",
            self.media.to_str().unwrap(),
            "--evidence-dir",
            self.evidence.to_str().unwrap(),
            "--transaction-id",
            "cli-test-transaction",
        ]);
        command
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.root).unwrap();
    }
}

#[test]
fn simulate_persists_journal_and_publishes_no_clobber_receipt() {
    let fixture = Fixture::new();
    let first = fixture.command().output().unwrap();
    assert!(
        first.status.success(),
        "{}",
        String::from_utf8_lossy(&first.stderr)
    );
    let stdout = String::from_utf8(first.stdout).unwrap();
    assert!(stdout.contains("result=pass safe_to_boot=true"));
    assert!(stdout.contains("receipt_sha256="));

    let journal = fixture.evidence.join("journal.jsonl");
    let receipt = fixture.evidence.join("receipt.json");
    let complete = fixture.evidence.join("RECEIPT-COMPLETE");
    let events: Vec<Value> = std::fs::read_to_string(&journal)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    assert!(events.len() >= 8);
    for (index, event) in events.iter().enumerate() {
        assert_eq!(event["sequence"], (index + 1) as u64);
    }
    assert_eq!(events.last().unwrap()["receipt"]["state"], "ejected");
    assert_eq!(events.last().unwrap()["receipt"]["safe_to_boot"], true);
    let receipt_before = std::fs::read(&receipt).unwrap();
    let complete_before = std::fs::read(&complete).unwrap();
    let media_before = std::fs::read(&fixture.media).unwrap();
    let second = fixture.command().output().unwrap();
    assert!(!second.status.success());
    assert!(String::from_utf8_lossy(&second.stderr).contains("reserve evidence directory"));
    assert_eq!(std::fs::read(&receipt).unwrap(), receipt_before);
    assert_eq!(std::fs::read(&complete).unwrap(), complete_before);
    assert_eq!(std::fs::read(&fixture.media).unwrap(), media_before);
}

#[test]
fn preexisting_evidence_directory_blocks_before_the_first_media_write() {
    let fixture = Fixture::new();
    std::fs::create_dir(&fixture.evidence).unwrap();
    let media_before = std::fs::read(&fixture.media).unwrap();

    let output = fixture.command().output().unwrap();

    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("reserve evidence directory"));
    assert_eq!(std::fs::read(&fixture.media).unwrap(), media_before);
    assert!(
        std::fs::read_dir(&fixture.evidence)
            .unwrap()
            .next()
            .is_none()
    );
}

#[test]
fn failed_preflight_publishes_unsafe_receipt_without_changing_media() {
    let fixture = Fixture::new();
    let mut plan: Value = serde_json::from_slice(&std::fs::read(&fixture.plan).unwrap()).unwrap();
    plan["operations"][0]["target_before"]["sha256"] = Value::String("1".repeat(64));
    write_json(&fixture.plan, &plan);
    let media_before = std::fs::read(&fixture.media).unwrap();

    let output = fixture.command().output().unwrap();

    assert!(!output.status.success());
    assert_eq!(std::fs::read(&fixture.media).unwrap(), media_before);
    let receipt: Value =
        serde_json::from_slice(&std::fs::read(fixture.evidence.join("receipt.json")).unwrap())
            .unwrap();
    assert_eq!(receipt["state"], "failed");
    assert_eq!(receipt["safe_to_boot"], false);
    assert_eq!(
        receipt["failure_disposition"]["flush"]["state"],
        "succeeded"
    );
    assert_eq!(
        receipt["failure_disposition"]["eject"]["state"],
        "succeeded"
    );
    let complete = std::fs::read_to_string(fixture.evidence.join("RECEIPT-COMPLETE")).unwrap();
    assert!(complete.starts_with("receipt_sha256="));
}

#[test]
fn help_has_no_patch_artifacts_and_documents_reserved_evidence() {
    let output = Command::new(env!("CARGO_BIN_EXE_r46h-card"))
        .arg("--help")
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.contains("--evidence-dir NEW_DIR"));
    assert!(stdout.contains("verify-readonly-receipt"));
    assert!(!stdout.contains("\n+"));
    assert!(!stdout.contains("--journal"));

    for arguments in [["--help", "unexpected"], ["--version", "unexpected"]] {
        let rejected = Command::new(env!("CARGO_BIN_EXE_r46h-card"))
            .args(arguments)
            .output()
            .unwrap();
        assert!(!rejected.status.success());
        assert!(String::from_utf8_lossy(&rejected.stderr).contains("additional arguments"));
    }
}

#[test]
fn readonly_schema_and_receipt_verifier_are_executable_and_strict() {
    let fixture = Fixture::new();
    let profile_path = fixture.root.join("readonly-profile.json");
    let profile_value = json!({
        "format_version": 2,
        "profile_id": "cli-readonly-profile-v2",
        "target": "R46H-TEST",
        "whole_size": 4096,
        "sector_size": 512,
        "partition_scheme": "mbr",
        "prefix": { "size": 512, "sha256": "1".repeat(64) },
        "partitions": [
            { "role": "boot", "number": 1, "offset": 512, "size": 1024,
              "mbr": { "bootable": false, "type_code": 12 },
              "filesystem": "fat32", "identifiers": { "volume_uuid": "AB-CD" } },
            { "role": "root", "number": 2, "offset": 1536, "size": 1024,
              "mbr": { "bootable": false, "type_code": 131 },
              "filesystem": "ext4", "identifiers": { "partuuid": "1234abcd-02" } },
            { "role": "easyroms", "number": 3, "offset": 2560, "size": 1536,
              "mbr": { "bootable": false, "type_code": 7 },
              "filesystem": "exfat", "identifiers": { "volume_uuid": "EF-01" } }
        ]
    });
    write_json(&profile_path, &profile_value);
    let profile: CardProfile = serde_json::from_value(profile_value.clone()).unwrap();
    let profile_sha256 = digest(&fs::read(&profile_path).unwrap());
    let tool_sha256 = "2".repeat(64);
    let mut receipt = ReadOnlyAuditReceipt {
        format_version: 1,
        audit_id: "cli-readonly-audit".into(),
        profile_id: profile.profile_id.clone(),
        profile_sha256: profile_sha256.clone(),
        tool_version: "0.2.0".into(),
        tool_sha256: tool_sha256.clone(),
        hardware_target: profile.target.clone(),
        layout_id: String::new(),
        candidate: DiscoveryCandidate {
            platform: "macos".into(),
            attachment_id: "macos-iomedia-v1:test".into(),
            physical_store_id: "macos-ioreg-v1:test".into(),
            display_path: "/dev/disk99".into(),
            transport: "USB".into(),
            size: 4096,
            sector_size: 512,
            whole: true,
            internal: false,
            removable: true,
            ejectable: true,
            writable: true,
            system_disk: false,
        },
        partition_scheme: PartitionScheme::Mbr,
        prefix_size: 512,
        prefix_sha256: "1".repeat(64),
        mbr_disk_signature: 0x1234_abcd,
        partitions: vec![
            VerifiedPartition {
                role: PartitionRole::Boot,
                number: 1,
                offset: 512,
                size: 1024,
                mbr_bootable: false,
                mbr_type_code: 12,
                filesystem: Some("fat32".into()),
                identifiers: BTreeMap::from([("volume_uuid".into(), "AB-CD".into())]),
            },
            VerifiedPartition {
                role: PartitionRole::Root,
                number: 2,
                offset: 1536,
                size: 1024,
                mbr_bootable: false,
                mbr_type_code: 131,
                filesystem: Some("ext4".into()),
                identifiers: BTreeMap::from([("partuuid".into(), "1234abcd-02".into())]),
            },
            VerifiedPartition {
                role: PartitionRole::Easyroms,
                number: 3,
                offset: 2560,
                size: 1536,
                mbr_bootable: false,
                mbr_type_code: 7,
                filesystem: Some("exfat".into()),
                identifiers: BTreeMap::from([("volume_uuid".into(), "EF-01".into())]),
            },
        ],
        media_access: MediaAccess::ReadOnly,
        ejected: true,
    };
    receipt.layout_id = receipt.recompute_layout_id().unwrap();
    receipt
        .validate_against(&profile, &profile_sha256, "0.2.0", &tool_sha256)
        .unwrap();

    let receipt_path = fixture.root.join("READONLY-AUDIT.json");
    let complete_path = fixture.root.join("AUDIT-COMPLETE");
    let write_receipt = |receipt: &ReadOnlyAuditReceipt| {
        let mut bytes = serde_json::to_vec_pretty(receipt).unwrap();
        bytes.push(b'\n');
        fs::write(&receipt_path, &bytes).unwrap();
        fs::write(
            &complete_path,
            format!("receipt_sha256={}\n", digest(&bytes)),
        )
        .unwrap();
    };
    write_receipt(&receipt);

    let verifier = || {
        let mut command = Command::new(env!("CARGO_BIN_EXE_r46h-card"));
        command.args([
            "verify-readonly-receipt",
            "--profile",
            profile_path.to_str().unwrap(),
            "--receipt",
            receipt_path.to_str().unwrap(),
            "--complete",
            complete_path.to_str().unwrap(),
            "--tool-version",
            "0.2.0",
            "--tool-sha256",
            &tool_sha256,
        ]);
        command
    };
    let output = verifier().output().unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("layout_id="));

    let schema = Command::new(env!("CARGO_BIN_EXE_r46h-card"))
        .args([
            "schema-check-readonly",
            "--profile",
            profile_path.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(schema.status.success());

    let wrong_tool = verifier();
    let arguments = wrong_tool
        .get_args()
        .map(|value| value.to_owned())
        .collect::<Vec<_>>();
    let position = arguments
        .iter()
        .position(|value| value == "--tool-sha256")
        .unwrap();
    let mut wrong_tool = Command::new(env!("CARGO_BIN_EXE_r46h-card"));
    wrong_tool.args(&arguments[..=position]);
    wrong_tool.arg("3".repeat(64));
    assert!(!wrong_tool.output().unwrap().status.success());

    fs::write(
        &complete_path,
        format!("receipt_sha256={}\n", "0".repeat(64)),
    )
    .unwrap();
    assert!(!verifier().output().unwrap().status.success());
    write_receipt(&receipt);

    let mut reordered = receipt.clone();
    reordered.partitions.swap(0, 1);
    reordered.layout_id = reordered.recompute_layout_id().unwrap();
    write_receipt(&reordered);
    assert!(!verifier().output().unwrap().status.success());
    write_receipt(&receipt);

    let mut unknown: Value = serde_json::to_value(&receipt).unwrap();
    unknown["safe_to_boot"] = Value::Bool(true);
    write_json(&receipt_path, &unknown);
    fs::write(
        &complete_path,
        format!(
            "receipt_sha256={}\n",
            digest(&fs::read(&receipt_path).unwrap())
        ),
    )
    .unwrap();
    assert!(!verifier().output().unwrap().status.success());
    write_receipt(&receipt);

    let mut unrelated = verifier();
    unrelated.args(["--plan", fixture.plan.to_str().unwrap()]);
    assert!(!unrelated.output().unwrap().status.success());

    let mut missing_mbr = profile_value;
    missing_mbr["partitions"][0]
        .as_object_mut()
        .unwrap()
        .remove("mbr");
    write_json(&profile_path, &missing_mbr);
    let rejected = Command::new(env!("CARGO_BIN_EXE_r46h-card"))
        .args([
            "schema-check-readonly",
            "--profile",
            profile_path.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(!rejected.status.success());
}

#[cfg(not(target_os = "macos"))]
#[test]
fn native_discovery_is_fail_closed() {
    let output = Command::new(env!("CARGO_BIN_EXE_r46h-card"))
        .arg("discover")
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("not enabled"));
}

#[cfg(target_os = "macos")]
#[test]
#[ignore = "requires explicit authorization to enumerate attached physical media"]
fn macos_discovery_never_opens_or_writes_simulated_media() {
    let output = Command::new(env!("CARGO_BIN_EXE_r46h-card"))
        .arg("discover")
        .output()
        .unwrap();
    if output.status.success() {
        let stdout = String::from_utf8(output.stdout).unwrap();
        for line in stdout.lines() {
            let candidate: Value = serde_json::from_str(line).unwrap();
            assert_eq!(candidate["platform"], "macos");
            assert!(candidate.get("stable_id").is_none());
            assert!(candidate.get("hardware_target").is_none());
            assert!(candidate.get("safe_to_boot").is_none());
        }
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        assert!(stderr.contains("no whole IOMedia") || stderr.contains("discover IOMedia"));
    }
}

fn write_bytes(path: &Path, value: u8, count: usize) {
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(path)
        .unwrap();
    file.write_all(&vec![value; count]).unwrap();
    file.sync_all().unwrap();
}

fn write_json(path: &Path, value: &Value) {
    let mut bytes = serde_json::to_vec_pretty(value).unwrap();
    bytes.push(b'\n');
    let mut file = File::create(path).unwrap();
    file.write_all(&bytes).unwrap();
    file.sync_all().unwrap();
}

fn digest(bytes: &[u8]) -> String {
    hash_reader(&mut &*bytes).unwrap().0
}
