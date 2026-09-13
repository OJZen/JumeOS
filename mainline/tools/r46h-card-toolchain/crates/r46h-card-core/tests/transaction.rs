use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use r46h_card_core::backend::PlatformBackend;
use r46h_card_core::digest::hash_reader;
use r46h_card_core::file_backend::FileBackend;
use r46h_card_core::model::{
    CardProfile, FORMAT_VERSION, MbrPartitionIdentity, Partition, PartitionRole, PartitionScheme,
    Prefix, RangeAttestation, SourceImage, TargetPrecondition, VerificationMode, WriteOperation,
    WritePlan,
};
use r46h_card_core::receipt::{EvidenceBindings, FailureDispositionStep, ReceiptState};
use r46h_card_core::source::SourceRoot;
use r46h_card_core::transaction::Transaction;

const WHOLE_SIZE: u64 = 4096;
const PARTITION_SIZE: u64 = 1024;
static FIXTURE_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct Fixture {
    root: PathBuf,
    media: PathBuf,
    profile: CardProfile,
    plan: WritePlan,
}

impl Fixture {
    fn new(mode: VerificationMode) -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let sequence = FIXTURE_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!(
            "r46h-card-core-test-{}-{nonce}-{sequence}",
            std::process::id(),
        ));
        std::fs::create_dir(&root).unwrap();
        let media = root.join("media.bin");
        write_bytes(&media, 0, WHOLE_SIZE as usize);
        let source = root.join("boot.img");
        write_bytes(&source, 0xa5, PARTITION_SIZE as usize);
        let zero_512 = digest_for(&vec![0; 512]);
        let zero_partition = digest_for(&vec![0; PARTITION_SIZE as usize]);
        let source_digest = digest_for(&vec![0xa5; PARTITION_SIZE as usize]);
        let profile = CardProfile {
            format_version: FORMAT_VERSION,
            profile_id: "test-profile-v2".into(),
            target: "R46H-TEST".into(),
            whole_size: WHOLE_SIZE,
            sector_size: 512,
            partition_scheme: PartitionScheme::Mbr,
            prefix: Prefix {
                size: 512,
                sha256: zero_512,
            },
            partitions: vec![
                partition(PartitionRole::Boot, 1, 512),
                partition(PartitionRole::Root, 2, 1536),
                partition(PartitionRole::Easyroms, 3, 2560),
            ],
        };
        let backend = FileBackend::new(&media);
        let stable_id = backend.discover().unwrap().remove(0).stable_id;
        let plan = WritePlan {
            format_version: FORMAT_VERSION,
            plan_id: "test-plan-v2".into(),
            profile_id: profile.profile_id.clone(),
            target_stable_id: stable_id,
            verification: mode,
            operations: vec![WriteOperation {
                id: "write-boot".into(),
                partition: PartitionRole::Boot,
                source: SourceImage {
                    relative_path: "boot.img".into(),
                    size: PARTITION_SIZE,
                    sha256: source_digest,
                },
                target_before: TargetPrecondition::ExactSha256 {
                    sha256: zero_partition.clone(),
                },
            }],
            unchanged_ranges: vec![
                RangeAttestation {
                    id: "prefix-unchanged".into(),
                    offset: 0,
                    length: 512,
                    sha256_before: digest_for(&vec![0; 512]),
                },
                RangeAttestation {
                    id: "remainder-unchanged".into(),
                    offset: 1536,
                    length: WHOLE_SIZE - 1536,
                    sha256_before: digest_for(&vec![0; (WHOLE_SIZE - 1536) as usize]),
                },
            ],
        };
        Self {
            root,
            media,
            profile,
            plan,
        }
    }

    fn run(
        &self,
        backend: FileBackend,
    ) -> (
        r46h_card_core::Result<r46h_card_core::receipt::TransactionReceipt>,
        r46h_card_core::receipt::TransactionReceipt,
    ) {
        let stable_id = backend.discover().unwrap().remove(0).stable_id;
        let session = backend
            .claim(&stable_id, self.profile.clone(), true)
            .unwrap();
        let sources = SourceRoot::open(&self.root).unwrap();
        Transaction::new(
            session,
            &self.plan,
            &sources,
            &self.root,
            "transaction-test".into(),
            EvidenceBindings {
                profile_sha256: "1".repeat(64),
                plan_sha256: "2".repeat(64),
                tool_version: "test".into(),
                tool_sha256: "3".repeat(64),
            },
        )
        .unwrap()
        .execute()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.root).unwrap();
    }
}

#[test]
fn full_transaction_publishes_safe_receipt_after_readback() {
    let fixture = Fixture::new(VerificationMode::Full);
    let (result, receipt) = fixture.run(FileBackend::new(&fixture.media));
    assert!(result.is_ok());
    assert_eq!(receipt.state, ReceiptState::Ejected);
    assert!(receipt.safe_to_boot);
    assert!(receipt.failure_disposition.is_none());
    assert_eq!(receipt.operations.len(), 1);
    assert!(receipt.operations[0].target_sha256_after.is_some());
    assert_eq!(receipt.unchanged_ranges.len(), 2);
    let mut media = File::open(&fixture.media).unwrap();
    media.seek(SeekFrom::Start(512)).unwrap();
    let mut bytes = vec![0; PARTITION_SIZE as usize];
    media.read_exact(&mut bytes).unwrap();
    assert!(bytes.iter().all(|byte| *byte == 0xa5));
}

#[test]
fn baseline_mismatch_fails_before_any_write() {
    let mut fixture = Fixture::new(VerificationMode::Quick);
    fixture.plan.operations[0].target_before = TargetPrecondition::ExactSha256 {
        sha256: "1".repeat(64),
    };
    let before = std::fs::read(&fixture.media).unwrap();
    let (result, receipt) = fixture.run(FileBackend::new(&fixture.media));
    assert!(result.is_err());
    assert_eq!(receipt.state, ReceiptState::Failed);
    assert!(!receipt.safe_to_boot);
    assert!(receipt.operations.is_empty());
    assert_eq!(std::fs::read(&fixture.media).unwrap(), before);
}

#[test]
fn injected_short_write_never_becomes_safe_to_boot() {
    let fixture = Fixture::new(VerificationMode::Balanced);
    let (result, receipt) =
        fixture.run(FileBackend::new(&fixture.media).with_write_failure(PARTITION_SIZE / 2));
    assert!(result.is_err());
    assert_eq!(receipt.state, ReceiptState::Failed);
    assert!(!receipt.safe_to_boot);
    assert_eq!(receipt.operations.len(), 1);
    assert_eq!(receipt.operations[0].bytes_written, PARTITION_SIZE / 2);
    let disposition = receipt
        .failure_disposition
        .expect("failed-media disposition");
    assert_eq!(disposition.flush, FailureDispositionStep::Succeeded);
    assert_eq!(disposition.eject, FailureDispositionStep::Succeeded);
}

#[test]
fn v2_schema_rejects_unknown_fields_and_legacy_v1() {
    let fixture = Fixture::new(VerificationMode::Quick);
    let mut value = serde_json::to_value(&fixture.profile).unwrap();
    value["unexpected"] = serde_json::json!(true);
    assert!(serde_json::from_value::<CardProfile>(value).is_err());
    let mut legacy = serde_json::to_value(&fixture.profile).unwrap();
    legacy["format_version"] = serde_json::json!(1);
    let profile: CardProfile = serde_json::from_value(legacy).unwrap();
    assert!(profile.validate().is_err());

    let mut plan_with_forged_authorization = serde_json::to_value(&fixture.plan).unwrap();
    plan_with_forged_authorization["execution_authorization"] = serde_json::json!({
        "target_stable_id": fixture.plan.target_stable_id,
        "profile_sha256": "1".repeat(64),
        "plan_sha256": "2".repeat(64),
        "transaction_nonce": "transaction-test"
    });
    assert!(serde_json::from_value::<WritePlan>(plan_with_forged_authorization).is_err());

    let mut plan_without_attestations = serde_json::to_value(&fixture.plan).unwrap();
    plan_without_attestations
        .as_object_mut()
        .unwrap()
        .remove("unchanged_ranges");
    assert!(serde_json::from_value::<WritePlan>(plan_without_attestations).is_err());

    let mut plan_with_ads_path = fixture.plan.clone();
    plan_with_ads_path.operations[0].source.relative_path = "boot.img:stream".into();
    assert!(plan_with_ads_path.validate(&fixture.profile).is_err());
}

#[test]
fn disposable_json_request_is_denied_without_backend_authorization() {
    let mut fixture = Fixture::new(VerificationMode::Quick);
    fixture.plan.operations[0].target_before = TargetPrecondition::Disposable {
        destructive: true,
        rationale: "simulator fixture may be overwritten".into(),
    };
    let before = std::fs::read(&fixture.media).unwrap();
    let backend = FileBackend::new(&fixture.media);
    let observer = backend.clone();
    let (result, receipt) = fixture.run(backend);

    assert!(result.is_err());
    assert_eq!(observer.authorization_attempts(), 1);
    assert_eq!(std::fs::read(&fixture.media).unwrap(), before);
    assert_eq!(receipt.state, ReceiptState::Failed);
    assert!(!receipt.safe_to_boot);
    let disposition = receipt
        .failure_disposition
        .expect("failed-media disposition");
    assert!(disposition.is_complete());
}

#[test]
fn claimed_backend_can_issue_one_bound_destructive_capability() {
    let mut fixture = Fixture::new(VerificationMode::Quick);
    fixture.plan.operations[0].target_before = TargetPrecondition::Disposable {
        destructive: true,
        rationale: "simulator fixture may be overwritten".into(),
    };
    let backend = FileBackend::new(&fixture.media).with_destructive_authorization();
    let observer = backend.clone();
    let (result, receipt) = fixture.run(backend);

    assert!(result.is_ok());
    assert_eq!(observer.authorization_attempts(), 1);
    assert_eq!(receipt.state, ReceiptState::Ejected);
    assert!(receipt.safe_to_boot);
}

#[test]
fn failed_flush_never_suppresses_eject_attempt() {
    let fixture = Fixture::new(VerificationMode::Quick);
    let backend = FileBackend::new(&fixture.media)
        .with_write_failure(PARTITION_SIZE / 2)
        .with_flush_failure();
    let observer = backend.clone();
    let (result, receipt) = fixture.run(backend);

    let error = result.unwrap_err().to_string();
    assert!(error.contains("failed-media disposition incomplete"));
    assert_eq!(observer.flush_attempts(), 1);
    assert_eq!(observer.eject_attempts(), 1);
    let disposition = receipt
        .failure_disposition
        .expect("failed-media disposition");
    assert!(matches!(
        disposition.flush,
        FailureDispositionStep::Failed { .. }
    ));
    assert_eq!(disposition.eject, FailureDispositionStep::Succeeded);
}

#[test]
fn failed_eject_is_reported_without_hiding_the_primary_write_failure() {
    let fixture = Fixture::new(VerificationMode::Quick);
    let backend = FileBackend::new(&fixture.media)
        .with_write_failure(PARTITION_SIZE / 2)
        .with_eject_failure();
    let observer = backend.clone();
    let (result, receipt) = fixture.run(backend);

    let error = result.unwrap_err().to_string();
    assert!(error.contains("partial media write"));
    assert!(error.contains("failed-media disposition incomplete"));
    assert_eq!(observer.flush_attempts(), 1);
    assert_eq!(observer.eject_attempts(), 1);
    let disposition = receipt
        .failure_disposition
        .expect("failed-media disposition");
    assert_eq!(disposition.flush, FailureDispositionStep::Succeeded);
    assert!(matches!(
        disposition.eject,
        FailureDispositionStep::Failed { .. }
    ));
}

#[test]
fn construction_failure_disposes_the_already_claimed_session() {
    let fixture = Fixture::new(VerificationMode::Quick);
    let backend = FileBackend::new(&fixture.media);
    let observer = backend.clone();
    let stable_id = backend.discover().unwrap().remove(0).stable_id;
    let session = backend
        .claim(&stable_id, fixture.profile.clone(), true)
        .unwrap();
    let sources = SourceRoot::open(&fixture.root).unwrap();

    let result = Transaction::new(
        session,
        &fixture.plan,
        &sources,
        &fixture.root,
        "INVALID TRANSACTION ID".into(),
        EvidenceBindings {
            profile_sha256: "1".repeat(64),
            plan_sha256: "2".repeat(64),
            tool_version: "test".into(),
            tool_sha256: "3".repeat(64),
        },
    );

    assert!(result.is_err());
    assert_eq!(observer.flush_attempts(), 1);
    assert_eq!(observer.eject_attempts(), 1);
}

#[test]
fn external_evidence_validation_failure_disposes_the_claimed_session() {
    let fixture = Fixture::new(VerificationMode::Quick);
    let backend = FileBackend::new(&fixture.media);
    let observer = backend.clone();
    let stable_id = backend.discover().unwrap().remove(0).stable_id;
    let session = backend
        .claim(&stable_id, fixture.profile.clone(), true)
        .unwrap();
    let sources = SourceRoot::open(&fixture.root).unwrap();

    let result = Transaction::new(
        session,
        &fixture.plan,
        &sources,
        &fixture.media,
        "transaction-evidence-path-test".into(),
        EvidenceBindings {
            profile_sha256: "1".repeat(64),
            plan_sha256: "2".repeat(64),
            tool_version: "test".into(),
            tool_sha256: "3".repeat(64),
        },
    );

    assert!(result.is_err());
    assert_eq!(observer.flush_attempts(), 1);
    assert_eq!(observer.eject_attempts(), 1);
}

#[test]
fn dropping_an_unexecuted_transaction_releases_its_claimed_session() {
    let fixture = Fixture::new(VerificationMode::Quick);
    let backend = FileBackend::new(&fixture.media);
    let observer = backend.clone();
    let stable_id = backend.discover().unwrap().remove(0).stable_id;
    let session = backend
        .claim(&stable_id, fixture.profile.clone(), true)
        .unwrap();
    let sources = SourceRoot::open(&fixture.root).unwrap();
    let transaction = Transaction::new(
        session,
        &fixture.plan,
        &sources,
        &fixture.root,
        "transaction-drop-test".into(),
        EvidenceBindings {
            profile_sha256: "1".repeat(64),
            plan_sha256: "2".repeat(64),
            tool_version: "test".into(),
            tool_sha256: "3".repeat(64),
        },
    )
    .unwrap();

    drop(transaction);

    assert_eq!(observer.flush_attempts(), 1);
    assert_eq!(observer.eject_attempts(), 1);
}

fn partition(role: PartitionRole, number: u32, offset: u64) -> Partition {
    Partition {
        role,
        number,
        offset,
        size: PARTITION_SIZE,
        mbr: Some(MbrPartitionIdentity {
            bootable: false,
            type_code: match role {
                PartitionRole::Boot => 0x0c,
                PartitionRole::Root => 0x83,
                PartitionRole::Easyroms => 0x07,
            },
        }),
        filesystem: None,
        identifiers: Default::default(),
    }
}

fn write_bytes(path: &Path, byte: u8, count: usize) {
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(path)
        .unwrap();
    file.write_all(&vec![byte; count]).unwrap();
    file.sync_all().unwrap();
}

fn digest_for(bytes: &[u8]) -> String {
    let mut reader = bytes;
    hash_reader(&mut reader).unwrap().0
}
