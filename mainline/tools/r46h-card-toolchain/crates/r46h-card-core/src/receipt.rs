use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::backend::DeviceIdentity;
use crate::model::{FORMAT_VERSION, PartitionRole, VerificationMode};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct EvidenceBindings {
    pub profile_sha256: String,
    pub plan_sha256: String,
    pub tool_version: String,
    pub tool_sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TransactionReceipt {
    pub format_version: u32,
    pub transaction_id: String,
    pub plan_id: String,
    pub profile_id: String,
    pub bindings: EvidenceBindings,
    pub device: DeviceIdentity,
    pub verification: VerificationMode,
    pub state: ReceiptState,
    pub safe_to_boot: bool,
    pub operations: Vec<OperationReceipt>,
    pub unchanged_ranges: Vec<RangeReceipt>,
    #[serde(default)]
    pub failure_disposition: Option<FailureDisposition>,
    #[serde(default)]
    pub details: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ReceiptState {
    Initialized,
    PreflightComplete,
    WriteInProgress,
    WriteComplete,
    VerificationComplete,
    Ejected,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OperationReceipt {
    pub id: String,
    pub partition: PartitionRole,
    pub offset: u64,
    pub length: u64,
    pub state: OperationState,
    pub bytes_written: u64,
    pub source_sha256: String,
    pub target_sha256_before: Option<String>,
    pub target_sha256_after: Option<String>,
    pub samples_after: Vec<SampleReceipt>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum OperationState {
    Pending,
    Writing,
    Written,
    Verified,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct FailureDisposition {
    pub flush: FailureDispositionStep,
    pub eject: FailureDispositionStep,
}

impl FailureDisposition {
    pub fn is_complete(&self) -> bool {
        self.flush == FailureDispositionStep::Succeeded
            && self.eject == FailureDispositionStep::Succeeded
    }

    pub fn errors(&self) -> Vec<&str> {
        [&self.flush, &self.eject]
            .into_iter()
            .filter_map(|step| match step {
                FailureDispositionStep::Succeeded => None,
                FailureDispositionStep::Failed { error } => Some(error.as_str()),
            })
            .collect()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "state", rename_all = "snake_case", deny_unknown_fields)]
pub enum FailureDispositionStep {
    Succeeded,
    Failed { error: String },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RangeReceipt {
    pub id: String,
    pub offset: u64,
    pub length: u64,
    pub sha256_before: String,
    pub sha256_after: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct SampleReceipt {
    pub source_offset: u64,
    pub target_offset: u64,
    pub length: u64,
    pub source_sha256: String,
    pub target_sha256: String,
}

impl TransactionReceipt {
    pub fn new(
        transaction_id: String,
        plan_id: String,
        profile_id: String,
        bindings: EvidenceBindings,
        device: DeviceIdentity,
        verification: VerificationMode,
    ) -> Self {
        Self {
            format_version: FORMAT_VERSION,
            transaction_id,
            plan_id,
            profile_id,
            bindings,
            device,
            verification,
            state: ReceiptState::Initialized,
            safe_to_boot: false,
            operations: Vec::new(),
            unchanged_ranges: Vec::new(),
            failure_disposition: None,
            details: BTreeMap::new(),
        }
    }
}
